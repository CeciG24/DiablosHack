"""F3: separate temporal and cold-pitcher experiments on the same eligible pitches."""
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
import re
import shutil
import sys
import time
import uuid

import numpy as np
from modeling.baselines import CLASSES, EventBaseline
from modeling.cli import verify, write_json
from modeling.datasets import ROOT, FEATURES, META, ModelingDataset, ids_hash, pd, sha256_file
from modeling.metrics import calibration_bins, multiclass_metrics, paired_bootstrap, per_pitch_losses
from modeling.models import BACKEND_VERSION, TabularEventModel
from modeling.phase2 import verify_f1
from modeling.protocols import assign_pitcher_partitions

NAMES = {'stuff': 'Stuff', 'location': 'Location', 'pitching': 'Pitching'}
PROBABILITIES = ['p_' + label for label in CLASSES]
PAIRS = [('Stuff', 'B1'), ('Location', 'B1'), ('Pitching', 'Location'), ('Pitching', 'B1')]


def verify_f2(dataset):
    verify_f1(dataset)
    cfg = dataset.config
    if next(p for p in cfg['phases'] if p['id'] == 'F2')['status'] != 'verified':
        raise RuntimeError('F2 must be verified')
    name = cfg['F3']['f2_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', name):
        raise ValueError('Invalid F2 reference ID')
    folder = dataset.root / 'artifacts/modeling' / name / 'F2'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest['status'] != 'verified' or manifest['phase_id'] != 'F2' or manifest['smoke']
            or manifest['test_accessed'] or manifest['data_run'] != dataset.run_id
            or manifest['data_manifest_sha256'] != dataset.manifest_hash):
        raise RuntimeError('F2 must be a verified full run on the pinned data')
    required = {'stuff/model.txt', 'stuff/preprocessing.json', 'B1.json', 'predictions.parquet',
                'config.json', 'checks.json', 'cohort_manifest.json'}
    if not required.issubset(manifest['artifact_hashes']):
        raise RuntimeError('Incomplete F2 artifacts')
    for name, digest in manifest['artifact_hashes'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise RuntimeError('F2 artifact integrity failure: ' + name)
    checks = json.loads((folder / 'checks.json').read_text(encoding='utf-8'))
    if not checks or not all(value is True for value in checks.values()):
        raise RuntimeError('F2 technical checks failed')
    previous = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    for key in ('expected_data_run', 'primary_target', 'event_class_order', 'seed', 'protocol_A', 'F2', 'evaluation', 'numerical_checks'):
        if cfg[key] != previous[key]:
            raise RuntimeError('F2 contract changed: ' + key)
    return folder, manifest


def select_model(training, development, settings, seed, directory, family, protocol, smoke):
    if not 1 <= len(settings['candidates']) <= 12:
        raise ValueError('At most 12 predeclared configurations per family/protocol')
    trials = settings['candidates'][:1] if smoke else settings['candidates']
    results = []
    for i, parameters in enumerate(trials):
        print(f'F3 {protocol}/{family}: candidate {i+1}/{len(trials)}', flush=True)
        model = TabularEventModel(seed, settings['threads'], family, protocol).fit(
            training, development, parameters,
            settings['smoke_rounds'] if smoke else settings['maximum_rounds'], settings['early_stopping_rounds'])
        name = f'candidate_{i+1:02}'
        model.save(directory / name)
        score = multiclass_metrics(development.y_event, model.predict(development), CLASSES)['multiclass_log_loss']
        results.append({'candidate_id': name, 'parameters': parameters, 'development_log_loss': score,
                        'best_iteration': model.metadata['best_iteration']})
    selected = min(results, key=lambda x: (x['development_log_loss'], x['candidate_id']))
    return TabularEventModel.load(directory / selected['candidate_id']), {
        'family': family, 'protocol_id': protocol, 'selected': selected, 'trials': results,
        'selection_partition': 'development', 'review_used_for_selection': False,
        'fit_ids_sha256': ids_hash(training.pitch_uid.tolist()),
        'development_ids_sha256': ids_hash(development.pitch_uid.tolist())}


def partition_summary(rows):
    return {part: {'n_pitches': len(group), 'n_games': int(group.game_anon_id.nunique()),
                   'n_pitchers': int(group.pitcher_anon_id.nunique()),
                   'years': sorted(int(y) for y in group.year.unique()),
                   'ids_sha256': ids_hash(group.pitch_uid.tolist())}
            for part, group in rows.groupby('partition')}


def family_decisions(comparisons, smoke):
    decisions = {name: 'inconclusive' if smoke else 'retain_reference' for name in NAMES.values()}
    if not smoke:
        for family in ('Stuff', 'Location'):
            if comparisons[family + '_vs_B1']['decision'] == 'promote':
                decisions[family] = 'promote'
        if all(comparisons['Pitching_vs_' + name]['decision'] == 'promote' for name in ('Location', 'B1')):
            decisions['Pitching'] = 'promote'
    reference = 'Pitching' if decisions['Pitching'] == 'promote' else ('Location' if decisions['Location'] == 'promote' else 'B1')
    return {'families': decisions, 'predictive_reference': reference,
            'physical_increment_over_location': comparisons['Pitching_vs_Location']['decision'],
            'scientific_decision': 'inconclusive' if smoke else ('promote' if reference != 'B1' else 'retain_reference')}


def run_protocol(rows, cohort, protocol, folder, cfg, reference_folder, smoke, checks):
    folder.mkdir()
    settings = cfg['F3']
    if protocol == 'B':
        rows = assign_pitcher_partitions(rows, settings['protocol_B_validation_hash_seed'])
    rows = rows.sort_values('pitch_uid').reset_index(drop=True)
    training = rows.loc[rows.partition.eq('train')].copy()
    development = rows.loc[rows.partition.eq('development')].copy()
    evaluation = rows.loc[rows.partition.ne('train')].copy().reset_index(drop=True)
    if set(rows.partition) != {'train', 'development', 'calibration', 'phase_review'}:
        raise ValueError('All four protocol partitions are required')
    if protocol == 'B':
        pitcher_sets = {s: set(g.pitcher_anon_id) for s, g in rows.groupby('pitcher_split')}
        checks['B_pitcher_groups_disjoint'] = all(not pitcher_sets[a] & pitcher_sets[b]
                                                 for a, b in [('train', 'validation'), ('train', 'test'), ('validation', 'test')])
        validation = rows.loc[rows.pitcher_split.eq('validation')]
        checks['B_validation_games_separated'] = bool(validation.groupby('game_anon_id').partition.nunique().eq(1).all())
        shuffled = assign_pitcher_partitions(rows.sample(frac=1, random_state=7), settings['protocol_B_validation_hash_seed'])
        checks['B_assignment_shuffle_invariant'] = rows.equals(shuffled)
    checks[protocol + '_no_2026'] = bool(rows.year.isin([2024, 2025]).all())
    rows[META + ['y_event']].to_parquet(folder / 'cohort.parquet', index=False)
    coverage = {}
    for family, own in cohort['families'].items():
        if protocol == 'B':
            own = assign_pitcher_partitions(own, settings['protocol_B_validation_hash_seed'])
        coverage[family] = {'own_eligible': partition_summary(own), 'common': partition_summary(rows),
                            'own_metrics_computed': False}
    write_json(folder / 'coverage.json', {'families': coverage, 'quality_exclusions': cohort['exclusions'],
               'denominator': 'sampled 2024/2025 before family quality filters',
               'sampled_rows': len(cohort['sampled_ids']),
               'policy': 'Prepared quality flags unchanged, including environment availability in Pitching eligibility; altitude is not a predictor'})
    summary = partition_summary(rows)
    write_json(folder / 'cohort_manifest.json', {'partitions': summary, 'common_ids_sha256': ids_hash(rows.pitch_uid.tolist()),
               'temporal': protocol == 'A', 'games_may_cross_pitcher_groups': protocol == 'B',
               'fit_review_shared_games': len(set(training.game_anon_id) & set(rows.loc[rows.partition.eq('phase_review'), 'game_anon_id'])),
               'validation_assignment': '50/50 hash by game' if protocol == 'B' else 'protocol_A'})
    if not all(checks.values()):
        raise RuntimeError('Cohort integrity failed before model fitting')
    models, selections = {}, {}
    frozen = protocol == 'A' and not smoke
    if frozen:
        shutil.copyfile(reference_folder / 'B1.json', folder / 'B1.json')
    else:
        EventBaseline('B1', CLASSES, cfg['training']['baseline_global_pseudocount_per_class'],
                      cfg['training']['baseline_group_prior_strength']).fit(training, protocol).save(folder / 'B1.json')
    baseline = EventBaseline.load(folder / 'B1.json')
    checks[protocol + '_B1_fit_ids'] = baseline.state['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
    for family in NAMES:
        if family == 'stuff' and frozen:
            shutil.copytree(reference_folder / 'stuff', folder / family)
            model = TabularEventModel.load(folder / family)
            selections[family] = {'policy': 'frozen_F2', 'model_sha256': sha256_file(folder / family / 'model.txt')}
        else:
            model, selections[family] = select_model(training, development, settings, cfg['seed'],
                                                     folder / 'candidates' / family, family, protocol, smoke)
            model.save(folder / family)
        models[family] = model
        checks[protocol + '_' + family + '_fit_ids'] = model.metadata['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
        checks[protocol + '_' + family + '_features'] = model.booster.feature_name() == FEATURES[family]
    # Freeze all selections before any review predictions are computed.
    write_json(folder / 'selection.json', selections)
    predictions, metrics, curves, losses, reproduction = [], [], [], {}, {}
    for name in ('B1', 'Stuff', 'Location', 'Pitching'):
        if name == 'B1':
            probabilities, routes = baseline.predict(evaluation)
            warnings = [''] * len(evaluation)
            model_hash = sha256_file(folder / 'B1.json')
        else:
            family = name.lower()
            model = models[family]
            probabilities = model.predict(evaluation)
            reloaded = TabularEventModel.load(folder / family)
            difference = float(np.max(np.abs(probabilities - reloaded.predict(evaluation))))
            checks[f'{protocol}_{family}_reload'] = difference <= cfg['numerical_checks']['reload_prediction_atol_cpu']
            reproduction[family] = {'reload_max_abs_difference': difference}
            # Refit the chosen configuration to test determinism, without a new search.
            if not (family == 'stuff' and frozen):
                replay = TabularEventModel(cfg['seed'], settings['threads'], family, protocol).fit(
                    training, development, selections[family]['selected']['parameters'],
                    settings['smoke_rounds'] if smoke else settings['maximum_rounds'], settings['early_stopping_rounds'])
                difference = float(np.max(np.abs(probabilities - replay.predict(evaluation))))
                reproduction[family]['refit_max_abs_difference'] = difference
                checks[f'{protocol}_{family}_deterministic_refit'] = difference <= cfg['numerical_checks']['reload_prediction_atol_cpu']
            changed = evaluation.head(100).copy()
            for column in set(FEATURES['pitching'] + ['altitude_category', 'pitch_uid', 'y_event']) - set(FEATURES[family]):
                changed[column] = 'excluded_feature_changed'
            checks[f'{protocol}_{family}_excluded_features_invariant'] = bool(np.array_equal(probabilities[:len(changed)], model.predict(changed)))
            warnings = model.warnings(evaluation)
            routes = family + '_without_environment'
            model_hash = sha256_file(folder / family / 'model.txt')
        prediction = evaluation[META + ['y_event']].copy()
        prediction[PROBABILITIES] = probabilities
        prediction['model'], prediction['route'], prediction['warnings'] = name, routes, warnings
        prediction['protocol_id'], prediction['model_version'] = protocol, model_hash
        prediction['data_version'] = cfg['expected_data_run']
        prediction['status'] = 'smoke_only' if smoke else 'ok'
        predictions.append(prediction)
        for part, group in prediction.groupby('partition'):
            result = multiclass_metrics(group.y_event, group[PROBABILITIES].to_numpy(), CLASSES,
                                        cfg['numerical_checks']['log_loss_clipping_epsilon'])
            result.update(model=name, partition=part, protocol_id=protocol, n_games=int(group.game_anon_id.nunique()),
                          n_pitchers=int(group.pitcher_anon_id.nunique()), ids_sha256=ids_hash(group.pitch_uid.tolist()))
            metrics.append(result)
            curves.extend(dict(row, model=name, partition=part) for row in calibration_bins(group.y_event, group[PROBABILITIES].to_numpy(), CLASSES))
            if part == 'phase_review':
                loss, _ = per_pitch_losses(group.y_event, group[PROBABILITIES].to_numpy(), CLASSES)
                losses[name] = group[['pitch_uid', 'game_anon_id', 'y_event']].assign(loss=loss)
    predictions = pd.concat(predictions, ignore_index=True)
    if frozen:
        past = pd.read_parquet(reference_folder / 'predictions.parquet')
        for name in ('B1', 'Stuff'):
            old = past.loc[past.model.eq(name)].sort_values('pitch_uid')
            new = predictions.loc[predictions.model.eq(name)].sort_values('pitch_uid')
            checks['A_' + name + '_matches_frozen_F2'] = (old.pitch_uid.tolist() == new.pitch_uid.tolist()
                and old.y_event.tolist() == new.y_event.tolist() and np.array_equal(old[PROBABILITIES].to_numpy(), new[PROBABILITIES].to_numpy()))
    comparisons = {candidate + '_vs_' + reference: paired_bootstrap(
        losses[reference], losses[candidate], cfg['evaluation']['bootstrap_smoke' if smoke else 'bootstrap_full'],
        cfg['seed'], cfg['evaluation']['bootstrap_confidence'], cfg['evaluation']['promotion_min_relative_log_loss_reduction'], smoke)
        for candidate, reference in PAIRS}
    decision = family_decisions(comparisons, smoke)
    checks[protocol + '_unique_pitch_model_pairs'] = not predictions.duplicated(['pitch_uid', 'model']).any()
    checks[protocol + '_finite_metrics'] = bool(np.isfinite([m[k] for m in metrics for k in ('multiclass_log_loss', 'multiclass_brier_sum_over_classes')]).all())
    predictions.to_parquet(folder / 'predictions.parquet', index=False)
    checks[protocol + '_parquet_roundtrip'] = predictions.equals(pd.read_parquet(folder / 'predictions.parquet'))
    pd.DataFrame(metrics).to_csv(folder / 'comparison_table.csv', index=False)
    pd.DataFrame(curves).to_csv(folder / 'calibration.csv', index=False)
    write_json(folder / 'reproducibility.json', reproduction)
    write_json(folder / 'metrics.json', {'protocol_id': protocol, 'status': 'smoke_only' if smoke else 'evaluated',
               'target': 'y_event', 'denominator': 'common eligible pitches; four models on identical IDs and labels',
               'class_order': list(CLASSES), 'metrics': metrics, 'comparisons': comparisons, 'decision': decision,
               'review_is_independent_final_test': False})
    return decision, summary


def train_families(experiment_id=None, smoke=False, root=ROOT):
    started, tick = datetime.now(timezone.utc), time.perf_counter()
    dataset = ModelingDataset(root)
    cfg, settings = dataset.config, dataset.config['F3']
    reference_folder, reference = verify_f2(dataset)
    if (settings['cohort_policy'] != 'f0_common_v1' or cfg['training']['backend'] != 'lightgbm==' + BACKEND_VERSION
            or cfg['protocol_B']['development_years_only'] != [2024, 2025]
            or settings['protocol_B_development_bucket'] != [0, 4999]
            or settings['protocol_B_calibration_bucket'] != [5000, 9999]):
        raise ValueError('Unsupported F3 cohort/backend/protocol')
    experiment_id = experiment_id or started.strftime('f3-%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root / 'artifacts/modeling' / experiment_id / 'F3'
    folder.mkdir(parents=True, exist_ok=False)
    sources = sorted((dataset.root / 'modeling').glob('*.py')) + [dataset.root / 'diablos_data.py']
    manifest = {'experiment_id': experiment_id, 'phase_id': 'F3', 'status': 'in_progress',
                'scientific_decision': 'not_applicable', 'protocol_ids': ['A', 'B'], 'smoke': smoke,
                'target': 'y_event', 'feature_sets': FEATURES, 'seed': cfg['seed'],
                'data_run': dataset.run_id, 'data_manifest_sha256': dataset.manifest_hash,
                'data_output_hashes': dataset.manifest['outputs'], 'config_sha256': dataset.config_hash,
                'document_sha256': sha256_file(dataset.root / cfg['document']),
                'code_hashes': {str(p.relative_to(dataset.root)): sha256_file(p) for p in sources},
                'requirements_sha256': sha256_file(dataset.root / 'requirements-modeling.txt'),
                'dependency_F2': {'experiment_id': reference['experiment_id'], 'manifest_sha256': sha256_file(reference_folder / 'manifest.json')},
                'versions': {'python': platform.python_version(), **{n: importlib.metadata.version(n) for n in ('numpy', 'pandas', 'pyarrow', 'duckdb', 'lightgbm', 'scipy')}},
                'python_executable': sys.executable, 'virtual_environment': sys.prefix != sys.base_prefix,
                'started_utc': started.isoformat(), 'test_accessed': False, 'test_quality_previously_profiled': True,
                'hardware': {'processor': platform.processor(), 'machine': platform.machine(), 'threads_used': settings['threads']}}
    write_json(folder / 'manifest.json', manifest)
    write_json(folder / 'config.json', cfg)
    checks = {}
    try:
        cohort = dataset.load(maximum=cfg['training']['smoke_target_max_pitches'] if smoke else None, phase='F3')
        checks.update(verify(cohort, dataset))
        rows = cohort['aligned']['pitching']
        if not smoke:
            checks['same_F2_common_cohort'] = ids_hash(rows.pitch_uid.tolist()) == reference['cohort']['common_ids_sha256']
        if not all(checks.values()):
            raise RuntimeError('F3 cohort does not match approved dependencies')
        decisions, summaries = {}, {}
        for protocol in ('A', 'B'):
            decisions[protocol], summaries[protocol] = run_protocol(rows, cohort, protocol, folder / protocol, cfg, reference_folder, smoke, checks)
        write_json(folder / 'metrics.json', {'protocol_decisions': decisions, 'primary_protocol': 'A',
                   'protocols_are_not_directly_comparable': True, 'test_accessed': False})
        write_json(folder / 'cohort_manifest.json', summaries)
        write_json(folder / 'checks.json', {k: bool(v) for k, v in checks.items()})
        if not all(checks.values()):
            raise RuntimeError('Failed checks: ' + ', '.join(k for k, v in checks.items() if not v))
        dataset.assert_unchanged()
        manifest.update(status='verified', scientific_decision=decisions['A']['scientific_decision'], protocol_decisions=decisions)
        (folder / 'decision.md').write_text('# F3\n\nImplementación: verified.\n\n' +
            '\n'.join(f"- Protocolo {p}: {d['scientific_decision']}; referencia predictiva {d['predictive_reference']}; familias {d['families']}" for p, d in decisions.items()) +
            '\n\nA es temporal; B usa pitchers separados en 2024/2025, con posibles partidos compartidos entre grupos. '
            'Desarrollo/calibración de B se separan por partido. Sin historia de arsenal.\n\n'
            'Location es asociación condicionada a ubicación/contexto, no comando causal. '
            '2026 sellado; sin calibradores, scores ni xRunValue. '
            + ('Smoke no habilita F4.' if smoke else 'F4 habilitada tras pruebas; no iniciada automáticamente.') + '\n', encoding='utf-8')
    except Exception as exc:
        manifest.update(status='blocked', error=f'{type(exc).__name__}: {exc}')
        write_json(folder / 'checks.json', {**{k: bool(v) for k, v in checks.items()}, 'technical_failure': False})
        (folder / 'decision.md').write_text('# F3 blocked\n\n' + manifest['error'], encoding='utf-8')
        raise
    finally:
        manifest.update(finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.perf_counter() - tick)
        manifest['artifact_hashes'] = {p.relative_to(folder).as_posix(): sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file() and p != folder / 'manifest.json'}
        write_json(folder / 'manifest.json', manifest)
    print(json.dumps({'path': str(folder), 'status': manifest['status'], 'decisions': decisions}, indent=2), flush=True)
    return folder
