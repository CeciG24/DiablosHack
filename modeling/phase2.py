"""F2: physical Stuff, development-only selection, frozen F1 comparisons."""
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
from modeling.datasets import ROOT, META, STUFF, ModelingDataset, ids_hash, join_pitches, pd, sha256_file
from modeling.metrics import (calibration_bins, multiclass_metrics, paired_bootstrap,
                              per_pitch_losses, write_calibration_svg)
from modeling.models import BACKEND_VERSION, StuffModel, permutation_importance
from modeling.phase1 import verify_f0
import numpy as np


def verify_f1(dataset):
    verify_f0(dataset)
    cfg = dataset.config
    if next(p for p in cfg['phases'] if p['id'] == 'F1')['status'] != 'verified':
        raise RuntimeError('F1 must be verified')
    reference_id = cfg['F2']['f1_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', reference_id):
        raise ValueError('Invalid F1 reference ID')
    folder = dataset.root / 'artifacts/modeling' / reference_id / 'F1'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest['status'] != 'verified' or manifest['phase_id'] != 'F1' or manifest['smoke']
            or manifest['data_run'] != dataset.run_id or manifest['data_manifest_sha256'] != dataset.manifest_hash):
        raise RuntimeError('F1 must be a verified full run on pinned data')
    required = {'models/B0.json', 'models/B1.json', 'predictions.parquet', 'config.json', 'checks.json', 'cohort_manifest.json'}
    if not required.issubset(manifest['artifact_hashes']):
        raise RuntimeError('Incomplete F1 evidence')
    for name, digest in manifest['artifact_hashes'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise RuntimeError(f'F1 artifact integrity failure: {name}')
    checks = json.loads((folder / 'checks.json').read_text(encoding='utf-8'))
    if not checks or not all(value is True for value in checks.values()):
        raise RuntimeError('F1 technical checks did not pass')
    previous = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    for key in ('expected_data_run', 'primary_target', 'event_class_order', 'seed', 'protocol_A', 'F1', 'evaluation'):
        if cfg[key] != previous[key]:
            raise RuntimeError(f'F1 contract has changed: {key}')
    for key in ('baseline_global_pseudocount_per_class', 'baseline_group_prior_strength'):
        if cfg['training'][key] != previous['training'][key]:
            raise RuntimeError('Baseline smoothing changed')
    return folder, manifest


def select_stuff(training, development, settings, seed, directory, smoke=False):
    trials = settings['candidates'][:1] if smoke else settings['candidates']
    if not 1 <= len(settings['candidates']) <= 12:
        raise ValueError('F2 permits at most 12 predeclared configurations')
    rounds = settings['smoke_rounds'] if smoke else settings['maximum_rounds']
    results = []
    for i, parameters in enumerate(trials):
        print(f'F2: fitting configuration {i+1}/{len(trials)} on 2024; selecting on development 2025', flush=True)
        model = StuffModel(seed, settings['threads']).fit(training, development, parameters,
                                                        rounds, settings['early_stopping_rounds'])
        candidate_id = f'candidate_{i+1:02}'
        model.save(directory / candidate_id)
        score = multiclass_metrics(development.y_event, model.predict(development), CLASSES)['multiclass_log_loss']
        results.append({'candidate_id': candidate_id, 'parameters': parameters,
                        'development_log_loss': score, 'best_iteration': model.metadata['best_iteration'],
                        'iterations_evaluated': model.metadata['iterations_evaluated']})
    selected = min(results, key=lambda row: (row['development_log_loss'], row['candidate_id']))
    return StuffModel.load(directory / selected['candidate_id']), {
        'selection_partition': 'development', 'selection_metric': 'multiclass_log_loss',
        'selected': selected, 'trials': results, 'smoke': smoke,
        'development_ids_sha256': ids_hash(development.pitch_uid.tolist()),
        'review_used_for_selection': False,
    }


def train_stuff(experiment_id=None, smoke=False, root=ROOT):
    started, tick = datetime.now(timezone.utc), time.perf_counter()
    dataset = ModelingDataset(root)
    cfg, settings = dataset.config, dataset.config['F2']
    reference_folder, reference = verify_f1(dataset)
    if settings['cohort_policy'] != 'f0_common_v1' or cfg['training']['backend'] != 'lightgbm=='+BACKEND_VERSION:
        raise ValueError('Unsupported cohort or backend policy')
    if len(settings['candidates']) > cfg['training']['maximum_initial_hyperparameter_configurations']:
        raise ValueError('Hyperparameter budget exceeded')
    experiment_id = experiment_id or started.strftime('f2-%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root / 'artifacts/modeling' / experiment_id / 'F2'
    folder.mkdir(parents=True, exist_ok=False)
    source_paths = sorted((dataset.root / 'modeling').glob('*.py')) + [dataset.root / 'diablos_data.py']
    manifest = {
        'experiment_id': experiment_id, 'phase_id': 'F2', 'status': 'in_progress',
        'scientific_decision': 'not_applicable', 'protocol_id': 'A', 'target': 'y_event',
        'family': 'stuff', 'features': STUFF, 'seed': cfg['seed'], 'smoke': smoke,
        'reference_model': 'B1', 'data_run': dataset.run_id, 'data_manifest_sha256': dataset.manifest_hash,
        'data_output_hashes': dataset.manifest['outputs'], 'config_sha256': dataset.config_hash,
        'code_hashes': {str(p.relative_to(dataset.root)): sha256_file(p) for p in source_paths},
        'requirements_sha256': sha256_file(dataset.root / 'requirements-modeling.txt'),
        'document_sha256': sha256_file(dataset.root / cfg['document']),
        'dependency_F1': {'experiment_id': reference['experiment_id'], 'manifest_sha256': sha256_file(reference_folder / 'manifest.json')},
        'versions': {'python': platform.python_version(), **{name: importlib.metadata.version(name)
                     for name in ('pandas', 'numpy', 'pyarrow', 'duckdb', 'lightgbm', 'scipy')}},
        'python_executable': sys.executable, 'virtual_environment': sys.prefix != sys.base_prefix,
        'hardware': {'processor': platform.processor(), 'machine': platform.machine(), 'threads_used': settings['threads']},
        'started_utc': started.isoformat(), 'test_accessed': False, 'test_quality_previously_profiled': True,
        'denominator': 'F0 common eligible pitches; same training and evaluation population as F1',
        'baseline_policy': 'refit on smoke training only' if smoke else 'reuse frozen F1 B0/B1 without refitting',
    }
    write_json(folder / 'manifest.json', manifest)
    write_json(folder / 'config.json', cfg)
    checks = {}
    try:
        cohort = dataset.load(maximum=cfg['training']['smoke_target_max_pitches'] if smoke else None, phase='F2')
        checks.update(verify(cohort, dataset))
        rows = join_pitches(cohort['aligned']['stuff'], cohort['context']).sort_values('pitch_uid').reset_index(drop=True)
        training = rows.loc[rows.partition.eq('train')].copy()
        development = rows.loc[rows.partition.eq('development')].copy()
        checks['train_game_folds_intact'] = bool(training.groupby('game_anon_id').game_cv_fold.nunique().eq(1).all())
        checks['train_folds_present'] = set(training.game_cv_fold) == set(range(5))
        if not smoke:
            checks['same_F1_cohort'] = ids_hash(rows.pitch_uid.tolist()) == reference['cohort']['common_ids_sha256']
        if not all(checks.values()):
            raise RuntimeError('F2 cohort checks failed before training')
        manifest['cohort'] = {'common_rows': len(rows), 'common_ids_sha256': ids_hash(rows.pitch_uid.tolist()),
                              'by_partition': {p: {'n_pitches': len(g), 'n_games': int(g.game_anon_id.nunique()),
                                                   'ids_sha256': ids_hash(g.pitch_uid.tolist())} for p, g in rows.groupby('partition')},
                              'training_fold_sizes': {str(k): int(v) for k, v in training.groupby('game_cv_fold').size().items()},
                              'exclusions': cohort['exclusions']}
        write_json(folder / 'cohort_manifest.json', manifest['cohort'])
        rows[META].to_parquet(folder / 'cohort.parquet', index=False)
        selected, selection = select_stuff(training, development, settings, cfg['seed'], folder / 'candidates', smoke)
        # Persist selection before producing any review predictions or comparisons.
        write_json(folder / 'selection.json', selection)
        selected.save(folder / 'stuff')
        model = StuffModel.load(folder / 'stuff')
        checks['exact_physical_features'] = model.booster.feature_name() == STUFF
        checks['encoder_fitted_only_on_training'] = all(model.vocabularies[c] == sorted(training[c].unique().tolist()) for c in model.vocabularies)
        print('F2: selected model frozen; computing permutation importance on development only', flush=True)
        importance = permutation_importance(model, development, 1 if smoke else settings['permutation_repeats'], cfg['seed'])
        write_json(folder / 'permutation_importance.json', importance)
        pd.DataFrame([{k: v for k, v in row.items() if k != 'deltas'} for row in importance]).to_csv(folder / 'permutation_importance.csv', index=False)
        evaluation = rows.loc[~rows.partition.eq('train')].copy()
        physical = model.predict(evaluation)
        original = selected.predict(evaluation)
        difference = float(np.max(np.abs(physical-original)))
        checks['reload_prediction_tolerance'] = difference <= cfg['numerical_checks']['reload_prediction_atol_cpu']
        probe = evaluation.iloc[:512].copy()
        expected = model.predict(probe)
        for column in ('balls', 'strikes', 'plate_loc_height', 'plate_loc_side', 'batter_side', 'altitude_category', 'pitch_uid', 'game_anon_id', 'pitcher_anon_id', 'year', 'y_event'):
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
        checks['unseen_category_finite_with_warning'] = bool(np.isfinite(model.predict(unknown)).all() and all('unknown_category' in w for w in model.warnings(unknown)))
        print('F2: verifying deterministic refit of selected configuration (no additional search)', flush=True)
        replay = StuffModel(cfg['seed'], settings['threads']).fit(training, development,
                  selection['selected']['parameters'], settings['smoke_rounds'] if smoke else settings['maximum_rounds'], settings['early_stopping_rounds'])
        replay_difference = float(np.max(np.abs(physical-replay.predict(evaluation))))
        checks['deterministic_refit'] = replay_difference <= cfg['numerical_checks']['reload_prediction_atol_cpu']
        write_json(folder / 'reproducibility.json', {'reload_max_abs_difference': difference,
                   'refit_max_abs_difference': replay_difference, 'n_predictions_compared': len(evaluation),
                   'tolerance': cfg['numerical_checks']['reload_prediction_atol_cpu'],
                   'selection_not_repeated': True, 'refit_same_configuration': selection['selected']['candidate_id']})
        output, metrics, curves, losses = [], [], [], {}
        columns = ['p_' + label for label in CLASSES]
        approved_predictions = None if smoke else pd.read_parquet(reference_folder / 'predictions.parquet')
        for name in ('B0', 'B1', 'Stuff'):
            if name == 'Stuff':
                probabilities, routes = physical, np.full(len(evaluation), 'physical')
                model_hash = sha256_file(folder / 'stuff/model.txt')
            else:
                if smoke:
                    baseline = EventBaseline(name, cfg['event_class_order'], cfg['training']['baseline_global_pseudocount_per_class'], cfg['training']['baseline_group_prior_strength']).fit(training)
                    baseline.save(folder / (name + '.json'))
                else:
                    shutil.copyfile(reference_folder / 'models' / (name+'.json'), folder / (name+'.json'))
                baseline = EventBaseline.load(folder / (name+'.json'))
                checks[name + '_same_training_ids'] = baseline.state['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
                probabilities, routes = baseline.predict(evaluation[['balls', 'strikes', 'auto_pitch_type']])
                model_hash = sha256_file(folder / (name+'.json'))
                if not smoke:
                    past = approved_predictions.loc[approved_predictions.model.eq(name), ['pitch_uid']+columns]
                    aligned = join_pitches(evaluation[['pitch_uid']], past)
                    checks[name + '_matches_F1_probabilities'] = len(aligned) == len(evaluation) and bool(np.array_equal(probabilities, aligned[columns].to_numpy()))
            prediction = evaluation[META+['y_event']].copy()
            prediction[columns] = probabilities
            prediction['model'], prediction['route'] = name, routes
            prediction['status'] = 'smoke_only' if smoke else 'ok'
            prediction['warnings'] = model.warnings(evaluation) if name == 'Stuff' else ''
            prediction['data_version'], prediction['protocol_id'], prediction['model_version'] = dataset.run_id, 'A', model_hash
            output.append(prediction)
            for part in ('development', 'calibration', 'phase_review'):
                mask = evaluation.partition.eq(part).to_numpy()
                group, values = evaluation.loc[mask], probabilities[mask]
                result = multiclass_metrics(group.y_event, values, CLASSES, cfg['numerical_checks']['log_loss_clipping_epsilon'])
                result.update(model=name, partition=part, n_games=int(group.game_anon_id.nunique()), ids_sha256=ids_hash(group.pitch_uid.tolist()))
                metrics.append(result)
                curves.extend(dict(row, model=name, partition=part) for row in calibration_bins(group.y_event, values, CLASSES))
                if part == 'phase_review':
                    loss, _ = per_pitch_losses(group.y_event, values, CLASSES)
                    losses[name] = group[['pitch_uid', 'game_anon_id', 'y_event']].assign(loss=loss)
        comparisons = {f'Stuff_vs_{name}': paired_bootstrap(losses[name], losses['Stuff'],
                           cfg['evaluation']['bootstrap_smoke' if smoke else 'bootstrap_full'], cfg['seed'],
                           cfg['evaluation']['bootstrap_confidence'], cfg['evaluation']['promotion_min_relative_log_loss_reduction'], smoke)
                       for name in ('B0', 'B1')}
        decision = 'inconclusive' if smoke else ('promote' if comparisons['Stuff_vs_B1']['decision'] == 'promote' else 'retain_reference')
        predictions = pd.concat(output, ignore_index=True)
        checks['unique_pitch_model_pairs'] = not predictions.duplicated(['pitch_uid', 'model']).any()
        checks['only_2025_predictions'] = bool(predictions.year.eq(2025).all())
        checks['finite_metrics'] = bool(np.isfinite([m[k] for m in metrics for k in ('multiclass_log_loss', 'multiclass_brier_sum_over_classes')]).all())
        predictions.to_parquet(folder / 'predictions.parquet', index=False)
        checks['predictions_roundtrip'] = predictions.equals(pd.read_parquet(folder / 'predictions.parquet'))
        pd.DataFrame(curves).to_csv(folder / 'calibration.csv', index=False)
        for part in ('development', 'calibration', 'phase_review'):
            write_calibration_svg(folder / f'calibration_{part}.svg', curves, part, CLASSES,
                                  colors={'B0': '#475569', 'B1': '#2563eb', 'Stuff': '#c2410c'}, phase='F2')
        write_json(folder / 'metrics.json', {'status': 'smoke_only' if smoke else 'evaluated',
                   'protocol_id': 'A', 'target': 'y_event', 'data_run': dataset.run_id, 'seed': cfg['seed'],
                   'denominator': manifest['denominator'], 'class_order': list(CLASSES), 'metrics': metrics,
                   'comparisons': comparisons, 'scientific_decision': decision, 'review_is_independent_final_test': False})
        write_json(folder / 'checks.json', {key: bool(value) for key, value in checks.items()})
        if not all(checks.values()):
            raise RuntimeError('F2 checks failed: '+', '.join(k for k,v in checks.items() if not v))
        dataset.assert_unchanged()
        manifest.update(status='verified', scientific_decision=decision,
                        selected_candidate=selection['selected']['candidate_id'],
                        best_iteration=selection['selected']['best_iteration'])
        (folder / 'decision.md').write_text(
            '# Decisión F2\n\nImplementación: `verified`. Decisión científica: `' + decision + '`.\n\n'
            'Selección y parada temprana solo en desarrollo 2025. Ajuste físico y vocabularios solo en 2024.\n\n'
            + ('Stuff supera la regla de promoción frente a B1.\n\n' if decision == 'promote' else 'B1 permanece como referencia; Stuff se conserva como candidato diagnóstico.\n\n')
            + 'No superar un baseline contextual no demuestra ausencia de valor de las variables físicas.\n\n'
            + ('Smoke no habilita F3 por sí solo.\n' if smoke else 'F3 habilitada tras las pruebas de regresión; no se inicia automáticamente.\n')
            + '\n2026 sigue sellado. No hay scores, xRunValue ni calibradores ajustados.\n', encoding='utf-8')
    except Exception as exc:
        manifest.update(status='blocked', error=f'{type(exc).__name__}: {exc}')
        write_json(folder / 'checks.json', {**{k: bool(v) for k,v in checks.items()}, 'technical_failure': False, 'error': manifest['error']})
        (folder / 'decision.md').write_text('# F2 blocked\n\nNo avanzar.\n\n'+manifest['error'], encoding='utf-8')
        raise
    finally:
        manifest['finished_utc'], manifest['elapsed_seconds'] = datetime.now(timezone.utc).isoformat(), time.perf_counter()-tick
        manifest['artifact_hashes'] = {p.relative_to(folder).as_posix(): sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file() and p != folder/'manifest.json'}
        write_json(folder / 'manifest.json', manifest)
    print(json.dumps({'path': str(folder), 'status': manifest['status'], 'decision': decision,
                      'selected': manifest['selected_candidate'], 'best_iteration': manifest['best_iteration']}, indent=2))
    return folder
