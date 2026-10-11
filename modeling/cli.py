"""F0 infrastructure: smoke [--full]. F1/F2/F3/F4 modeling: train --phase F1|F2|F3|F4 [--smoke]."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
import re
import time
import uuid

from modeling.datasets import (ROOT, FEATURES, META, ModelingDataset, assign_partitions,
                               ids_hash, join_pitches, pd, sha256_file)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def verify(cohort, dataset):
    checks = {}
    assignments = cohort['assignments']
    checks['unique_assignment_ids'] = bool(assignments.pitch_uid.is_unique)
    checks['no_2026'] = bool(assignments.year.isin([2024, 2025]).all())
    checks['games_do_not_cross_partitions'] = bool(assignments.groupby('game_anon_id').partition.nunique().eq(1).all())
    shuffled = assign_partitions(assignments.drop(columns='partition').sample(frac=1, random_state=dataset.config['seed']), dataset.config)
    checks['shuffle_invariant_assignments'] = assignments.equals(shuffled)
    common_ids = cohort['common_ids'].pitch_uid.tolist()
    shuffled_common = cohort['families']['stuff'][['pitch_uid']].sample(frac=1, random_state=7)
    for family in ('location', 'pitching'):
        shuffled_common = join_pitches(shuffled_common, cohort['families'][family][['pitch_uid']].sample(frac=1, random_state=9))
    checks['shuffle_invariant_common_cohort'] = ids_hash(shuffled_common.pitch_uid.tolist()) == ids_hash(common_ids)
    checks['nonempty_common_cohort'] = bool(common_ids)
    checks['all_development_partitions_represented'] = set(cohort['aligned']['stuff'].partition) == {'train', 'development', 'calibration', 'phase_review'}
    for family, rows in cohort['aligned'].items():
        X, y, meta = dataset.matrices(cohort, family)
        checks[family + '_exact_features'] = X.columns.tolist() == FEATURES[family]
        checks[family + '_one_to_one_common_ids'] = rows.pitch_uid.tolist() == common_ids and rows.pitch_uid.is_unique
        checks[family + '_same_labels'] = y.equals(cohort['aligned']['stuff'].y_event)
        checks[family + '_no_missing_values'] = not X.isna().any().any() and not y.isna().any()
    checks['baseline_context_aligned'] = cohort['context'].pitch_uid.tolist() == common_ids
    try:
        join_pitches(pd.DataFrame({'pitch_uid': ['a', 'a']}), pd.DataFrame({'pitch_uid': ['a']}))
    except ValueError:
        checks['duplicate_join_rejected'] = True
    else:
        checks['duplicate_join_rejected'] = False
    for key, kwargs, error in [
        ('unknown_target_rejected', {'target': 'unknown_target'}, ValueError),
        ('test_access_rejected', {'partitions': ['test']}, PermissionError),
        ('f8_without_release_rejected', {'partitions': ['test'], 'phase': 'F8'}, PermissionError),
    ]:
        try:
            dataset.load(**kwargs)
        except error:
            checks[key] = True
        else:
            checks[key] = False
    return checks


def smoke(experiment_id=None, full=False, maximum=None, root=ROOT):
    started = datetime.now(timezone.utc)
    tick = time.perf_counter()
    dataset = ModelingDataset(root)
    maximum = None if full else (maximum if maximum is not None else dataset.config['training']['smoke_target_max_pitches'])
    if maximum is not None and not 0 < maximum <= 20000:
        raise ValueError('Smoke maximum must be between 1 and 20000; use --full for complete verification')
    experiment_id = experiment_id or started.strftime('f0-%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    destination = dataset.root / 'artifacts/modeling' / experiment_id / 'F0'
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {
        'experiment_id': experiment_id, 'phase_id': 'F0', 'status': 'in_progress',
        'scientific_decision': 'not_applicable', 'protocol_id': 'A',
        'model': 'dummy_uniform_NOT_A_TRAINED_MODEL', 'prediction_kind': 'synthetic_smoke_only',
        'target': 'y_event', 'seed': dataset.config['seed'],
        'started_utc': started.isoformat(), 'data_run': dataset.run_id,
        'data_manifest_sha256': dataset.manifest_hash,
        'data_output_hashes': dataset.manifest['outputs'],
        'config_sha256': dataset.config_hash,
        'code_hashes': {str(p.relative_to(dataset.root)): sha256_file(p) for p in sorted((dataset.root / 'modeling').glob('*.py'))},
        'document_sha256': sha256_file(dataset.root / dataset.config['document']),
        'versions': {'python': platform.python_version(), **{
            name: importlib.metadata.version(name) for name in ('pandas', 'numpy', 'duckdb', 'pyarrow')}},
        'sampling': {'maximum_pitches': maximum, 'unit': 'game_anon_id',
                     'method': 'whole games in SHA256(seed|game_id) order; stop before budget'},
        'test_accessed': False,
        'test_quality_previously_profiled': True,
        'f8_release_access_implemented': False,
        'eligibility_policy': 'Preserve prepared family quality flags, including environment availability for pitching; altitude excluded from predictors',
    }
    write_json(destination / 'manifest.json', manifest)
    write_json(destination / 'config.json', dataset.config)
    try:
        cohort = dataset.load(maximum=maximum)
        checks = verify(cohort, dataset)
        rows = cohort['aligned']['stuff']
        predictions = rows[META].copy()
        for label in dataset.config['event_class_order']:
            predictions['p_' + label] = 1.0 / 6
        predictions['prediction_kind'] = 'synthetic_smoke_only'
        predictions['status'] = 'not_for_scoring'
        predictions['model_version'] = 'F0_dummy_uniform'
        predictions['data_version'] = dataset.run_id
        predictions['protocol_id'] = 'A'
        probability_columns = ['p_' + label for label in dataset.config['event_class_order']]
        probabilities = predictions[probability_columns]
        checks['dummy_probabilities_valid'] = bool(
            probabilities.ge(0).all().all() and probabilities.le(1).all().all() and
            probabilities.sum(axis=1).sub(1).abs().le(dataset.config['numerical_checks']['probability_sum_atol']).all())
        cohort['assignments'].to_parquet(destination / 'assignments.parquet', index=False)
        cohort['sampled_ids'].to_parquet(destination / 'sampled_ids.parquet', index=False)
        predictions.to_parquet(destination / 'predictions.parquet', index=False)
        checks['prediction_roundtrip'] = predictions.equals(pd.read_parquet(destination / 'predictions.parquet'))
        manifest['cohort'] = {
            'assigned_rows': len(cohort['assignments']),
            'sampled_rows_before_filters': len(cohort['sampled_ids']),
            'common_rows': len(rows), 'common_ids_sha256': ids_hash(rows.pitch_uid.tolist()),
            'partition_ids_sha256': {p: ids_hash(g.pitch_uid.tolist()) for p, g in rows.groupby('partition')},
            'common_rows_by_partition': {p: len(g) for p, g in rows.groupby('partition')},
            'family_ids_sha256': {f: ids_hash(g.pitch_uid.tolist()) for f, g in cohort['families'].items()},
            'exclusions': cohort['exclusions'],
            'denominator': 'same eligible pitches across stuff/location/pitching; y_event non-null',
            'feature_sets': FEATURES,
        }
        write_json(destination / 'cohort_manifest.json', manifest['cohort'])
        write_json(destination / 'metrics.json', {
            'status': 'not_applicable', 'reason': 'F0 synthetic format test; no predictive metrics or scientific comparison',
            'population': len(rows), 'denominator': manifest['cohort']['denominator'],
        })
        write_json(destination / 'checks.json', checks)
        if not all(checks.values()):
            raise RuntimeError('F0 checks failed: ' + ', '.join(k for k, v in checks.items() if not v))
        dataset.assert_unchanged()
        manifest['status'] = 'verified'
        (destination / 'decision.md').write_text(
            '# DecisiÃ³n F0\n\nImplementaciÃ³n: `verified`. DecisiÃ³n cientÃ­fica: `not_applicable`.\n\n'
            'Predicciones uniformes ficticias, exclusivamente para verificar infraestructura. '
            'No son scores ni evidencia de calidad predictiva. No se entrenÃ³ un modelo.\n\n'
            'F1 puede comenzar tras reproducir el hash de cohorte y aprobar las pruebas unitarias. '
            '2026 permanece sellado. La revisiÃ³n de 2025 no es un test final independiente.\n', encoding='utf-8')
    except Exception as exc:
        manifest['status'] = 'blocked'
        manifest['error'] = f'{type(exc).__name__}: {exc}'
        failed_checks = locals().get('checks', {})
        failed_checks['technical_failure'] = False
        failed_checks['error'] = manifest['error']
        write_json(destination / 'checks.json', failed_checks)
        (destination / 'decision.md').write_text('# DecisiÃ³n F0\n\n`blocked`; no avanzar a F1.\n\n' + manifest['error'] + '\n', encoding='utf-8')
        raise
    finally:
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['elapsed_seconds'] = time.perf_counter() - tick
        manifest['artifact_hashes'] = {p.name: sha256_file(p) for p in sorted(destination.iterdir()) if p.is_file() and p.name != 'manifest.json'}
        write_json(destination / 'manifest.json', manifest)
    print(json.dumps({'path': str(destination), 'status': manifest['status'],
                      'common_rows': len(rows), 'cohort_sha256': manifest['cohort']['common_ids_sha256']}, indent=2))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('smoke', help='F0 infrastructure only; synthetic probabilities')
    command.add_argument('--experiment-id')
    scope = command.add_mutually_exclusive_group()
    scope.add_argument('--full', action='store_true', help='All development pitches, still no 2026')
    scope.add_argument('--max-pitches', type=int)
    train = commands.add_parser('train', help='Train and evaluate F1 baselines, F2 Stuff F3 families or F4 calibration/contact; final test remains sealed')
    train.add_argument('--phase', choices=['F1', 'F2', 'F3', 'F4'], required=True)
    train.add_argument('--smoke', action='store_true', help='Small flow check with 20 bootstrap resamples')
    train.add_argument('--experiment-id')
    args = parser.parse_args()
    try:
        if args.command == 'train':
            if args.phase == 'F4':
                from modeling.phase4 import train_calibration_contact
                train_calibration_contact(args.experiment_id, args.smoke)
            elif args.phase == 'F3':
                from modeling.phase3 import train_families
                train_families(args.experiment_id, args.smoke)
            elif args.phase == 'F2':
                from modeling.phase2 import train_stuff
                train_stuff(args.experiment_id, args.smoke)
            else:
                from modeling.phase1 import train_baselines
                train_baselines(args.experiment_id, args.smoke)
        else:
            smoke(args.experiment_id, args.full, args.max_pitches)
    except (ValueError, RuntimeError, PermissionError, FileExistsError) as exc:
        phase = args.phase if args.command == 'train' else 'F0'
        parser.exit(1, f'{phase} blocked: {exc}\n')


if __name__ == '__main__':
    main()
