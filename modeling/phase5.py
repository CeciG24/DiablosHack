"""F5: separate protocol C ablation using a frozen 2024 repertoire."""
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
import re
import sys
import time
import uuid
import numpy as np
from modeling.arsenal import (ARSENAL, PHYSICAL, ArsenalEventModel, attach_reference,
                              build_reference, route_probabilities)
from modeling.baselines import CLASSES
from modeling.cli import write_json
from modeling.datasets import ROOT, META, ModelingDataset, duckdb, ids_hash, pd, sha256_file
from modeling.metrics import multiclass_metrics, validate_probabilities
from modeling.phase3 import PROBABILITIES, partition_summary
from modeling.phase4 import calibrate, compare_head, support, verify_f3


def verify_f4(dataset):
    verify_f3(dataset)
    cfg = dataset.config
    if next(p for p in cfg['phases'] if p['id'] == 'F4')['status'] != 'verified':
        raise RuntimeError('F4 must be verified')
    name = cfg['F5']['f4_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', name):
        raise ValueError('Invalid F4 dependency')
    folder = dataset.root/'artifacts/modeling'/name/'F4'
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if (manifest['status'] != 'verified' or manifest['smoke'] or manifest['phase_id'] != 'F4'
            or manifest['test_accessed'] or manifest['data_run'] != dataset.run_id
            or manifest['data_manifest_sha256'] != dataset.manifest_hash):
        raise RuntimeError('F4 must be a verified full run on pinned data')
    required = {'checks.json', 'config.json', 'predictions.parquet', 'metrics.json'}
    if not required.issubset(manifest['artifact_hashes']):
        raise RuntimeError('Missing F4 evidence')
    for name, digest in manifest['artifact_hashes'].items():
        path = (folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise RuntimeError('F4 artifact integrity failure: '+name)
    checks = json.loads((folder/'checks.json').read_text(encoding='utf-8'))
    if not checks or not all(v is True for v in checks.values()):
        raise RuntimeError('F4 checks failed')
    previous = json.loads((folder/'config.json').read_text(encoding='utf-8'))
    for key in ('F4', 'protocol_A', 'protocol_C', 'evaluation', 'seed'):
        if cfg[key] != previous[key]:
            raise RuntimeError('Dependency configuration changed: '+key)
    return folder, manifest


def load_history(dataset):
    columns = ['pitch_uid', 'year', 'pitcher_anon_id', 'auto_pitch_type'] + PHYSICAL
    with duckdb.connect(str(dataset.run/'diablos.duckdb'), read_only=True) as db:
        history = db.execute('SELECT '+', '.join(columns)+' FROM pitches WHERE year = 2024').df()
    dataset.assert_unchanged()
    return history.sort_values('pitch_uid').reset_index(drop=True)


def load_c_rows(dataset, smoke, reference):
    cohort = dataset.load(partitions=('development', 'calibration', 'phase_review'),
                          maximum=dataset.config['training']['smoke_target_max_pitches'] if smoke else None, phase='F5')
    rows = cohort['aligned']['pitching']
    # Category is coverage metadata only, never an input to either model.
    with duckdb.connect(str(dataset.run/'diablos.duckdb'), read_only=True) as db:
        categories = db.execute('SELECT pitch_uid, altitude_category FROM model_base WHERE year = 2025').df()
    rows = rows.merge(categories, on='pitch_uid', validate='one_to_one')
    return attach_reference(rows, *reference), cohort['exclusions']


def coverage_tables(rows, folder):
    summary = {}
    for column in ('partition', 'auto_pitch_type', 'altitude_category', 'pitcher_anon_id', 'history_status'):
        table = rows.groupby(['partition', column] if column != 'partition' else ['partition'], dropna=False).agg(
            n_pitches=('pitch_uid', 'size'), n_with_reference=('has_reference', 'sum'),
            n_pitchers=('pitcher_anon_id', 'nunique')).reset_index()
        table['coverage'] = table.n_with_reference/table.n_pitches
        table.to_csv(folder/('coverage_'+column+'.csv'), index=False)
        if column == 'partition':
            summary = table.to_dict('records')
    return summary


def fit_variant(name, training, evaluation, folder, cfg, smoke, checks):
    destination = folder/name
    destination.mkdir()
    settings = cfg['F5']
    rounds = settings['smoke_rounds'] if smoke else settings['fixed_rounds']
    print(f'F5 {name}: fitting {len(training)} pitches, {rounds} fixed rounds', flush=True)
    model = ArsenalEventModel(name == 'arsenal', cfg['seed'], settings['threads']).fit(training, settings['parameters'], rounds)
    model.save(destination/'model')
    raw = model.predict(evaluation)
    checks[name+'_reload_exact'] = bool(np.array_equal(raw, ArsenalEventModel.load(destination/'model').predict(evaluation)))
    replay = ArsenalEventModel(name == 'arsenal', cfg['seed'], settings['threads']).fit(training, settings['parameters'], rounds)
    checks[name+'_refit_exact'] = bool(np.array_equal(raw, replay.predict(evaluation)))
    checks[name+'_fit_ids'] = model.metadata['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
    changed = evaluation.head(100).copy()
    for column in ('y_event', 'pitch_uid', 'pitcher_anon_id', 'altitude_category'):
        changed[column] = 'not_a_predictor'
    checks[name+'_excluded_invariant'] = bool(np.array_equal(raw[:len(changed)], model.predict(changed)))
    selected, temperature, policy = calibrate(evaluation, raw, 'y_event', CLASSES, destination, cfg, smoke=smoke)
    output = evaluation[META+['y_event']].copy()
    for label, matrix in (('raw', raw), ('temperature', temperature), ('selected', selected)):
        for i, cls in enumerate(CLASSES):
            output[label+'_'+cls] = matrix[:, i]
    output.to_parquet(destination/'predictions.parquet', index=False)
    write_json(destination/'fit_cohort.json', {'n_rows': len(training), 'ids_sha256': ids_hash(training.pitch_uid.tolist()),
               'year': 2025, 'partition': 'development', 'reference_year': 2024})
    return selected, policy


def train_arsenal(experiment_id=None, smoke=False, root=ROOT):
    started, tick = datetime.now(timezone.utc), time.perf_counter()
    dataset = ModelingDataset(root)
    cfg, settings = dataset.config, dataset.config['F5']
    if cfg['protocol_C']['reference_years_fixed'] != [2024] or cfg['protocol_C']['existing_2026_arsenal_features_allowed']:
        raise ValueError('Protocol C must freeze 2024 history')
    dependency, prior = verify_f4(dataset)
    experiment_id = experiment_id or started.strftime('f5-%Y%m%dT%H%M%S-')+uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root/'artifacts/modeling'/experiment_id/'F5'
    folder.mkdir(parents=True, exist_ok=False)
    sources = sorted((dataset.root/'modeling').glob('*.py'))+[dataset.root/'scripts/check_phase5.py']
    manifest = dict(phase_id='F5', experiment_id=experiment_id, status='in_progress', protocol_id='C', smoke=smoke,
        seed=cfg['seed'], data_run=dataset.run_id, data_manifest_sha256=dataset.manifest_hash,
        config_sha256=dataset.config_hash, document_sha256=sha256_file(dataset.root/cfg['document']),
        code_hashes={str(p.relative_to(dataset.root)): sha256_file(p) for p in sources},
        dependency_F4={'experiment_id': prior['experiment_id'], 'manifest_sha256': sha256_file(dependency/'manifest.json')},
        versions={'python': platform.python_version(), **{n: importlib.metadata.version(n) for n in ('numpy','pandas','lightgbm','scipy','pyarrow','duckdb')}},
        python_executable=sys.executable, virtual_environment=sys.prefix != sys.base_prefix,
        started_utc=started.isoformat(), test_accessed=False, test_quality_previously_profiled=True,
        scientific_decision='not_applicable', hardware={'processor': platform.processor(), 'threads': settings['threads']})
    write_json(folder/'manifest.json', manifest)
    write_json(folder/'config.json', cfg)
    checks = {}
    try:
        history = load_history(dataset)
        data_cfg = json.loads((dataset.root/cfg['data_contract']).read_text(encoding='utf-8'))
        reference = build_reference(history, data_cfg['minimum_fastball_reference'], data_cfg['fastball_types'])
        ref_folder = folder/'reference_2024'
        ref_folder.mkdir()
        for name, table in zip(('fastballs', 'type_counts', 'pitcher_counts'), reference):
            table.to_parquet(ref_folder/(name+'.parquet'), index=False)
        history[['pitch_uid', 'year', 'pitcher_anon_id']].to_parquet(ref_folder/'source_ids.parquet', index=False)
        write_json(ref_folder/'manifest.json', dict(reference_id='fixed_2024_'+ids_hash(history.pitch_uid.tolist())[:16],
                   reference_years=[2024], source_rows=len(history), source_ids_sha256=ids_hash(history.pitch_uid.tolist()),
                   data_run=dataset.run_id, minimum_fastball_reference=data_cfg['minimum_fastball_reference'],
                   fastball_types=data_cfg['fastball_types'], target_years=[2025,2026], outcomes_used=False,
                   semantics='release_distance_is_not_tunneling',
                   artifact_hashes={p.name: sha256_file(p) for p in ref_folder.iterdir() if p.is_file()}))
        rows, exclusions = load_c_rows(dataset, smoke, reference)
        rows.to_parquet(folder/'cohort.parquet', index=False)
        checks['reference_only_2024'] = bool(history.year.eq(2024).all() and reference[0].source_max_year.eq(2024).all())
        checks['reference_order_invariant'] = all(a.equals(b) for a,b in zip(reference, build_reference(history.sample(frac=1, random_state=7), data_cfg['minimum_fastball_reference'], data_cfg['fastball_types'])))
        checks['only_2025_model_population'] = bool(rows.year.eq(2025).all())
        checks['partitions_separate_games'] = bool(rows.groupby('game_anon_id').partition.nunique().eq(1).all())
        checks['unique_ids'] = not rows.pitch_uid.duplicated().any()
        coverage = coverage_tables(rows, folder)
        write_json(folder/'cohort_manifest.json', dict(partitions=partition_summary(rows), coverage=coverage,
            common_ids_sha256=ids_hash(rows.pitch_uid.tolist()), exclusions=exclusions,
            denominator='F0 common eligibility restricted to 2025; all history built from full 2024',
            split_is_chronological=False, comparable_to_protocol_A=False))
        fit = rows.loc[rows.partition.eq('development')]
        evaluation = rows.loc[rows.partition.ne('development')].reset_index(drop=True)
        history_fit = fit.loc[fit.has_reference]
        history_eval = evaluation.loc[evaluation.has_reference].reset_index(drop=True)
        if not all(checks.values()):
            raise RuntimeError('Cohort integrity failure')
        base, base_calibration = fit_variant('fallback', fit, evaluation, folder, cfg, smoke, checks)
        enough = all(support(g, 'y_event', CLASSES, cfg)['sufficient'] for g in
                     (history_fit, history_eval.loc[history_eval.partition.eq('phase_review')]))
        review = evaluation.partition.eq('phase_review').to_numpy()
        covered_review = history_eval.partition.eq('phase_review').to_numpy()
        comparison = None
        if enough:
            control, _ = fit_variant('control', history_fit, history_eval, folder, cfg, smoke, checks)
            arsenal, _ = fit_variant('arsenal', history_fit, history_eval, folder, cfg, smoke, checks)
            comparison = compare_head(history_eval.loc[covered_review], 'y_event', CLASSES,
                                      control[covered_review], arsenal[covered_review], cfg, smoke)
            checks['matched_fit_ids'] = json.loads((folder/'control/fit_cohort.json').read_text()) == json.loads((folder/'arsenal/fit_cohort.json').read_text())
        else:
            control = arsenal = base[evaluation.has_reference.to_numpy()]
        promoted = comparison is not None and comparison['decision'] == 'promote'
        control_policy, _ = route_probabilities(base, control, arsenal, evaluation.has_reference, False)
        candidate_policy, _ = route_probabilities(base, control, arsenal, evaluation.has_reference, True)
        selected, routes = route_probabilities(base, control, arsenal, evaluation.has_reference, promoted)
        if not enough:
            routes[:] = 'fallback'
        checks['fallback_exact'] = bool(np.array_equal(selected[~evaluation.has_reference], base[~evaluation.has_reference]))
        checks['cold_start_uses_base'] = bool(np.array_equal(route_probabilities(base, control[:0], arsenal[:0], np.zeros(len(base), dtype=bool), True)[0], base))
        checks['valid_probabilities'] = bool(np.isfinite(validate_probabilities(selected)).all())
        complete_comparison = compare_head(evaluation.loc[review], 'y_event', CLASSES,
                                          control_policy[review], candidate_policy[review], cfg, smoke) if enough else None
        metrics = []
        for name, p in (('full_base', base), ('control_policy', control_policy), ('candidate_policy', candidate_policy), ('selected_policy', selected)):
            for part in ('calibration', 'phase_review'):
                mask = evaluation.partition.eq(part).to_numpy()
                metrics.append(dict(multiclass_metrics(evaluation.loc[mask, 'y_event'], p[mask], CLASSES),
                                    model=name, partition=part, ids_sha256=ids_hash(evaluation.loc[mask, 'pitch_uid'].tolist())))
        decision = 'promote' if promoted else ('inconclusive' if smoke or not enough else 'retain_reference')
        output = evaluation[META+['y_event', 'has_reference', 'history_status', 'fb_n']].copy()
        for name, p in (('full_base', base), ('control_policy', control_policy), ('candidate_policy', candidate_policy), ('selected', selected)):
            for i, cls in enumerate(CLASSES):
                output[name+'_'+cls] = p[:,i]
        output['route'], output['protocol_id'] = routes, 'C'
        output['status'] = 'smoke_only' if smoke else 'ok'
        output['data_version'] = dataset.run_id
        output['warnings'] = np.where(evaluation.has_reference, '', 'insufficient_history')
        output.to_parquet(folder/'predictions.parquet', index=False)
        checks['output_roundtrip'] = output.equals(pd.read_parquet(folder/'predictions.parquet'))
        write_json(folder/'metrics.json', dict(metrics=metrics, paired_arsenal=comparison,
            full_policy_comparison=complete_comparison, scientific_decision=decision,
            arsenal_status='evaluated' if enough else 'insufficient_data', review_is_independent_final_test=False,
            protocol_A_reference_retained=True, promotion_scope='protocol_C_only'))
        write_json(folder/'policy.json', dict(protocol_id='C', promote_arsenal=promoted, available=bool(enough),
            history_branch='arsenal' if promoted else ('control' if enough else 'fallback'),
            missing_history_branch='fallback', cold_start_branch='fallback',
            scenario='adaptation_with_fixed_2024_history', reference_years=[2024],
            protocol_A_replaced=False, score_available=False, environment_used=False))
        if not all(checks.values()):
            raise RuntimeError('Failed checks: '+', '.join(k for k,v in checks.items() if not v))
        dataset.assert_unchanged()
        manifest.update(status='verified', scientific_decision=decision)
        (folder/'decision.md').write_text('# F5\n\nImplementation: verified. Decision: '+decision+
            '\n\nProtocol C only; fixed 2024 history. Models fit 2025 development, calibration on calibration only. '
            'Matched control and arsenal populations; full policy includes fallback. A is retained independently. '
            'No 2026 labels, environmental predictor, tunneling claim, scores or xRunValue.\n', encoding='utf-8')
    except Exception as exc:
        manifest.update(status='blocked', error=f'{type(exc).__name__}: {exc}')
        checks['technical_failure'] = False
        raise
    finally:
        write_json(folder/'checks.json', {k: bool(v) for k,v in checks.items()})
        manifest.update(finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.perf_counter()-tick)
        manifest['artifact_hashes'] = {p.relative_to(folder).as_posix(): sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file() and p != folder/'manifest.json'}
        write_json(folder/'manifest.json', manifest)
    print(json.dumps({'path': str(folder), 'status': manifest['status'], 'decision': decision}), flush=True)
    return folder
