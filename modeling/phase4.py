"""F4 protocol A: frozen events, calibration-only temperatures, conditional auxiliary heads."""
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

from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler, calibration_decision
from modeling.cli import verify, write_json
from modeling.contact import (HEADS, AuxiliaryModel, head_metrics, joint_contact_probabilities,
                              load_targets, sample_support, smoothed_prevalence)
from modeling.datasets import ROOT, FEATURES, META, ModelingDataset, ids_hash, join_pitches, pd, sha256_file
from modeling.metrics import calibration_bins, multiclass_metrics, paired_bootstrap, per_pitch_losses, write_calibration_svg
from modeling.models import TabularEventModel
from modeling.phase3 import PROBABILITIES, partition_summary, verify_f2


def verify_f3(dataset):
    verify_f2(dataset)
    cfg = dataset.config
    if next(p for p in cfg['phases'] if p['id'] == 'F3')['status'] != 'verified':
        raise RuntimeError('F3 must be verified')
    name = cfg['F4']['f3_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', name):
        raise ValueError('Invalid F3 dependency')
    folder = dataset.root / 'artifacts/modeling' / name / 'F3'
    m = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if (m['status'] != 'verified' or m['smoke'] or m['phase_id'] != 'F3' or m['test_accessed']
            or m['data_run'] != dataset.run_id or m['data_manifest_sha256'] != dataset.manifest_hash):
        raise RuntimeError('F3 is not an approved full run on pinned data')
    required = {'A/predictions.parquet', 'A/cohort_manifest.json', 'A/cohort.parquet', 'config.json', 'checks.json'}
    required |= {f'A/{f}/{name}' for f in FEATURES for name in ('model.txt', 'preprocessing.json')}
    if not required.issubset(m['artifact_hashes']):
        raise RuntimeError('Incomplete F3 evidence')
    for name, digest in m['artifact_hashes'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise RuntimeError('F3 artifact integrity failure: '+name)
    checks = json.loads((folder / 'checks.json').read_text(encoding='utf-8'))
    if not checks or not all(v is True for v in checks.values()):
        raise RuntimeError('F3 checks failed')
    previous = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    for key in ('expected_data_run', 'primary_target', 'event_class_order', 'seed', 'protocol_A', 'F3', 'evaluation', 'numerical_checks'):
        if cfg[key] != previous[key]:
            raise RuntimeError('F3 configuration changed: '+key)
    return folder, m


def support(rows, target, classes, cfg):
    return sample_support(rows, target, classes, cfg['evaluation']['auxiliary_min_rows_per_fit_and_review'],
                          cfg['evaluation']['auxiliary_min_each_class_per_fit_and_review'])


def calibrate(rows, probabilities, target, classes, folder, cfg, auxiliary=False, smoke=False):
    """Persist a fitted scalar before looking at review loss; never refit on review."""
    calibration = rows.partition.eq('calibration').to_numpy() & rows[target].notna().to_numpy()
    cal_rows = rows.loc[calibration]
    cal_support = support(cal_rows, target, classes, cfg)
    scaler = TemperatureScaler(classes)
    candidate = probabilities.copy()
    if cal_support['sufficient']:
        scaler.fit(cal_rows, probabilities[calibration], target)
        scaler.save(folder / 'temperature.json')
        loaded = TemperatureScaler.load(folder / 'temperature.json')
        candidate = loaded.transform(probabilities)
        if not np.array_equal(candidate, scaler.transform(probabilities)):
            raise RuntimeError('Calibrator reload changed predictions')
    review = rows.partition.eq('phase_review').to_numpy() & rows[target].notna().to_numpy()
    review_support = support(rows.loc[review], target, classes, cfg)
    route = 'identity'
    comparison = None
    if review_support['sufficient']:
        raw = multiclass_metrics(rows.loc[review, target], probabilities[review], classes)['multiclass_log_loss']
        new = multiclass_metrics(rows.loc[review, target], candidate[review], classes)['multiclass_log_loss']
        if cal_support['sufficient']:
            route = calibration_decision(raw, new, cfg['F4']['calibration_acceptance_max_relative_increase'])
        comparison = {'raw_log_loss': raw, 'temperature_log_loss': new, 'relative_increase': (new-raw)/raw}
    chosen = candidate if route == 'temperature' else probabilities
    policy = {'route': route, 'temperature': scaler.temperature, 'fit_support': cal_support,
              'fit_status': 'fitted' if cal_support['sufficient'] else 'insufficient_data_identity',
              'review_support': review_support, 'review_comparison': comparison,
              'paired_comparison': compare_head(rows.loc[review], target, classes, probabilities[review], candidate[review], cfg, smoke) if review_support['sufficient'] else None,
              'fit_partition': '2025/calibration', 'review_refit': False, 'acceptance_max_relative_increase': 0.0}
    write_json(folder / 'calibration_policy.json', policy)
    metrics, curves = [], []
    for part in ('development', 'calibration', 'phase_review'):
        mask = rows.partition.eq(part).to_numpy() & rows[target].notna().to_numpy()
        eligible = rows.loc[mask]
        sufficient = support(eligible, target, classes, cfg)['sufficient']
        for name, p in (('raw', probabilities), ('temperature', candidate), ('selected', chosen)):
            if not len(eligible) or (auxiliary and not sufficient):
                metrics.append({'partition': part, 'variant': name, 'status': 'insufficient_data', 'n_pitches': len(eligible)})
                continue
            result = head_metrics(eligible[target], p[mask], classes) if auxiliary else multiclass_metrics(eligible[target], p[mask], classes)
            result.update(partition=part, variant=name, status='evaluated', ids_sha256=ids_hash(eligible.pitch_uid.tolist()),
                          n_games=int(eligible.game_anon_id.nunique()))
            metrics.append(result)
            curves.extend(dict(row, model=name, partition=part) for row in calibration_bins(eligible[target], p[mask], classes))
    pd.DataFrame(curves).to_csv(folder / 'calibration.csv', index=False)
    for part in ('calibration', 'phase_review'):
        write_calibration_svg(folder / f'calibration_{part}.svg', curves, part, classes,
                              colors={'raw': '#64748b', 'temperature': '#2563eb', 'selected': '#16a34a'}, phase='F4 '+target)
    write_json(folder / 'calibration_metrics.json', metrics)
    return chosen, candidate, policy


def compare_head(rows, target, classes, baseline, candidate, cfg, smoke):
    losses = []
    for p in (baseline, candidate):
        loss, _ = per_pitch_losses(rows[target], p, classes)
        losses.append(rows[['pitch_uid', 'game_anon_id']].assign(y_event=rows[target].to_numpy(), loss=loss))
    return paired_bootstrap(*losses, cfg['evaluation']['bootstrap_smoke' if smoke else 'bootstrap_full'], cfg['seed'],
                            cfg['evaluation']['bootstrap_confidence'], cfg['evaluation']['promotion_min_relative_log_loss_reduction'], smoke)


def train_head(rows, evaluation, family, head, folder, cfg, smoke, checks):
    folder.mkdir(parents=True)
    classes = HEADS[head]
    coverage = {part: support(group, head, classes, cfg) for part, group in rows.groupby('partition')}
    for part, group in rows.groupby('partition'):
        coverage[part]['in_play_rows'] = int(group.y_event.eq('in_play').sum())
        if head != 'chase':
            coverage[part]['in_play_missing_measurement'] = int((group.y_event.eq('in_play') & group[head].isna()).sum())
    write_json(folder / 'coverage.json', coverage)
    training = rows.loc[rows.partition.eq('train') & rows[head].notna()]
    development = rows.loc[rows.partition.eq('development') & rows[head].notna()]
    key = family + '_' + head
    if not all(coverage[p]['sufficient'] for p in ('train', 'development', 'phase_review')):
        decision = {'status': 'insufficient_data', 'scientific_decision': 'inconclusive', 'route': 'unavailable',
                    'reason': 'minimum_200_rows_and_20_each_class_required_in_fit_development_review', 'comparison': None}
        write_json(folder / 'decision.json', decision)
        return None, decision
    print(f'F4 {family}/{head}: fitting {len(training)} measured/conditional rows', flush=True)
    settings = cfg['F4']
    model = AuxiliaryModel(family, head, cfg['seed'], settings['threads']).fit(training, development,
        settings['auxiliary_parameters'], settings['smoke_rounds'] if smoke else settings['maximum_rounds'], settings['early_stopping_rounds'])
    model.save(folder / 'model')
    write_json(folder / 'selection.json', {'search_configurations': 1, 'parameters': settings['auxiliary_parameters'],
               'selection_partition': 'development', 'best_iteration': model.metadata['best_iteration'], 'review_used_for_selection': False})
    probabilities = model.predict(evaluation)
    loaded = AuxiliaryModel.load(folder / 'model')
    checks[key + '_reload_exact'] = bool(np.array_equal(probabilities, loaded.predict(evaluation)))
    checks[key + '_fit_ids'] = model.metadata['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
    checks[key + '_features'] = model.booster.feature_name() == FEATURES[family]
    changed = evaluation.head(50).copy()
    for column in set(FEATURES['pitching'] + ['altitude_category', head, 'y_event', 'pitch_uid']) - set(FEATURES[family]):
        changed[column] = 'excluded'
    checks[key + '_excluded_features_invariant'] = bool(np.array_equal(probabilities[:len(changed)], model.predict(changed)))
    replay = AuxiliaryModel(family, head, cfg['seed'], settings['threads']).fit(training, development, settings['auxiliary_parameters'],
        settings['smoke_rounds'] if smoke else settings['maximum_rounds'], settings['early_stopping_rounds'])
    difference = float(np.max(np.abs(probabilities-replay.predict(evaluation))))
    checks[key + '_deterministic_refit'] = difference <= cfg['numerical_checks']['reload_prediction_atol_cpu']
    write_json(folder / 'reproducibility.json', {'refit_max_abs_difference': difference, 'reload_exact': checks[key+'_reload_exact']})
    selected, calibrated, calibration = calibrate(evaluation, probabilities, head, classes, folder, cfg, auxiliary=True, smoke=smoke)
    prevalence = smoothed_prevalence(training, head, classes)
    baseline = np.tile(prevalence, (len(evaluation), 1))
    write_json(folder / 'baseline.json', {'classes': list(classes), 'probabilities': prevalence.tolist(), 'pseudocount': 1,
               'fit_year': 2024, 'fit_partition': 'train', 'fit_ids_sha256': ids_hash(training.pitch_uid.tolist()), 'fit_rows': len(training)})
    review = evaluation.partition.eq('phase_review').to_numpy() & evaluation[head].notna().to_numpy()
    comparison = compare_head(evaluation.loc[review], head, classes, baseline[review], selected[review], cfg, smoke)
    promote = comparison['decision'] == 'promote'
    decision = {'status': 'validated' if promote else 'experimental', 'scientific_decision': 'promote' if promote else ('inconclusive' if smoke else 'retain_reference'),
                'route': 'model' if promote else 'smoothed_training_prevalence', 'comparison': comparison,
                'calibration_route': calibration['route'], 'semantics': 'conditional_given_outside' if head=='chase' else 'conditional_given_in_play'}
    write_json(folder / 'decision.json', decision)
    diagnostic = evaluation[META + ['y_event', head]].copy()
    for name, p in (('raw', probabilities), ('temperature', calibrated), ('selected', selected), ('baseline', baseline)):
        for i, label in enumerate(classes):
            diagnostic[f'{name}_{label}'] = p[:, i]
    diagnostic.to_parquet(folder / 'predictions.parquet', index=False)
    baseline_metrics = []
    for part in ('development', 'calibration', 'phase_review'):
        mask = evaluation.partition.eq(part).to_numpy() & evaluation[head].notna().to_numpy()
        if coverage[part]['sufficient']:
            baseline_metrics.append(dict(head_metrics(evaluation.loc[mask, head], baseline[mask], classes), partition=part,
                                         ids_sha256=ids_hash(evaluation.loc[mask, 'pitch_uid'].tolist()), status='evaluated'))
        else:
            baseline_metrics.append({'partition': part, 'status': 'insufficient_data'})
    write_json(folder / 'baseline_metrics.json', baseline_metrics)
    return selected if promote else baseline, decision


def train_calibration_contact(experiment_id=None, smoke=False, root=ROOT):
    started, tick = datetime.now(timezone.utc), time.perf_counter()
    dataset = ModelingDataset(root)
    cfg = dataset.config
    if cfg['F4']['protocol_id'] != 'A' or cfg['F4']['heads'] != list(HEADS) or cfg['F4']['calibration_acceptance_max_relative_increase'] != 0:
        raise ValueError('Unsupported F4 protocol or policy')
    reference_folder, reference = verify_f3(dataset)
    experiment_id = experiment_id or started.strftime('f4-%Y%m%dT%H%M%S-')+uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root / 'artifacts/modeling' / experiment_id / 'F4'
    folder.mkdir(parents=True, exist_ok=False)
    sources = sorted((dataset.root / 'modeling').glob('*.py')) + [dataset.root / 'diablos_data.py']
    manifest = {'phase_id': 'F4', 'experiment_id': experiment_id, 'status': 'in_progress', 'scientific_decision': 'not_applicable',
                'protocol_id': 'A', 'smoke': smoke, 'seed': cfg['seed'], 'data_run': dataset.run_id,
                'data_manifest_sha256': dataset.manifest_hash, 'data_output_hashes': dataset.manifest['outputs'],
                'config_sha256': dataset.config_hash, 'code_hashes': {str(p.relative_to(dataset.root)): sha256_file(p) for p in sources},
                'document_sha256': sha256_file(dataset.root / cfg['document']),
                'requirements_sha256': sha256_file(dataset.root / 'requirements-modeling.txt'),
                'dependency_F3': {'experiment_id': reference['experiment_id'], 'manifest_sha256': sha256_file(reference_folder / 'manifest.json')},
                'versions': {'python': platform.python_version(), **{n: importlib.metadata.version(n) for n in ('numpy','pandas','lightgbm','scipy','pyarrow','duckdb')}},
                'python_executable': sys.executable, 'virtual_environment': sys.prefix != sys.base_prefix,
                'started_utc': started.isoformat(), 'test_accessed': False, 'test_quality_previously_profiled': True,
                'feature_sets': FEATURES, 'protocol_B': 'retained_F3_not_calibrated_in_F4',
                'hardware': {'processor': platform.processor(), 'threads_used': cfg['F4']['threads']}}
    write_json(folder / 'manifest.json', manifest)
    write_json(folder / 'config.json', cfg)
    checks, decisions = {}, {}
    try:
        cohort = dataset.load(maximum=cfg['training']['smoke_target_max_pitches'] if smoke else None, phase='F4')
        checks.update(verify(cohort, dataset))
        rows = load_targets(dataset, cohort['aligned']['pitching'])
        if not smoke:
            past = json.loads((reference_folder / 'A/cohort_manifest.json').read_text(encoding='utf-8'))
            checks['same_F3_common_ids'] = ids_hash(rows.pitch_uid.tolist()) == past['common_ids_sha256']
        rows[META + ['y_event'] + list(HEADS)].to_parquet(folder / 'cohort.parquet', index=False)
        write_json(folder / 'cohort_manifest.json', {'common_ids_sha256': ids_hash(rows.pitch_uid.tolist()),
                   'partitions': partition_summary(rows), 'exclusions': cohort['exclusions'],
                   'denominator': 'F0/F3 common eligible events; conditional measurements are a strict labeled subset'})
        evaluation = rows.loc[rows.partition.ne('train')].reset_index(drop=True)
        approved = pd.read_parquet(reference_folder / 'A/predictions.parquet')
        all_output = []
        if not all(checks.values()):
            raise RuntimeError('F4 cohort checks failed before fitting')
        for family in FEATURES:
            print('F4 '+family+': calibrating frozen F3 events', flush=True)
            destination = folder / family
            destination.mkdir()
            event_folder = destination / 'event'
            event_folder.mkdir()
            shutil.copytree(reference_folder / 'A' / family, event_folder / 'model')
            model = TabularEventModel.load(event_folder / 'model')
            saved = approved.loc[approved.model.eq(family.title()), ['pitch_uid'] + PROBABILITIES]
            aligned = join_pitches(evaluation[['pitch_uid']], saved)
            if len(aligned) != len(evaluation):
                raise RuntimeError('F3 probabilities do not cover the F4 population')
            probabilities = aligned[PROBABILITIES].to_numpy()
            checks[family+'_frozen_F3_predictions'] = bool(np.array_equal(probabilities, model.predict(evaluation)))
            selected, candidate, policy = calibrate(evaluation, probabilities, 'y_event', CLASSES, event_folder, cfg, smoke=smoke)
            event_output = evaluation[META + ['y_event']].copy()
            for name, p in (('raw', probabilities), ('temperature', candidate), ('selected', selected)):
                for i, label in enumerate(CLASSES):
                    event_output[f'{name}_{label}'] = p[:, i]
            event_output.to_parquet(event_folder / 'predictions.parquet', index=False)
            output = evaluation[META].copy()
            output[PROBABILITIES] = selected
            output['family'], output['protocol_id'], output['data_version'] = family, 'A', dataset.run_id
            output['status'] = 'smoke_only' if smoke else 'ok'
            output['warnings'] = model.warnings(evaluation)
            output['event_calibration_route'] = policy['route']
            decisions[family] = {'event_calibration': policy, 'heads': {}}
            for head in HEADS:
                p, decision = train_head(rows, evaluation, family, head, destination / head, cfg, smoke, checks)
                decisions[family]['heads'][head] = decision
                output[head+'_status'], output[head+'_route'] = decision['status'], decision['route']
                if head == 'contact':
                    for label in ('weak', 'medium', 'hard'):
                        output['p_'+label+'_given_in_play'] = np.nan if p is None else p[:, HEADS[head].index(label)]
                        output['p_'+label+'_per_pitch'] = np.nan if p is None else selected[:, 4]*p[:, HEADS[head].index(label)]
                    if p is not None:
                        joint = joint_contact_probabilities(selected, p)
                        checks[family+'_contact_exclusive'] = bool(np.all(p[:, 0]+p[:, 2] <= 1+1e-12))
                        checks[family+'_joint_contact_coherent'] = bool(np.allclose(joint.sum(axis=1), selected[:, 4], atol=1e-12))
                elif head == 'groundball':
                    output['p_groundball_given_in_play'] = np.nan if p is None else p[:, 1]
                    output['p_groundball_per_pitch'] = np.nan if p is None else selected[:, 4]*p[:, 1]
                else:
                    output['p_chase_given_outside'] = np.nan if p is None else p[:, 1]
            all_output.append(output)
        predictions = pd.concat(all_output, ignore_index=True)
        probability_columns = [c for c in predictions if c.startswith('p_')]
        checks['joint_and_conditional_bounds'] = bool(all(predictions[c].dropna().between(0, 1).all() for c in probability_columns))
        checks['event_probabilities_sum_one'] = bool(np.allclose(predictions[PROBABILITIES].sum(axis=1), 1, atol=1e-6))
        checks['no_2026_output'] = bool(predictions.year.eq(2025).all())
        checks['unique_pitch_family_pairs'] = not predictions.duplicated(['pitch_uid', 'family']).any()
        predictions.to_parquet(folder / 'predictions.parquet', index=False)
        checks['output_roundtrip'] = predictions.equals(pd.read_parquet(folder / 'predictions.parquet'))
        write_json(folder / 'metrics.json', {'protocol_id': 'A', 'smoke': smoke, 'families': decisions,
                   'primary_reference': 'Pitching', 'review_is_independent_final_test': False,
                   'groundball_semantics': 'diagnostic_not_run_prevention_reward', 'chase_semantics': 'conditional_given_supplied_outside_zone'})
        write_json(folder / 'checks.json', {k: bool(v) for k, v in checks.items()})
        if not all(checks.values()):
            raise RuntimeError('F4 technical checks failed: '+', '.join(k for k,v in checks.items() if not v))
        dataset.assert_unchanged()
        promote = any(d['scientific_decision']=='promote' for family in decisions.values() for d in family['heads'].values())
        decision = 'inconclusive' if smoke else ('promote' if promote else 'retain_reference')
        manifest.update(status='verified', scientific_decision=decision)
        (folder / 'decision.md').write_text('# F4\n\nImplementaciÃ³n verified; decisiÃ³n '+decision+'.\n\n'
            'Ajuste de cabezas: 2024. Parada temprana: desarrollo 2025. Temperaturas: calibraciÃ³n 2025. '
            'RevisiÃ³n elige temperatura/identidad y contrasta cabezas con prevalencia. No se reajusta sobre revisiÃ³n.\n\n'
            'Cabezas experimentales usan prevalencia de entrenamiento; sin muestra se devuelven nulos. '
            '2026 sellado; F5 no iniciada. Sin scores ni xRunValue.\n', encoding='utf-8')
    except Exception as exc:
        manifest.update(status='blocked', error=f'{type(exc).__name__}: {exc}')
        write_json(folder / 'checks.json', {**{k: bool(v) for k,v in checks.items()}, 'technical_failure': False})
        (folder / 'decision.md').write_text('# F4 blocked\n\n'+manifest['error'], encoding='utf-8')
        raise
    finally:
        manifest.update(finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.perf_counter()-tick)
        manifest['artifact_hashes'] = {p.relative_to(folder).as_posix(): sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file() and p != folder/'manifest.json'}
        write_json(folder / 'manifest.json', manifest)
    print(json.dumps({'path': str(folder), 'status': manifest['status'], 'decision': decision,
                      'heads': {f: {h:d['status'] for h,d in v['heads'].items()} for f,v in decisions.items()}}, indent=2), flush=True)
    return folder
