"""F6 A: matched environmental ablation and fixed-shape probability associations."""
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
import re
import sys
import time
import uuid
import numpy as np
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler
from modeling.cli import verify, write_json
from modeling.datasets import ROOT, META, ModelingDataset, duckdb, ids_hash, pd, sha256_file
from modeling.environment import (ENV, MODE, PROBS, EnvironmentEventModel, EnvironmentSimulator,
                                  cohort_delta_interval)
from modeling.metrics import multiclass_metrics
from modeling.models import TabularEventModel
from modeling.phase3 import partition_summary
from modeling.phase4 import calibrate, compare_head, support
from modeling.phase5 import verify_f4


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify_f5(dataset):
    f4_folder, _ = verify_f4(dataset)
    cfg = dataset.config
    if next(p for p in cfg['phases'] if p['id']=='F5')['status'] != 'verified':
        raise RuntimeError('F5 must be verified')
    name = cfg['F6']['f5_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', name):
        raise ValueError('Invalid F5 dependency')
    folder = dataset.root/'artifacts/modeling'/name/'F5'
    m = read(folder/'manifest.json')
    if (m['status'] != 'verified' or m['smoke'] or m['phase_id'] != 'F5' or m['test_accessed']
            or m['data_run'] != dataset.run_id or m['data_manifest_sha256'] != dataset.manifest_hash):
        raise RuntimeError('F5 must be a verified full experiment on pinned data')
    if not {'config.json','checks.json','policy.json','metrics.json'}.issubset(m['artifact_hashes']):
        raise RuntimeError('Incomplete F5 evidence')
    for name, digest in m['artifact_hashes'].items():
        path = (folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise RuntimeError('F5 artifact integrity failure: '+name)
    checks = read(folder/'checks.json')
    if not checks or not all(v is True for v in checks.values()):
        raise RuntimeError('F5 checks failed')
    previous = read(folder/'config.json')
    for key in ('F5','protocol_A','protocol_C','seed','evaluation'):
        if cfg[key] != previous[key]:
            raise RuntimeError('F5 configuration changed: '+key)
    if read(folder/'policy.json')['promote_arsenal'] or cfg['F6']['protocol_id'] != 'A':
        raise RuntimeError('F6 design requires the retained A reference; reconcile a changed F5 decision')
    return folder, f4_folder


def load_rows(dataset, smoke):
    cohort = dataset.load(maximum=dataset.config['training']['smoke_target_max_pitches'] if smoke else None, phase='F6')
    with duckdb.connect(str(dataset.run/'diablos.duckdb'), read_only=True) as db:
        category = db.execute('SELECT pitch_uid, altitude_category FROM model_base WHERE year IN (2024, 2025)').df()
    rows = cohort['aligned']['pitching'].merge(category, on='pitch_uid', validate='one_to_one', how='left')
    if rows[ENV].isna().any():
        raise ValueError('Unexpected missing environment after unchanged eligibility filters')
    dataset.assert_unchanged()
    return rows, cohort


def subgroup_metrics(training, review, control, candidate, cfg, smoke):
    groups = [[ENV], ['auto_pitch_type'], ['pitcher_throws'], ['batter_side'],
              [ENV,'auto_pitch_type','pitcher_throws']]
    result = []
    for columns in groups:
        for key, group in review.groupby(columns, sort=True, dropna=False):
            keys = key if isinstance(key, tuple) else (key,)
            fit = training
            for column, value in zip(columns, keys):
                fit = fit.loc[fit[column].eq(value)]
            fit_support, review_support = support(fit, 'y_event', CLASSES, cfg), support(group, 'y_event', CLASSES, cfg)
            item = dict(group_by=columns, values=list(keys), fit_support=fit_support, review_support=review_support,
                        status='insufficient_data', metrics=None, comparison=None, diagnostic_only=True,
                        multiplicity_adjusted=False, ranking_allowed=False)
            if fit_support['sufficient'] and review_support['sufficient']:
                positions = review.index.get_indexer(group.index)
                item.update(status='evaluated', metrics={
                    'control': multiclass_metrics(group.y_event, control[positions], CLASSES),
                    'environment': multiclass_metrics(group.y_event, candidate[positions], CLASSES)},
                    comparison=compare_head(group, 'y_event', CLASSES, control[positions], candidate[positions], cfg, smoke))
            result.append(item)
    return result


def run_variant(name, training, development, evaluation, parameters, folder, cfg, smoke, checks):
    settings = cfg['F6']
    destination = folder/name
    destination.mkdir()
    rounds = settings['smoke_rounds'] if smoke else settings['maximum_rounds']
    def fit():
        return EnvironmentEventModel(name=='environment', cfg['seed'], settings['threads']).fit(
            training, development, parameters, rounds, settings['early_stopping_rounds'], settings['minimum_support_rows'])
    print(f'F6 {name}: fitting {len(training)} pitches; development {len(development)}', flush=True)
    model = fit()
    model.save(destination/'model')
    raw = model.predict(evaluation)
    checks[name+'_reload_exact'] = bool(np.array_equal(raw, EnvironmentEventModel.load(destination/'model').predict(evaluation)))
    checks[name+'_refit_exact'] = bool(np.array_equal(raw, fit().predict(evaluation)))
    checks[name+'_fit_ids'] = model.metadata['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
    checks[name+'_development_ids'] = model.metadata['development_ids_sha256'] == ids_hash(development.pitch_uid.tolist())
    changed = evaluation.head(100).copy()
    for column in ('y_event','pitch_uid','pitcher_anon_id'):
        changed[column] = 'excluded'
    checks[name+'_outcomes_ids_invariant'] = bool(np.array_equal(raw[:len(changed)], model.predict(changed)))
    selected, temperatures, calibration = calibrate(evaluation, raw, 'y_event', CLASSES, destination, cfg, smoke=smoke)
    # The F4 calibration engine is reused; label this experiment's plots accurately.
    for path in destination.glob('*.svg'):
        path.write_text(path.read_text(encoding='utf-8').replace('F4 y_event', 'F6 A '+name), encoding='utf-8')
    predictions = evaluation[META+['y_event', ENV]].copy()
    for label, matrix in (('raw',raw),('temperature',temperatures),('selected',selected)):
        for i, cls in enumerate(CLASSES):
            predictions[label+'_'+cls] = matrix[:,i]
    predictions.to_parquet(destination/'predictions.parquet', index=False)
    return model, raw, selected, calibration


def train_environment(experiment_id=None, smoke=False, root=ROOT):
    started, tick = datetime.now(timezone.utc), time.perf_counter()
    dataset = ModelingDataset(root)
    cfg, settings = dataset.config, dataset.config['F6']
    f5_folder, f4_folder = verify_f5(dataset)
    reference_model = read(f4_folder/'pitching/event/model/preprocessing.json')
    parameters = {k: reference_model['parameters'][k] for k in ('num_leaves','min_data_in_leaf','learning_rate','lambda_l2')}
    if settings['maximum_rounds'] != reference_model['maximum_rounds'] or settings['early_stopping_rounds'] != reference_model['patience']:
        raise ValueError('F6 control must reproduce the approved A training budget')
    experiment_id = experiment_id or started.strftime('f6-%Y%m%dT%H%M%S-')+uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root/'artifacts/modeling'/experiment_id/'F6'
    folder.mkdir(parents=True, exist_ok=False)
    sources = sorted((dataset.root/'modeling').glob('*.py'))+[dataset.root/'scripts/check_phase6.py',dataset.root/'diablos_data.py']
    manifest = dict(phase_id='F6', experiment_id=experiment_id, status='in_progress', scientific_decision='not_applicable',
        protocol_id='A', smoke=smoke, seed=cfg['seed'], data_run=dataset.run_id, data_manifest_sha256=dataset.manifest_hash,
        config_sha256=dataset.config_hash, document_sha256=sha256_file(dataset.root/cfg['document']),
        code_hashes={str(p.relative_to(dataset.root)):sha256_file(p) for p in sources},
        requirements_sha256=sha256_file(dataset.root/'requirements-modeling.txt'),
        dependencies={name:sha256_file(path/'manifest.json') for name,path in [('F5',f5_folder),('F4',f4_folder)]},
        versions={'python':platform.python_version(), **{n:importlib.metadata.version(n) for n in ('lightgbm','numpy','pandas','scipy','pyarrow','duckdb')}},
        python_executable=sys.executable, virtual_environment=sys.prefix != sys.base_prefix,
        hardware={'processor':platform.processor(),'threads':settings['threads']},
        test_accessed=False, test_quality_previously_profiled=True, started_utc=started.isoformat())
    write_json(folder/'manifest.json', manifest)
    write_json(folder/'config.json', cfg)
    write_json(folder/'design.json', dict(protocol='A', parameters=parameters, parameter_source='approved_F3_A_Pitching',
        search_configurations=1, selection_partition='2025/development',
        reference_choice='F5 did not promote arsenal; continue approved A without comparing A/C metrics',
        environmental_scope='categorical_association_only', arsenal_used=False))
    checks = {}
    try:
        rows, cohort = load_rows(dataset, smoke)
        checks.update(verify(cohort,dataset))
        training = rows.loc[rows.partition.eq('train')].reset_index(drop=True)
        development = rows.loc[rows.partition.eq('development')].reset_index(drop=True)
        evaluation = rows.loc[rows.partition.ne('train')].reset_index(drop=True)
        categories = sorted(training[ENV].unique().tolist())
        checks['evaluation_environment_seen'] = set(evaluation[ENV]).issubset(categories)
        rows.to_parquet(folder/'cohort.parquet',index=False)
        write_json(folder/'cohort_manifest.json', dict(partitions=partition_summary(rows), common_ids_sha256=ids_hash(rows.pitch_uid.tolist()),
            exclusions=cohort['exclusions'], training_categories=categories, denominator='unchanged F0/F3 common eligibility'))
        coverage = rows.groupby(['partition',ENV],sort=True).agg(n_pitches=('pitch_uid','size'),
            n_pitchers=('pitcher_anon_id','nunique'),n_games=('game_anon_id','nunique')).reset_index()
        coverage.to_csv(folder/'environment_coverage.csv',index=False)
        if not all(checks.values()):
            raise RuntimeError('Cohort integrity failed before training')
        models, raw, selected, calibrations = {}, {}, {}, {}
        for name in ('control','environment'):
            models[name],raw[name],selected[name],calibrations[name] = run_variant(
                name,training,development,evaluation,parameters,folder,cfg,smoke,checks)
        checks['identical_fit_and_development'] = all(models['control'].metadata[k]==models['environment'].metadata[k]
            for k in ('fit_ids_sha256','development_ids_sha256','fit_rows'))
        if not smoke:
            old = pd.read_parquet(f4_folder/'pitching/event/predictions.parquet').set_index('pitch_uid').loc[evaluation.pitch_uid]
            checks['control_matches_approved_F4_raw'] = bool(np.array_equal(old[['raw_'+c for c in CLASSES]].to_numpy(),raw['control']))
            checks['control_matches_approved_F4_calibrated'] = bool(np.array_equal(old[['selected_'+c for c in CLASSES]].to_numpy(),selected['control']))
        changed = evaluation.head(100).copy()
        changed[ENV] = 'unsupported_for_environment_but_ignored_by_other_families'
        for family in ('stuff','location'):
            model = TabularEventModel.load(f4_folder/family/'event/model')
            checks[family+'_environment_invariant'] = bool(np.array_equal(model.predict(evaluation.head(100)),model.predict(changed)))
        checks['control_environment_invariant'] = bool(np.array_equal(raw['control'][:len(changed)],models['control'].predict(changed)))
        review_mask = evaluation.partition.eq('phase_review').to_numpy()
        review = evaluation.loc[review_mask].reset_index(drop=True)
        comparison = compare_head(review,'y_event',CLASSES,selected['control'][review_mask],selected['environment'][review_mask],cfg,smoke)
        enough = all(support(g,'y_event',CLASSES,cfg)['sufficient'] for g in (training,review))
        promoted = enough and comparison['decision']=='promote'
        decision = 'promote' if promoted else ('inconclusive' if smoke or not enough else 'retain_reference')
        write_json(folder/'policy.json',dict(protocol_id='A',promote_environment=bool(promoted),
            prediction_branch='environment' if promoted else 'control', environment_mode=MODE,
            simulator_branch='environment',simulator_is_diagnostic=True,score_available=False,
            unsupported_environment_policy='null_with_reason',reference='F4_A_Pitching',test_accessed=False))
        output = evaluation[META+['y_event',ENV]].copy()
        for name, matrix in [('control',selected['control']),('environment',selected['environment']),
                             ('selected',selected['environment'] if promoted else selected['control'])]:
            for i,c in enumerate(CLASSES):
                output[name+'_'+c] = matrix[:,i]
        output['protocol_id'],output['data_version'] = 'A',dataset.run_id
        output['route'] = 'environment' if promoted else 'base'
        output['status'] = 'smoke_only' if smoke else 'ok'
        output.to_parquet(folder/'predictions.parquet',index=False)
        checks['prediction_roundtrip'] = output.equals(pd.read_parquet(folder/'predictions.parquet'))
        metrics = []
        for name,matrix in selected.items():
            for part in ('development','calibration','phase_review'):
                mask = evaluation.partition.eq(part).to_numpy()
                metrics.append(dict(multiclass_metrics(evaluation.loc[mask,'y_event'],matrix[mask],CLASSES),
                    model=name,partition=part,ids_sha256=ids_hash(evaluation.loc[mask,'pitch_uid'].tolist())))
        write_json(folder/'metrics.json',dict(metrics=metrics,comparison=comparison,scientific_decision=decision,
            sufficient_for_comparison=bool(enough),review_is_independent_final_test=False))
        subgroups = subgroup_metrics(training,review,selected['control'][review_mask],selected['environment'][review_mask],cfg,smoke)
        write_json(folder/'subgroup_metrics.json',subgroups)
        write_json(folder/'environment_support.json',models['environment'].metadata['environment_support'])
        simulator = EnvironmentSimulator.load(folder)
        diagnostic = simulator.predict(evaluation)
        checks['simulator_observed_probabilities_exact'] = bool(np.array_equal(diagnostic[PROBS].to_numpy(),selected['environment']))
        diagnostic.to_parquet(folder/'input_support.parquet',index=False)
        simulations,intervals = [],[]
        for target in categories:
            scenario = simulator.simulate(review,target)
            interval = cohort_delta_interval(scenario,review,cfg['evaluation']['bootstrap_smoke' if smoke else 'bootstrap_full'],
                cfg['seed'],cfg['evaluation']['bootstrap_confidence'],settings['minimum_support_rows'],smoke)
            interval['target_environment'] = target
            simulations.append(scenario)
            intervals.append(interval)
        pd.concat(simulations,ignore_index=True).to_parquet(folder/'simulation_deltas.parquet',index=False)
        write_json(folder/'simulation_intervals.json',intervals)
        same = simulator.simulate(review.head(100),review.head(100)[ENV].to_numpy())
        checks['same_environment_zero_delta'] = bool((same[['delta_'+p for p in PROBS]].to_numpy()==0).all())
        invalid = simulator.simulate(review.head(5),'Harp Helu')
        checks['unknown_environment_rejected'] = bool(invalid.status.eq('unsupported_environment').all() and invalid[['delta_'+p for p in PROBS]].isna().all().all())
        snapshot = review.head(100).copy(deep=True)
        simulator.simulate(snapshot,categories[0])
        checks['simulator_preserves_physics_location_inputs'] = snapshot.equals(review.head(100))
        extremes = review.head(5).copy()
        extremes['induced_vert_break'] = 1e6
        warned = simulator.simulate(extremes,categories[0])
        checks['outside_support_warned_no_recommendation'] = bool(warned.input_support_status.eq('outside_support').all() and ~warned.recommendation_allowed.any())
        if not all(checks.values()):
            raise RuntimeError('Failed checks: '+', '.join(k for k,v in checks.items() if not v))
        dataset.assert_unchanged()
        manifest.update(status='verified',scientific_decision=decision)
        (folder/'decision.md').write_text('# F6\n\nImplementation: verified. Decision: '+decision+
            '\n\nA matched environment ablation; 2024 fit, 2025 development/calibration/review. '
            'Simulator is fixed_shape_environment_association, not a physical transformation or causal effect. '
            'Intervals apply to supported cohort means with models fixed, never to individual pitches. '
            'Unknown environments return null. No Harp mapping, numeric altitude, scores or test opening.\n',encoding='utf-8')
    except Exception as exc:
        manifest.update(status='blocked',error=f'{type(exc).__name__}: {exc}')
        checks['technical_failure'] = False
        raise
    finally:
        write_json(folder/'checks.json',{k:bool(v) for k,v in checks.items()})
        manifest.update(finished_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.perf_counter()-tick)
        manifest['artifact_hashes']={p.relative_to(folder).as_posix():sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file() and p!=folder/'manifest.json'}
        write_json(folder/'manifest.json',manifest)
    print(json.dumps({'path':str(folder),'status':manifest['status'],'decision':decision}),flush=True)
    return folder
