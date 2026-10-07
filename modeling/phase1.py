"""Train, persist and evaluate F1 on the fixed F0 common cohort."""
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
import re
import sys
import time
import uuid

from modeling.baselines import CLASSES, EventBaseline
from modeling.cli import verify, write_json
from modeling.datasets import ROOT, META, ModelingDataset, ids_hash, join_pitches, pd, sha256_file
from modeling.metrics import (calibration_bins, multiclass_metrics, paired_bootstrap,
                              per_pitch_losses, validate_probabilities, write_calibration_svg)
import numpy as np


def verify_f0(dataset):
    config = dataset.config
    if next(p for p in config['phases'] if p['id'] == 'F0')['status'] != 'verified':
        raise RuntimeError('F0 is not verified')
    reference_id = config['F1']['f0_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', reference_id):
        raise ValueError('Invalid F0 reference ID')
    folder = dataset.root / 'artifacts/modeling' / reference_id / 'F0'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest['status'] != 'verified' or manifest['phase_id'] != 'F0' or
            manifest['data_run'] != dataset.run_id or manifest['data_manifest_sha256'] != dataset.manifest_hash or
            manifest['sampling']['maximum_pitches'] is not None):
        raise RuntimeError('F0 dependency is not an approved full run on the pinned data')
    required = {'config.json', 'cohort_manifest.json', 'assignments.parquet', 'checks.json', 'predictions.parquet'}
    if not required.issubset(manifest['artifact_hashes']):
        raise RuntimeError('Incomplete F0 evidence')
    for name, digest in manifest['artifact_hashes'].items():
        path = folder / name
        if path.resolve().parent != folder.resolve() or sha256_file(path) != digest:
            raise RuntimeError(f'F0 artifact integrity failure: {name}')
    checks = json.loads((folder / 'checks.json').read_text(encoding='utf-8'))
    if not checks or not all(value is True for value in checks.values()):
        raise RuntimeError('F0 checks did not pass')
    previous = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    for field in ('expected_data_run', 'primary_target', 'event_class_order', 'seed', 'protocol_A'):
        if previous[field] != config[field]:
            raise RuntimeError(f'F0 configuration no longer matches: {field}')
    if config['F1']['cohort_policy'] != 'f0_common_v1' or tuple(config['event_class_order']) != CLASSES:
        raise ValueError('Unsupported F1 cohort or class policy')
    if config['F1']['fallback'] != 'global_B0' or config['F1']['reference_model'] != 'B1':
        raise ValueError('Unsupported F1 fallback or reference')
    return manifest, {'experiment_id': reference_id, 'manifest_sha256': sha256_file(folder / 'manifest.json')}


def train_baselines(experiment_id=None, smoke=False, root=ROOT):
    started, tick = datetime.now(timezone.utc), time.perf_counter()
    dataset = ModelingDataset(root)
    cfg = dataset.config
    approved, dependency = verify_f0(dataset)
    experiment_id = experiment_id or started.strftime('f1-%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root / 'artifacts/modeling' / experiment_id / 'F1'
    folder.mkdir(parents=True, exist_ok=False)
    source_paths = sorted((dataset.root / 'modeling').glob('*.py')) + [dataset.root / 'diablos_data.py']
    manifest = {
        'experiment_id': experiment_id, 'phase_id': 'F1', 'status': 'in_progress',
        'scientific_decision': 'not_applicable', 'protocol_id': 'A', 'target': 'y_event',
        'models': ['B0', 'B1', 'B2'], 'reference_model': 'B1',
        'prediction_kind': 'fitted_baseline_smoke_only' if smoke else 'fitted_baseline',
        'seed': cfg['seed'], 'started_utc': started.isoformat(),
        'data_run': dataset.run_id, 'data_manifest_sha256': dataset.manifest_hash,
        'data_output_hashes': dataset.manifest['outputs'], 'config_sha256': dataset.config_hash,
        'code_hashes': {str(p.relative_to(dataset.root)): sha256_file(p) for p in source_paths},
        'document_sha256': sha256_file(dataset.root / cfg['document']), 'dependency_F0': dependency,
        'versions': {'python': platform.python_version(), **{name: importlib.metadata.version(name)
                     for name in ('pandas', 'numpy', 'pyarrow', 'duckdb')}},
        'python_executable': sys.executable, 'virtual_environment': sys.prefix != sys.base_prefix,
        'smoke': smoke, 'maximum_pitches': cfg['training']['smoke_target_max_pitches'] if smoke else None,
        'test_accessed': False, 'test_quality_previously_profiled': True,
        'fit_policy': '2024/train only; fixed pseudocount and prior; no tuning or calibration',
        'cohort_policy': cfg['F1']['cohort_policy'],
        'denominator': 'F0 common eligible pitches for stuff/location/pitching; non-null y_event',
    }
    write_json(folder / 'manifest.json', manifest)
    write_json(folder / 'config.json', cfg)
    checks = {}
    try:
        cohort = dataset.load(maximum=manifest['maximum_pitches'], phase='F1')
        checks.update(verify(cohort, dataset))
        # Count is joined by ID, never appended to the physical feature matrix.
        base = cohort['aligned']['stuff'][META + ['auto_pitch_type', 'y_event']]
        rows = join_pitches(base, cohort['context']).sort_values('pitch_uid').reset_index(drop=True)
        checks['context_join_preserves_population'] = len(rows) == len(base)
        if not smoke:
            checks['matches_approved_F0_cohort'] = ids_hash(rows.pitch_uid.tolist()) == approved['cohort']['common_ids_sha256']
        training = rows.loc[rows.partition.eq('train')].copy()
        evaluation = rows.loc[rows.partition.ne('train')].copy()
        checks['fit_2024_only'] = bool(len(training) and training.year.eq(2024).all())
        checks['evaluate_2025_only'] = bool(len(evaluation) and evaluation.year.eq(2025).all())
        checks['train_eval_games_disjoint'] = not bool(set(training.game_anon_id) & set(evaluation.game_anon_id))
        if not all(checks.values()):
            raise RuntimeError('Cohort checks failed before training')
        manifest['cohort'] = {
            'common_rows': len(rows), 'common_ids_sha256': ids_hash(rows.pitch_uid.tolist()),
            'by_partition': {part: {'n_pitches': len(group), 'n_games': int(group.game_anon_id.nunique()),
                                    'ids_sha256': ids_hash(group.pitch_uid.tolist()),
                                    'class_counts': {label: int(group.y_event.eq(label).sum()) for label in CLASSES}}
                             for part, group in rows.groupby('partition')},
            'exclusions': cohort['exclusions'],
        }
        write_json(folder / 'cohort_manifest.json', manifest['cohort'])
        rows[META].to_parquet(folder / 'cohort.parquet', index=False)
        cohort['assignments'].to_parquet(folder / 'assignments.parquet', index=False)
        (folder / 'models').mkdir()
        output, summaries, curves, losses = [], [], [], {}
        probability_columns = ['p_' + label for label in CLASSES]
        for name in ('B0', 'B1', 'B2'):
            model = EventBaseline(name, cfg['event_class_order'],
                                  cfg['training']['baseline_global_pseudocount_per_class'],
                                  cfg['training']['baseline_group_prior_strength']).fit(training)
            path = folder / 'models' / (name + '.json')
            model.save(path)
            inference = evaluation[['balls', 'strikes', 'auto_pitch_type']]
            probabilities, routes = model.predict(inference)
            validate_probabilities(probabilities, atol=cfg['numerical_checks']['probability_sum_atol'])
            reloaded = EventBaseline.load(path)
            again, again_routes = reloaded.predict(inference)
            checks[name + '_reload_predictions'] = bool(np.allclose(probabilities, again, atol=cfg['numerical_checks']['reload_prediction_atol_cpu'], rtol=0) and np.array_equal(routes, again_routes))
            checks[name + '_all_classes_positive'] = bool((probabilities > 0).all())
            checks[name + '_training_count'] = sum(model.state['global_counts']) == len(training)
            # Ensure changing evaluation inputs never modifies saved fitted counts.
            before = json.dumps(model.state, sort_keys=True)
            unknown = pd.DataFrame({'balls': [0], 'strikes': [0], 'auto_pitch_type': ['__unseen__']})
            model.predict(unknown)
            checks[name + '_predict_does_not_fit'] = before == json.dumps(model.state, sort_keys=True)
            prediction = evaluation[META + ['y_event']].copy()
            prediction[probability_columns] = probabilities
            prediction['model'] = name
            prediction['route'] = routes
            prediction['status'] = 'smoke_only' if smoke else 'ok'
            prediction['prediction_kind'] = manifest['prediction_kind']
            prediction['data_version'] = dataset.run_id
            prediction['protocol_id'] = 'A'
            prediction['model_version'] = sha256_file(path)
            output.append(prediction)
            for part in ('development', 'calibration', 'phase_review'):
                mask = evaluation.partition.eq(part).to_numpy()
                group = evaluation.loc[mask]
                values = probabilities[mask]
                result = multiclass_metrics(group.y_event, values, CLASSES,
                                            cfg['numerical_checks']['log_loss_clipping_epsilon'])
                result.update(model=name, partition=part, n_games=int(group.game_anon_id.nunique()),
                              fallback_rows=int((routes[mask] == 'fallback_global').sum()),
                              ids_sha256=ids_hash(group.pitch_uid.tolist()))
                summaries.append(result)
                curves.extend(dict(row, model=name, partition=part) for row in
                              calibration_bins(group.y_event, values, CLASSES, cfg['evaluation']['calibration_equal_width_bins']))
                if part == 'phase_review':
                    loss, _ = per_pitch_losses(group.y_event, values, CLASSES, cfg['numerical_checks']['log_loss_clipping_epsilon'])
                    losses[name] = group[['pitch_uid', 'game_anon_id', 'y_event']].assign(loss=loss)
        predictions = pd.concat(output, ignore_index=True)
        checks['unique_pitch_model_pairs'] = not predictions.duplicated(['pitch_uid', 'model']).any()
        checks['all_predictions_2025'] = bool(predictions.year.eq(2025).all())
        comparisons = {}
        for reference, candidate in [('B0', 'B1'), ('B0', 'B2'), ('B1', 'B2')]:
            comparison = paired_bootstrap(losses[reference], losses[candidate],
                                          cfg['evaluation']['bootstrap_smoke' if smoke else 'bootstrap_full'],
                                          cfg['seed'], cfg['evaluation']['bootstrap_confidence'],
                                          cfg['evaluation']['promotion_min_relative_log_loss_reduction'], smoke)
            comparison.update(reference=reference, candidate=candidate, partition='phase_review')
            comparisons[candidate + '_vs_' + reference] = comparison
        checks['finite_metrics'] = bool(np.isfinite([r[key] for r in summaries for key in
                                                   ('multiclass_log_loss', 'multiclass_brier_sum_over_classes')]).all())
        checks['calibration_bins_account_for_all_rows'] = all(
            sum(r['n'] for r in curves if r['model'] == m['model'] and r['partition'] == m['partition'] and r['class'] == label) == m['n_pitches']
            for m in summaries for label in CLASSES)
        predictions.to_parquet(folder / 'predictions.parquet', index=False)
        checks['prediction_file_roundtrip'] = predictions.equals(pd.read_parquet(folder / 'predictions.parquet'))
        pd.DataFrame(curves).to_csv(folder / 'calibration.csv', index=False)
        for part in ('development', 'calibration', 'phase_review'):
            write_calibration_svg(folder / f'calibration_{part}.svg', curves, part, CLASSES)
        write_json(folder / 'metrics.json', {
            'status': 'smoke_only' if smoke else 'evaluated', 'protocol_id': 'A', 'target': 'y_event',
            'data_run': dataset.run_id, 'seed': cfg['seed'], 'denominator': manifest['denominator'],
            'class_order': list(CLASSES), 'metrics': summaries, 'comparisons': comparisons,
            'reference_model': 'B1', 'B2_replaces_B1': False,
            'review_is_independent_final_test': False,
        })
        write_json(folder / 'checks.json', {key: bool(value) for key, value in checks.items()})
        if not all(checks.values()):
            raise RuntimeError('F1 technical checks failed: ' + ', '.join(k for k, v in checks.items() if not v))
        dataset.assert_unchanged()
        manifest['status'] = 'verified'
        manifest['scientific_decision'] = 'inconclusive' if smoke else 'retain_reference'
        lines = ['# Decisión F1', '', 'Implementación: `verified`.',
                 f'Decisión de fase: `{manifest["scientific_decision"]}`.', '',
                 'B1 conserva su papel de referencia conceptual. B2 es un comparador adicional y no lo reemplaza.',
                 'No se ha calculado xRunValue ni scores; el target es y_event. 2026 permanece sellado.', '']
        for key, result in comparisons.items():
            lines.append(f'- {key}: `{result["decision"]}`; reducción relativa de log loss: {result["relative_log_loss_reduction"]}; IC 95% delta: [{result["ci_low"]}, {result["ci_high"]}].')
        lines.extend(['', 'Las curvas son diagnósticas; no se ajustaron calibradores ni hiperparámetros con 2025.',
                      'La revisión de 2025 no es una evaluación final independiente.',
                      'Solo verificación de flujo; no habilita F2 por sí sola.' if smoke else 'F2 queda habilitada tras las pruebas de regresión y reproducción; no se ejecuta automáticamente.'])
        (folder / 'decision.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except Exception as exc:
        manifest.update(status='blocked', error=f'{type(exc).__name__}: {exc}')
        write_json(folder / 'checks.json', {**{k: bool(v) for k, v in checks.items()}, 'technical_failure': False, 'error': manifest['error']})
        (folder / 'decision.md').write_text('# Decisión F1\n\n`blocked`; no avanzar.\n\n' + manifest['error'], encoding='utf-8')
        raise
    finally:
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['elapsed_seconds'] = time.perf_counter() - tick
        manifest['artifact_hashes'] = {p.relative_to(folder).as_posix(): sha256_file(p)
                                      for p in sorted(folder.rglob('*')) if p.is_file() and p != folder / 'manifest.json'}
        write_json(folder / 'manifest.json', manifest)
    print(json.dumps({'path': str(folder), 'status': manifest['status'], 'decision': manifest['scientific_decision'],
                      'cohort_rows': len(rows), 'evaluated_rows_per_model': len(evaluation),
                      'cohort_sha256': manifest['cohort']['common_ids_sha256']}, indent=2))
    return folder
