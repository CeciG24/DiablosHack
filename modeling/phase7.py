"""F7: fixed common-reference indices and observed-mix coverage aggregates."""
from datetime import datetime, timezone
import re
import sys
import time
import numpy as np
from modeling.cli import write_json
from modeling.datasets import (ROOT, ModelingDataset, duckdb, pd, sha256_file, ids_hash,
                               assign_partitions, sample_games, require_unique)
from modeling.phase6 import verify_f5, read
from modeling.scoring import S0, S1, WEIGHTS, PROBS, FixedScale, utility, aggregate


def verify_f6(dataset):
    _,f4 = verify_f5(dataset)
    cfg = dataset.config
    if next(p for p in cfg['phases'] if p['id']=='F6')['status'] != 'verified':
        raise RuntimeError('F6 must be verified')
    name = cfg['F7']['f6_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}',name):
        raise ValueError('Invalid F6 dependency')
    folder = dataset.root/'artifacts/modeling'/name/'F6'
    m = read(folder/'manifest.json')
    if (m['phase_id'] != 'F6' or m['status'] != 'verified' or m['smoke'] or m['test_accessed']
            or m['data_run'] != dataset.run_id or m['data_manifest_sha256'] != dataset.manifest_hash):
        raise RuntimeError('F6 must be verified full evidence on pinned data')
    required = {'config.json','checks.json','policy.json','predictions.parquet','simulation_deltas.parquet'}
    if not required.issubset(m['artifact_hashes']):
        raise RuntimeError('Incomplete F6 evidence')
    for name,digest in m['artifact_hashes'].items():
        path = (folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise RuntimeError('F6 artifact integrity failure: '+name)
    if not read(folder/'checks.json') or not all(v is True for v in read(folder/'checks.json').values()):
        raise RuntimeError('Failed F6 checks')
    previous = read(folder/'config.json')
    for key in ('F6','protocol_A','seed','evaluation'):
        if cfg[key] != previous[key]:
            raise RuntimeError('Changed F6 configuration: '+key)
    policy = read(folder/'policy.json')
    if policy['promote_environment'] or policy['prediction_branch'] != 'control':
        raise RuntimeError('Reconcile changed environment policy before scoring')
    if cfg['score']['default_weights'] != WEIGHTS or cfg['F7']['published_score_version'] != S0:
        raise RuntimeError('Changed score policy requires new implementation/version')
    expected = dict(default_version=S0, optional_contact_weights=dict(weak_contact_joint=.5,hard_contact_joint=-1.),
                    optional_contact_version_requires_verified_heads=True,normalization_mean=100,normalization_std=10,
                    std_ddof=0,renormalize_by_park_or_pitcher=False,represents_expected_runs=False)
    if any(cfg['score'][k] != v for k,v in expected.items()):
        raise RuntimeError('Unsupported score configuration change')
    expected_f7 = dict(protocol_id='A',experimental_score_version=S1,sensitivity_relative_changes=[-.25,.25],
        reference_scope='full_common_eligible_2025_calibration_even_in_smoke',aggregation='observed_mix_mean_valid_pitches',
        coverage_denominator='all_2025_pitches_in_selected_games',contact_requires_promoted_model=True)
    if any(cfg['F7'][k] != v for k,v in expected_f7.items()):
        raise RuntimeError('Unsupported F7 configuration change')
    return folder,f4


def sources(dataset,smoke):
    f6,f4 = verify_f6(dataset)
    predictions = pd.read_parquet(f4/'predictions.parquet')
    selected = pd.read_parquet(f6/'predictions.parquet').set_index('pitch_uid')
    pitching = predictions.loc[predictions.family.eq('pitching')]
    if not np.array_equal(pitching[PROBS].to_numpy(),selected.loc[pitching.pitch_uid,['selected_'+c[2:] for c in PROBS]].to_numpy()):
        raise RuntimeError('Final Pitching policy diverges from F4 contact/event source')
    with duckdb.connect(str(dataset.run/'diablos.duckdb'),read_only=True) as db:
        population = db.execute('SELECT pitch_uid, year, game_anon_id, pitcher_anon_id, auto_pitch_type FROM model_base WHERE year=2025').df()
    population = assign_partitions(population,dataset.config)
    if smoke:
        population = sample_games(population,dataset.config['training']['smoke_target_max_pitches'],dataset.config['seed'])
    return f6,f4,predictions,population


def sensitivity(reference, development, family, changes):
    """One weight at a time; each variant has its own calibration scale, no selection."""
    rows = []
    base_ref,_ = utility(reference,S1)
    base_dev,_ = utility(development,S1)
    base = 100+10*(base_dev-base_ref.mean())/base_ref.std(ddof=0)
    for name in ['whiff','called_strike','ball','hit_by_pitch','weak_contact_joint','hard_contact_joint']:
        for change in changes:
            weights,contact = dict(WEIGHTS),[0.5,-1.]
            if name in weights:
                weights[name] *= 1+change
            else:
                contact[0 if name=='weak_contact_joint' else 1] *= 1+change
            ref,_ = utility(reference,S1,weights,contact)
            dev,_ = utility(development,S1,weights,contact)
            if ref.std(ddof=0) <= 1e-12:
                raise ValueError('Degenerate sensitivity reference')
            changed = 100+10*(dev-ref.mean())/ref.std(ddof=0)
            rows.append(dict(family=family,score_version=S1,weight=name,relative_change=change,
                reference_id=ids_hash(reference.pitch_uid.tolist()),development_id=ids_hash(development.pitch_uid.tolist()),
                partition='development',n=len(development),mu=float(ref.mean()),sigma=float(ref.std(ddof=0)),
                mean_absolute_score_change=float(np.abs(changed-base).mean()),max_absolute_score_change=float(np.abs(changed-base).max()),
                spearman_correlation=float(pd.Series(base).corr(pd.Series(changed),method='spearman')),
                selected=False,weights=weights,contact_weights=contact))
    return rows


def build_scores(experiment_id=None, smoke=False):
    tick = time.perf_counter()
    dataset = ModelingDataset()
    cfg = dataset.config
    name = experiment_id or 'f7-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}',name):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root/'artifacts/modeling'/name/'F7'
    folder.mkdir(parents=True,exist_ok=False)
    checks = {}
    manifest = dict(phase_id='F7',experiment_id=name,status='in_progress',smoke=smoke,protocol_id='A',
        data_run=dataset.run_id,data_manifest_sha256=dataset.manifest_hash,test_accessed=False,
        config_sha256=dataset.config_hash,python_executable=sys.executable,virtual_environment=sys.prefix != sys.base_prefix,
        started_utc=datetime.now(timezone.utc).isoformat(),
        code_hashes={str(p.relative_to(ROOT)):sha256_file(p) for p in sorted((ROOT/'modeling').glob('*.py'))+[ROOT/'scripts/check_phase7.py']})
    try:
        f6,f4,predictions,population = sources(dataset,smoke)
        manifest['dependencies'] = {phase:sha256_file(path/'manifest.json') for phase,path in [('F4',f4),('F6',f6)]}
        write_json(folder/'config.json',cfg)
        population.to_parquet(folder/'population.parquet',index=False)
        common = None
        all_scores,experimental,experiments = [],[],[]
        for family in ('stuff','location','pitching'):
            data = predictions.loc[predictions.family.eq(family)].copy()
            require_unique(data)
            reference = data.loc[data.partition.eq('calibration')].sort_values('pitch_uid')
            reference_ids = reference.pitch_uid.tolist()
            if common is None:
                common = reference_ids
                reference[['pitch_uid','year','partition']].to_parquet(folder/'reference_ids.parquet',index=False)
            if common != reference_ids:
                raise RuntimeError('Families do not share the calibration reference')
            # Retain all input rows and expose missing eligible predictions explicitly.
            values = population.merge(data.drop(columns=['year','game_anon_id','pitcher_anon_id','partition']),
                                      on='pitch_uid',how='left',validate='one_to_one')
            values['family'],values['data_version'] = family,dataset.run_id
            values['model_version'] = 'F4_A_'+family+'_calibrated'
            values['index_name'] = family.capitalize()+'+'
            values['model_status'] = 'diagnostic' if family=='stuff' else 'validated'
            values['warnings'] = values.warnings.fillna('outside_common_eligible_cohort')
            for version in (S0,S1):
                if version == S1 and family == 'stuff':
                    unavailable = values.copy()
                    unavailable['utility'],unavailable['score'] = np.nan,np.nan
                    unavailable['score_status'] = 'verified_contact_head_unavailable'
                    unavailable['score_version'],unavailable['score_semantics'] = S1,S1
                    unavailable['reference_id'] = None
                    unavailable['provisional'] = True
                    experimental.append(unavailable)
                    continue
                scale = FixedScale.fit(reference,family,version,dataset.run_id)
                filename = family+'_'+version+'.json'
                scale.save(folder/filename)
                reference_scores = scale.score(reference).score.to_numpy()
                checks[family+'_'+version+'_reference_scale'] = bool(abs(reference_scores.mean()-100)<1e-6 and abs(reference_scores.std(ddof=0)-10)<1e-6)
                result = scale.score(values)
                checks[family+'_'+version+'_reload_batch_invariance'] = bool(np.allclose(
                    FixedScale.load(folder/filename).score(values.iloc[:100]).score,result.score.iloc[:100],equal_nan=True,atol=0,rtol=0))
                checks[family+'_'+version+'_no_infinity'] = bool(~np.isinf(result.score).any())
                checks[family+'_'+version+'_null_reason'] = bool((result.score.isna() == result.score_status.ne('ok')).all())
                (all_scores if version==S0 else experimental).append(result)
                if version == S1:
                    dev = data.loc[data.partition.eq('development') & data.pitch_uid.isin(population.pitch_uid)]
                    experiments.extend(sensitivity(reference,dev,family,cfg['F7']['sensitivity_relative_changes']))
        for label,frames in [('scores',all_scores),('experimental_contact_scores',experimental)]:
            output = pd.concat(frames,ignore_index=True)
            output.to_parquet(folder/(label+'.parquet'),index=False)
            for suffix,keys in [('pitcher',['pitcher_anon_id']),('pitcher_type',['pitcher_anon_id','auto_pitch_type'])]:
                aggregate(output,keys).to_parquet(folder/(label+'_'+suffix+'.parquet'),index=False)
        write_json(folder/'contact_sensitivity.json',experiments)
        scenarios = pd.read_parquet(f6/'simulation_deltas.parquet')
        scenarios = scenarios.loc[scenarios.pitch_uid.isin(population.pitch_uid)].copy()
        scale = FixedScale.load(folder/('pitching_'+S0+'.json'))
        for side in ('source','target'):
            frame = scenarios.rename(columns={side+'_'+p:p for p in PROBS})
            values,_ = utility(frame,S0)
            scenarios[side+'_score'] = scale.transform(values)
        scenarios['delta_score'] = scenarios.target_score-scenarios.source_score
        scenarios['reference_id'],scenarios['score_version'] = scale.metadata['reference_id'],S0
        scenarios['score_semantics'] = S0
        scenarios['score_scope'] = 'experimental_environment_candidate_fixed_shape_not_causal'
        scenarios.to_parquet(folder/'environment_score_deltas.parquet',index=False)
        checks['same_environment_zero_score_delta'] = bool(scenarios.loc[scenarios.source_environment.eq(scenarios.target_environment),'delta_score'].eq(0).all())
        checks['fixed_environment_scale'] = bool(np.allclose(scenarios.delta_score,
            10*(scenarios[['delta_'+p for p in PROBS]].to_numpy() @ np.array([WEIGHTS[p[2:]] for p in PROBS]))/scale.metadata['sigma'],atol=1e-10,equal_nan=True))
        checks['positive_utility_direction'] = bool(np.all(np.diff(scale.transform([-1,0,1]))>0))
        checks['only_2025_outputs'] = bool(population.year.eq(2025).all() and predictions.year.eq(2025).all())
        checks['virtual_environment'] = manifest['virtual_environment']
        write_json(folder/'policy.json',dict(published_score_version=S0,experimental_score_version=S1,
            final_model_policy='F4_A_calibrated; F5 retain_reference; F6 control',reference_id=ids_hash(common),reference_n=len(common),
            reference_scope=cfg['F7']['reference_scope'],normalization='100 + 10*(utility-mu)/sigma; ddof=0',
            population_n=len(population),coverage_denominator=cfg['F7']['coverage_denominator'],
            calibration_is_independent_validation=False,represents_expected_runs=False,provisional=True,
            contact_stuff_status='verified_contact_head_unavailable',test_accessed=False,release_frozen=False))
        dataset.assert_unchanged()
        if not all(checks.values()):
            raise RuntimeError('Failed F7 checks: '+str(checks))
        manifest['status'] = 'verified'
    except Exception as exc:
        manifest.update(status='blocked',error=f'{type(exc).__name__}: {exc}')
        checks['technical_failure'] = False
        raise
    finally:
        write_json(folder/'checks.json',checks)
        manifest.update(elapsed_seconds=time.perf_counter()-tick,finished_utc=datetime.now(timezone.utc).isoformat())
        manifest['artifact_hashes'] = {p.name:sha256_file(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name!='manifest.json'}
        write_json(folder/'manifest.json',manifest)
    print({'path':str(folder),'status':manifest['status'],'reference_n':len(common)},flush=True)
    return folder
