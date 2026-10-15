"""F9 post-release: StuffV2 (derived physical features) vs B0/B1/F2-Stuff on 2025 partitions.

Lives outside modeling/ so release_lock.json keeps verifying the frozen F8 release.
2026 remains out of reach: dataset.load rejects 'test' for any phase other than F8,
and this phase declares the prior exposure instead of seeking a second evaluation.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import shutil
import sys
import time
import uuid

from modeling.baselines import CLASSES, EventBaseline
from modeling.cli import verify, write_json
from modeling.datasets import ROOT, META, ModelingDataset, ids_hash, join_pitches, pd, sha256_file
from modeling.metrics import (calibration_bins, multiclass_metrics, paired_bootstrap,
                              per_pitch_losses, write_calibration_svg)
from modeling.models import BACKEND_VERSION, StuffModel
from modeling.phase2 import verify_f1
from modeling.release import read, verify_release
from postrelease.stuff_v2 import (DERIVATION_ID, STUFF_V2, StuffV2Model, augment,
                                  fit_group_stats, permutation_importance_v2)
import numpy as np


def verify_f8(dataset):
    cfg = dataset.config
    if next(p for p in cfg['phases'] if p['id'] == 'F8')['status'] != 'verified':
        raise RuntimeError('F8 must be verified before post-release development')
    marker = dataset.root / 'artifacts/modeling/test_exposure.json'
    if not marker.exists():
        raise RuntimeError('F9 requires the F8 exposure record: run the frozen release first')
    exposure = read(marker)
    release = dataset.root / 'artifacts/modeling/releases' / cfg['F9']['release_reference']
    lock = verify_release(release)
    if lock['release_id'] != exposure['release_id']:
        raise RuntimeError('Exposure record does not match the referenced release')
    return release, lock, exposure


def verify_f2(dataset):
    cfg = dataset.config
    reference_id = cfg['F9']['f2_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', reference_id):
        raise ValueError('Invalid F2 reference ID')
    folder = dataset.root / 'artifacts/modeling' / reference_id / 'F2'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest['status'] != 'verified' or manifest['phase_id'] != 'F2' or manifest['smoke']
            or manifest['data_run'] != dataset.run_id or manifest['data_manifest_sha256'] != dataset.manifest_hash):
        raise RuntimeError('F2 must be a verified full run on pinned data')
    required = {'stuff/model.txt', 'stuff/preprocessing.json', 'selection.json',
                'predictions.parquet', 'metrics.json', 'checks.json', 'config.json',
                'cohort_manifest.json', 'B0.json', 'B1.json'}
    if not required.issubset(manifest['artifact_hashes']):
        raise RuntimeError('Incomplete F2 evidence')
    for name, digest in manifest['artifact_hashes'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise RuntimeError(f'F2 artifact integrity failure: {name}')
    checks = json.loads((folder / 'checks.json').read_text(encoding='utf-8'))
    if not checks or not all(value is True for value in checks.values()):
        raise RuntimeError('F2 technical checks did not pass')
    previous = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    for key in ('expected_data_run', 'primary_target', 'event_class_order', 'seed',
                'protocol_A', 'evaluation'):
        if cfg[key] != previous[key]:
            raise RuntimeError(f'F2 contract has changed: {key}')
    return folder, manifest


def select_stuff_v2(training, development, settings, seed, directory, smoke=False):
    trials = settings['candidates'][:1] if smoke else settings['candidates']
    if not 1 <= len(settings['candidates']) <= 12:
        raise ValueError('F9 permits at most 12 predeclared configurations')
    rounds = settings['smoke_rounds'] if smoke else settings['maximum_rounds']
    results = []
    for i, parameters in enumerate(trials):
        print(f'F9: fitting configuration {i+1}/{len(trials)} on 2024; selecting on development 2025', flush=True)
        model = StuffV2Model(seed, settings['threads']).fit(training, development, parameters,
                                                          rounds, settings['early_stopping_rounds'])
        candidate_id = f'candidate_{i+1:02}'
        model.save(directory / candidate_id)
        score = multiclass_metrics(development.y_event, model.predict(development), CLASSES)['multiclass_log_loss']
        results.append({'candidate_id': candidate_id, 'parameters': parameters,
                        'development_log_loss': score, 'best_iteration': model.metadata['best_iteration'],
                        'iterations_evaluated': model.metadata['iterations_evaluated']})
    selected = min(results, key=lambda row: (row['development_log_loss'], row['candidate_id']))
    return StuffV2Model.load(directory / selected['candidate_id']), {
        'selection_partition': 'development', 'selection_metric': 'multiclass_log_loss',
        'selected': selected, 'trials': results, 'smoke': smoke,
        'feature_set': DERIVATION_ID,
        'development_ids_sha256': ids_hash(development.pitch_uid.tolist()),
        'review_used_for_selection': False,
    }


def train_stuff_v2(experiment_id=None, smoke=False, root=ROOT):
    started, tick = datetime.now(timezone.utc), time.perf_counter()
    dataset = ModelingDataset(root)
    cfg, settings = dataset.config, dataset.config['F9']
    f1_folder, f1_reference = verify_f1(dataset)
    f2_folder, f2_reference = verify_f2(dataset)
    release_folder, release_lock, exposure = verify_f8(dataset)
    if settings['cohort_policy'] != 'f0_common_v1' or cfg['training']['backend'] != 'lightgbm==' + BACKEND_VERSION:
        raise ValueError('Unsupported cohort or backend policy')
    if len(settings['candidates']) > cfg['training']['maximum_initial_hyperparameter_configurations']:
        raise ValueError('Hyperparameter budget exceeded')
    experiment_id = experiment_id or started.strftime('f9-%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root / 'artifacts/modeling' / experiment_id / 'F9'
    folder.mkdir(parents=True, exist_ok=False)
    source_paths = sorted((dataset.root / 'postrelease').glob('*.py')) + sorted(
        (dataset.root / 'modeling').glob('*.py')) + [dataset.root / 'diablos_data.py']
    manifest = {
        'experiment_id': experiment_id, 'phase_id': 'F9', 'status': 'in_progress',
        'scientific_decision': 'not_applicable', 'protocol_id': 'A', 'target': 'y_event',
        'family': 'stuff', 'features': STUFF_V2, 'feature_set': DERIVATION_ID,
        'seed': cfg['seed'], 'smoke': smoke,
        'reference_model': 'B1', 'data_run': dataset.run_id,
        'data_manifest_sha256': dataset.manifest_hash,
        'data_output_hashes': dataset.manifest['outputs'], 'config_sha256': dataset.config_hash,
        'code_hashes': {str(p.relative_to(dataset.root)): sha256_file(p) for p in source_paths},
        'requirements_sha256': sha256_file(dataset.root / 'requirements-modeling.txt'),
        'document_sha256': sha256_file(dataset.root / cfg['document']),
        'dependency_F1': {'experiment_id': f1_reference['experiment_id'],
                          'manifest_sha256': sha256_file(f1_folder / 'manifest.json')},
        'dependency_F2': {'experiment_id': f2_reference['experiment_id'],
                          'manifest_sha256': sha256_file(f2_folder / 'manifest.json')},
        'dependency_F8': {'release': release_folder.name, 'release_id': release_lock['release_id'],
                          'release_lock_sha256': sha256_file(release_folder / 'release_lock.json')},
        'post_release_development': True,
        'test_previously_exposed': exposure,
        'test_accessed': False,
        'versions': {'python': platform.python_version(), **{name: importlib.metadata.version(name)
                     for name in ('pandas', 'numpy', 'pyarrow', 'duckdb', 'lightgbm', 'scipy')}},
        'python_executable': sys.executable, 'virtual_environment': sys.prefix != sys.base_prefix,
        'hardware': {'processor': platform.processor(), 'machine': platform.machine(),
                     'threads_used': settings['threads']},
        'started_utc': started.isoformat(),
        'denominator': 'F0 common eligible pitches; same development population as F2',
        'scope_note': 'Development after the final test was opened; phase_review 2025 informed earlier '
                      'decisions and is not an independent test. 2026 was not queried.',
    }
    write_json(folder / 'manifest.json', manifest)
    write_json(folder / 'config.json', cfg)
    checks = {}
    try:
        cohort = dataset.load(maximum=cfg['training']['smoke_target_max_pitches'] if smoke else None, phase='F9')
        checks.update(verify(cohort, dataset))
        try:
            dataset.load(partitions=['test'], phase='F9')
        except PermissionError:
            checks['test_partition_rejected_for_f9'] = True
        else:
            checks['test_partition_rejected_for_f9'] = False
        rows = join_pitches(cohort['aligned']['stuff'], cohort['context']).sort_values('pitch_uid').reset_index(drop=True)
        training = rows.loc[rows.partition.eq('train')].copy()
        development = rows.loc[rows.partition.eq('development')].copy()
        checks['train_game_folds_intact'] = bool(training.groupby('game_anon_id').game_cv_fold.nunique().eq(1).all())
        checks['train_folds_present'] = set(training.game_cv_fold) == set(range(5))
        if not smoke:
            checks['same_F2_cohort'] = ids_hash(rows.pitch_uid.tolist()) == f2_reference['cohort']['common_ids_sha256']
        if not all(checks.values()):
            raise RuntimeError('F9 cohort checks failed before training')
        manifest['cohort'] = {'common_rows': len(rows), 'common_ids_sha256': ids_hash(rows.pitch_uid.tolist()),
                              'by_partition': {p: {'n_pitches': len(g), 'n_games': int(g.game_anon_id.nunique()),
                                                   'ids_sha256': ids_hash(g.pitch_uid.tolist())} for p, g in rows.groupby('partition')},
                              'training_fold_sizes': {str(k): int(v) for k, v in training.groupby('game_cv_fold').size().items()},
                              'exclusions': cohort['exclusions']}
        write_json(folder / 'cohort_manifest.json', manifest['cohort'])
        rows[META].to_parquet(folder / 'cohort.parquet', index=False)
        selected, selection = select_stuff_v2(training, development, settings, cfg['seed'], folder / 'candidates', smoke)
        write_json(folder / 'selection.json', selection)
        selected.save(folder / 'stuff_v2')
        model = StuffV2Model.load(folder / 'stuff_v2')
        checks['exact_v2_features'] = model.booster.feature_name() == STUFF_V2
        checks['encoder_fitted_only_on_training'] = all(
            model.vocabularies[c] == sorted(training[c].unique().tolist()) for c in model.vocabularies)
        checks['z_stats_fitted_only_on_training'] = all(
            set(model.group_stats[c]['by_type']).issubset(set(training.auto_pitch_type.unique()))
            for c in model.group_stats)
        checks['derivation_deterministic'] = augment(rows.head(512), model.group_stats).equals(
            augment(rows.head(512), model.group_stats))
        print('F9: selected model frozen; computing permutation importance on development only', flush=True)
        importance = permutation_importance_v2(model, development, 1 if smoke else settings['permutation_repeats'], cfg['seed'])
        write_json(folder / 'permutation_importance.json', importance)
        pd.DataFrame([{k: v for k, v in row.items() if k != 'deltas'} for row in importance]).to_csv(
            folder / 'permutation_importance.csv', index=False)
        evaluation = rows.loc[~rows.partition.eq('train')].copy()
        physical = model.predict(evaluation)
        original = selected.predict(evaluation)
        difference = float(np.max(np.abs(physical - original)))
        checks['reload_prediction_tolerance'] = difference <= cfg['numerical_checks']['reload_prediction_atol_cpu']
        probe = evaluation.iloc[:512].copy()
        expected = model.predict(probe)
        for column in ('balls', 'strikes', 'plate_loc_height', 'plate_loc_side', 'batter_side',
                       'altitude_category', 'pitch_uid', 'game_anon_id', 'pitcher_anon_id', 'year', 'y_event'):
            changed = probe.copy()
            changed[column] = 'ignored_context'
            checks['invariant_' + column] = bool(np.array_equal(expected, model.predict(changed)))
        missing = probe.copy(); missing.loc[missing.index[0], 'rel_speed'] = np.nan
        try:
            model.predict(missing)
        except ValueError:
            checks['missing_physics_rejected'] = True
        else:
            checks['missing_physics_rejected'] = False
        unknown = probe.copy(); unknown['auto_pitch_type'] = '__unknown__'
        checks['unseen_category_finite_with_warning'] = bool(
            np.isfinite(model.predict(unknown)).all()
            and all('unknown_category' in w for w in model.warnings(unknown)))
        print('F9: verifying deterministic refit of selected configuration (no additional search)', flush=True)
        replay = StuffV2Model(cfg['seed'], settings['threads']).fit(
            training, development, selection['selected']['parameters'],
            settings['smoke_rounds'] if smoke else settings['maximum_rounds'], settings['early_stopping_rounds'])
        replay_difference = float(np.max(np.abs(physical - replay.predict(evaluation))))
        checks['deterministic_refit'] = replay_difference <= cfg['numerical_checks']['reload_prediction_atol_cpu']
        write_json(folder / 'reproducibility.json', {'reload_max_abs_difference': difference,
                   'refit_max_abs_difference': replay_difference, 'n_predictions_compared': len(evaluation),
                   'tolerance': cfg['numerical_checks']['reload_prediction_atol_cpu'],
                   'selection_not_repeated': True, 'refit_same_configuration': selection['selected']['candidate_id']})
        output, metrics, curves, losses = [], [], [], {}
        columns = ['p_' + label for label in CLASSES]
        f1_predictions = None if smoke else pd.read_parquet(f1_folder / 'predictions.parquet')
        f2_predictions = None if smoke else pd.read_parquet(f2_folder / 'predictions.parquet')
        f2_model = StuffModel.load(f2_folder / 'stuff')
        for name in ('B0', 'B1', 'Stuff', 'StuffV2'):
            if name == 'StuffV2':
                probabilities, routes = physical, np.full(len(evaluation), 'physical_derived')
                model_hash = sha256_file(folder / 'stuff_v2/model.txt')
            elif name == 'Stuff':
                probabilities = f2_model.predict(evaluation)
                routes = np.full(len(evaluation), 'physical')
                model_hash = sha256_file(f2_folder / 'stuff/model.txt')
                if not smoke:
                    past = f2_predictions.loc[f2_predictions.model.eq('Stuff'), ['pitch_uid'] + columns]
                    aligned = join_pitches(evaluation[['pitch_uid']], past)
                    checks['Stuff_matches_F2_probabilities'] = len(aligned) == len(evaluation) and bool(
                        np.array_equal(probabilities, aligned[columns].to_numpy()))
            else:
                if smoke:
                    baseline = EventBaseline(name, cfg['event_class_order'],
                                             cfg['training']['baseline_global_pseudocount_per_class'],
                                             cfg['training']['baseline_group_prior_strength']).fit(training)
                    baseline.save(folder / (name + '.json'))
                else:
                    shutil.copyfile(f1_folder / 'models' / (name + '.json'), folder / (name + '.json'))
                baseline = EventBaseline.load(folder / (name + '.json'))
                checks[name + '_same_training_ids'] = baseline.state['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
                probabilities, routes = baseline.predict(evaluation[['balls', 'strikes', 'auto_pitch_type']])
                model_hash = sha256_file(folder / (name + '.json'))
                if not smoke:
                    past = f1_predictions.loc[f1_predictions.model.eq(name), ['pitch_uid'] + columns]
                    aligned = join_pitches(evaluation[['pitch_uid']], past)
                    checks[name + '_matches_F1_probabilities'] = len(aligned) == len(evaluation) and bool(
                        np.array_equal(probabilities, aligned[columns].to_numpy()))
            prediction = evaluation[META + ['y_event']].copy()
            prediction[columns] = probabilities
            prediction['model'], prediction['route'] = name, routes
            prediction['status'] = 'smoke_only' if smoke else 'ok'
            prediction['warnings'] = model.warnings(evaluation) if name == 'StuffV2' else ''
            prediction['data_version'], prediction['protocol_id'], prediction['model_version'] = dataset.run_id, 'A', model_hash
            output.append(prediction)
            for part in ('development', 'calibration', 'phase_review'):
                mask = evaluation.partition.eq(part).to_numpy()
                group, values = evaluation.loc[mask], probabilities[mask]
                result = multiclass_metrics(group.y_event, values, CLASSES, cfg['numerical_checks']['log_loss_clipping_epsilon'])
                result.update(model=name, partition=part, n_games=int(group.game_anon_id.nunique()),
                              ids_sha256=ids_hash(group.pitch_uid.tolist()))
                metrics.append(result)
                curves.extend(dict(row, model=name, partition=part)
                              for row in calibration_bins(group.y_event, values, CLASSES))
                if part == 'phase_review':
                    loss, _ = per_pitch_losses(group.y_event, values, CLASSES)
                    losses[name] = group[['pitch_uid', 'game_anon_id', 'y_event']].assign(loss=loss)
        comparisons = {f'StuffV2_vs_{name}': paired_bootstrap(
                           losses[name], losses['StuffV2'],
                           cfg['evaluation']['bootstrap_smoke' if smoke else 'bootstrap_full'], cfg['seed'],
                           cfg['evaluation']['bootstrap_confidence'],
                           cfg['evaluation']['promotion_min_relative_log_loss_reduction'], smoke)
                       for name in ('B0', 'B1', 'Stuff')}
        decision = 'inconclusive' if smoke else (
            'promote' if comparisons['StuffV2_vs_B1']['decision'] == 'promote' else 'retain_reference')
        predictions = pd.concat(output, ignore_index=True)
        checks['unique_pitch_model_pairs'] = not predictions.duplicated(['pitch_uid', 'model']).any()
        checks['only_2025_predictions'] = bool(predictions.year.eq(2025).all())
        checks['finite_metrics'] = bool(np.isfinite(
            [m[k] for m in metrics for k in ('multiclass_log_loss', 'multiclass_brier_sum_over_classes')]).all())
        predictions.to_parquet(folder / 'predictions.parquet', index=False)
        checks['predictions_roundtrip'] = predictions.equals(pd.read_parquet(folder / 'predictions.parquet'))
        pd.DataFrame(curves).to_csv(folder / 'calibration.csv', index=False)
        for part in ('development', 'calibration', 'phase_review'):
            write_calibration_svg(folder / f'calibration_{part}.svg', curves, part, CLASSES,
                                  colors={'B0': '#475569', 'B1': '#2563eb', 'Stuff': '#94a3b8',
                                          'StuffV2': '#c2410c'}, phase='F9')
        write_json(folder / 'metrics.json', {'status': 'smoke_only' if smoke else 'evaluated',
                   'protocol_id': 'A', 'target': 'y_event', 'data_run': dataset.run_id, 'seed': cfg['seed'],
                   'denominator': manifest['denominator'], 'class_order': list(CLASSES), 'metrics': metrics,
                   'comparisons': comparisons, 'scientific_decision': decision,
                   'review_is_independent_final_test': False,
                   'post_release_development': True,
                   'release_unchangeable_test_exposed': True})
        write_json(folder / 'checks.json', {key: bool(value) for key, value in checks.items()})
        if not all(checks.values()):
            raise RuntimeError('F9 checks failed: ' + ', '.join(k for k, v in checks.items() if not v))
        dataset.assert_unchanged()
        manifest.update(status='verified', scientific_decision=decision,
                        selected_candidate=selection['selected']['candidate_id'],
                        best_iteration=selection['selected']['best_iteration'])
        (folder / 'decision.md').write_text(
            '# Decisión F9\n\nImplementación: `verified`. Decisión científica: `' + decision + '`.\n\n'
            'Desarrollo posterior a la apertura del test 2026 (release `'
            + release_lock['release_id'] + '`); la exposición quedó declarada y 2026 no se consultó.\n\n'
            'Selección y parada temprana solo en desarrollo 2025; ajuste físico, vocabularios y '
            'estadísticos por tipo solo en 2024. Candidato `' + DERIVATION_ID + '`.\n\n'
            + ('StuffV2 supera la regla de promoción frente a B1 en phase_review: evidencia para una '
               'futura versión del índice, sin reabrir el release congelado.\n\n'
               if decision == 'promote' else
               'B1 permanece como referencia; StuffV2 no alcanzó la regla de promoción. '
               'El resultado se reporta, no se ajusta hasta ganar.\n\n')
            + 'phase_review 2025 ya informó decisiones anteriores: no es un test independiente.\n\n'
            + ('Smoke no produce conclusión científica.\n' if smoke else '')
            + 'El release F8 permanece intacto y verificable; ninguna comparación de F9 lo modifica.\n',
            encoding='utf-8')
    except Exception as exc:
        manifest.update(status='blocked', error=f'{type(exc).__name__}: {exc}')
        write_json(folder / 'checks.json', {**{k: bool(v) for k, v in checks.items()},
                                            'technical_failure': False, 'error': manifest['error']})
        (folder / 'decision.md').write_text('# F9 blocked\n\nNo avanzar.\n\n' + manifest['error'], encoding='utf-8')
        raise
    finally:
        manifest['finished_utc'], manifest['elapsed_seconds'] = datetime.now(timezone.utc).isoformat(), time.perf_counter() - tick
        manifest['artifact_hashes'] = {p.relative_to(folder).as_posix(): sha256_file(p)
                                       for p in sorted(folder.rglob('*')) if p.is_file() and p != folder / 'manifest.json'}
        write_json(folder / 'manifest.json', manifest)
    print(json.dumps({'path': str(folder), 'status': manifest['status'], 'decision': decision,
                      'selected': manifest['selected_candidate'], 'best_iteration': manifest['best_iteration']}, indent=2))
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-id')
    parser.add_argument('--smoke', action='store_true',
                        help='Small flow check: 1 candidate, reduced rounds and bootstrap')
    args = parser.parse_args()
    try:
        train_stuff_v2(args.experiment_id, args.smoke)
    except (ValueError, RuntimeError, PermissionError, FileExistsError) as exc:
        parser.exit(1, f'F9 blocked: {exc}\n')


if __name__ == '__main__':
    main()
