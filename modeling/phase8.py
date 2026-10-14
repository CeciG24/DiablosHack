"""Frozen-release checks on 2025, followed by a logged, non-selective 2026 report."""
import argparse
from pathlib import Path
import platform
import time
import numpy as np
import pandas as pd
from modeling.datasets import ROOT, FEATURES, META, PITCHING, FLAGS, duckdb, ids_hash, select_family
from modeling.baselines import EventBaseline, CLASSES
from modeling.calibration import TemperatureScaler
from modeling.contact import derive_targets, TARGET_COLUMNS, HEADS, head_metrics
from modeling.environment import EnvironmentEventModel, EnvironmentSimulator
from modeling.inference import ReleasePredictor
from modeling.metrics import multiclass_metrics, calibration_bins, per_pitch_losses, paired_bootstrap
from modeling.release import freeze, authorize_test, verify_release, read, write
from modeling.scoring import PROBS, aggregate


def diagnostic_simulator(folder):
    folder=Path(folder)
    policy=read(folder/'environment/calibration_policy.json')
    scaler=TemperatureScaler.load(folder/'environment/temperature.json') if policy['route']=='temperature' else None
    return EnvironmentSimulator(EnvironmentEventModel.load(folder/'environment/model'),scaler,False)


def smoke(folder):
    """Before opening test, reproduce 2025 output and exercise invalid mixed inputs."""
    predictor=ReleasePredictor(folder)
    cfg=read(Path(folder)/'config.json')
    f6=ROOT/'artifacts/modeling'/cfg['F7']['f6_reference_experiment']/'F6'
    f4=ROOT/'artifacts/modeling'/cfg['F5']['f4_reference_experiment']/'F4'
    cohort=pd.read_parquet(f6/'cohort.parquet')
    rows=cohort.loc[cohort.partition.eq('phase_review')].head(1000).copy()
    expected=pd.read_parquet(f4/'predictions.parquet')
    checks={}
    timings=[]
    reloaded=ReleasePredictor(folder)
    for family in FEATURES:
        actual=predictor.predict(rows,family)
        known=expected.loc[expected.family.eq(family)].set_index('pitch_uid').loc[rows.pitch_uid]
        cols=PROBS+['p_weak_given_in_play','p_hard_given_in_play','p_groundball_given_in_play','p_chase_given_outside']
        checks[family+'_2025_probability_reproduction']=bool(np.allclose(actual[cols],known[cols],atol=1e-12,rtol=0))
        again=reloaded.predict(rows,family)
        checks[family+'_reload_exact']=actual.equals(again)
        checks[family+'_batch_invariance']=bool(np.allclose(predictor.predict(rows.iloc[[0]],family)[PROBS],actual.iloc[[0]][PROBS],atol=1e-12))
        duration=[]
        for _ in range(3):
            start=time.perf_counter();predictor.predict(rows,family);duration.append(time.perf_counter()-start)
        timings.append(dict(family=family,batch_size=len(rows),repetitions=3,warm_seconds=duration,median_seconds=float(np.median(duration))))
    mixed=pd.concat([rows.head(1)]*6,ignore_index=True)
    mixed.loc[1,'rel_speed']=np.nan
    mixed.loc[2,'auto_pitch_type']='NeverSeenType'
    mixed.loc[3,'pitcher_anon_id']='NeverSeenPitcher'
    mixed.loc[4,'balls']=4
    mixed.loc[5,'altitude_category']='UnknownAltitude'
    result=predictor.predict(mixed)
    checks['mixed_preserves_rows_and_duplicate_ids']=len(result)==6 and result.pitch_uid.tolist()==mixed.pitch_uid.tolist()
    checks['invalid_rows_null']=bool(result.loc[[1,4],'status'].eq('invalid_input').all() and result.loc[[1,4],PROBS+['score']].isna().all().all())
    checks['unseen_category_warned']=result.loc[2,'status']=='ok' and 'unknown_category' in result.loc[2,'warnings']
    checks['unseen_pitcher_base']=result.loc[3,'status']=='ok' and 'requires_no_history' in result.loc[3,'warnings']
    checks['unknown_environment_base_ignored']=result.loc[5,'status']=='ok' and 'ignored_by_base' in result.loc[5,'warnings']
    checks['unknown_environment_simulator_rejected']=diagnostic_simulator(folder).predict(mixed.iloc[[5]]).status.iloc[0]=='unsupported_environment'
    checks['unsupported_model']=predictor.predict(rows.head(1),'unknown').status.iloc[0]=='unsupported_model'
    checks['no_outcomes_required']=predictor.predict(rows[PITCHING].head(2)).status.eq('ok').all().item()
    checks['empty_batch']=predictor.predict([]).empty
    write(Path(folder)/'pretest_checks.json',checks)
    write(Path(folder)/'benchmark.json',dict(hardware=dict(platform=platform.platform(),processor=platform.processor(),machine=platform.machine()),
        threads=4,scope='warm_local_batch_including_auxiliary_heads_no_network_no_load',results=timings))
    if not all(checks.values()):raise RuntimeError('Pretest checks failed: '+str(checks))
    print({'pretest':'verified','checks':len(checks)},flush=True)
    return checks


def load_test(folder,release_id,reproduce=False):
    dataset,lock=authorize_test(folder,release_id,reproduce)
    columns=list(dict.fromkeys(META[:-1]+PITCHING+['altitude_category']+sum(FLAGS.values(),[])+['y_event']+TARGET_COLUMNS))
    with duckdb.connect(str(dataset.run/'diablos.duckdb'),read_only=True) as db:
        rows=db.execute('SELECT '+', '.join('"'+c+'"' for c in columns)+' FROM model_base WHERE year=2026').df()
    rows['partition']='test'
    dataset.assert_unchanged()
    return dataset,rows.sort_values('pitch_uid').reset_index(drop=True)


def evaluate(folder,release_id,reproduce=False):
    folder=Path(folder)
    lock=verify_release(folder,release_id)
    checks=read(folder/'pretest_checks.json')
    if not checks or not all(v is True for v in checks.values()):raise PermissionError('Successful pretest required')
    output=folder/('evaluation_reproduction_'+str(time.time_ns()) if reproduce else 'evaluation')
    output.mkdir(exist_ok=False)
    start=time.perf_counter()
    # All source and policy hashes are checked before any final-year query.
    dataset,rows=load_test(folder,release_id,reproduce)
    cfg=read(folder/'config.json')
    predictor=ReleasePredictor(folder,release_id)
    common=set(rows.pitch_uid)
    exclusions={}
    for family in FEATURES:
        eligible,exclusions[family]=select_family(rows,family,'y_event')
        common &= set(eligible.pitch_uid)
    common_mask=rows.pitch_uid.isin(common)
    evaluation=rows.loc[common_mask].copy().reset_index(drop=True)
    if evaluation.empty:raise RuntimeError('No common eligible test rows')
    evaluation['unseen_training']=~evaluation.pitcher_anon_id.isin(predictor.support['pitchers'])
    evaluation['unseen_development']=~evaluation.pitcher_anon_id.isin(predictor.support['pitchers_seen_development'])
    evaluation.to_parquet(output/'evaluation_cohort.parquet',index=False)
    rows[['pitch_uid','year','game_anon_id','pitcher_anon_id','auto_pitch_type','altitude_category']].to_parquet(output/'population.parquet',index=False)
    metrics,calibration,head_results,subgroups=[],[],[],[]
    matrices={}
    all_scores=[]
    coverage={}
    for family in FEATURES:
        print('Evaluating frozen '+family,flush=True)
        prediction=predictor.predict(rows,family)
        prediction['in_common_evaluation_cohort']=common_mask.to_numpy()
        prediction['year'],prediction['partition']=2026,'test'
        for c in ('game_anon_id','pitcher_anon_id','auto_pitch_type','altitude_category'):prediction[c]=rows[c].to_numpy()
        prediction.to_parquet(output/(family+'_inference.parquet'),index=False)
        selected=prediction.loc[common_mask].copy().reset_index(drop=True)
        assert selected.status.eq('ok').all()
        matrices[family]=selected[PROBS].to_numpy()
        score=prediction.copy()
        score.loc[~common_mask,PROBS+['score',family+'_plus']]=np.nan
        score.loc[~common_mask,'score_status']='outside_common_evaluation_cohort'
        all_scores.append(score)
        coverage[family]=dict(n_total=len(rows),n_inference_valid=int(prediction.status.eq('ok').sum()),
            n_common_evaluation=len(evaluation),common_coverage=len(evaluation)/len(rows),exclusions=exclusions[family])
        labels=derive_targets(evaluation)
        for head,classes in HEADS.items():
            cols=['p_'+c+'_given_in_play' for c in classes] if head=='contact' else ['p_'+('groundball_given_in_play' if head=='groundball' else 'chase_given_outside')]
            q=selected[cols].to_numpy()
            if head!='contact':q=np.column_stack([1-q[:,0],q[:,0]])
            valid=labels[head].notna().to_numpy() & np.isfinite(q).all(axis=1)
            head_results.append(dict(family=family,head=head,n_valid=int(valid.sum()),n_missing=int((~valid).sum()),
                metrics=head_metrics(labels.loc[valid,head],q[valid],classes) if valid.any() else None,
                route=predictor.heads[family][head][0]['route'],semantics='conditional_not_run_value'))
    baseline=EventBaseline.load(folder/'B1.json')
    matrices['B1']=baseline.predict(evaluation)[0]
    env=diagnostic_simulator(folder).predict(evaluation)
    env.to_parquet(output/'environment_diagnostic.parquet',index=False)
    matrices['environment']=env[PROBS].to_numpy()
    for name,p in matrices.items():
        valid=np.isfinite(p).all(axis=1)
        metrics.append(dict(model=name,**multiclass_metrics(evaluation.loc[valid,'y_event'],p[valid],CLASSES),
                            excluded=int((~valid).sum())))
        calibration.extend(dict(model=name,**bin) for bin in calibration_bins(evaluation.loc[valid,'y_event'],p[valid],CLASSES))
        for group in ('unseen_training','unseen_development','altitude_category'):
            for value,part in evaluation.groupby(group,dropna=False):
                positions=part.index.to_numpy();positions=positions[valid[positions]]
                enough=len(positions)>=200 and evaluation.loc[positions,'y_event'].value_counts().reindex(CLASSES,fill_value=0).min()>=20
                subgroups.append(dict(model=name,group=group,value=str(value),n_total=len(part),n_valid=len(positions),
                    status='descriptive_sufficient' if enough else 'insufficient_support',
                    metrics=multiclass_metrics(evaluation.loc[positions,'y_event'],p[positions],CLASSES) if len(positions) else None))
    comparisons=[]
    for reference,candidate in cfg['F8']['comparisons']:
        valid=np.isfinite(matrices[reference]).all(axis=1)&np.isfinite(matrices[candidate]).all(axis=1)
        pair=[]
        for name in (reference,candidate):
            f=evaluation.loc[valid,['pitch_uid','game_anon_id','y_event']].copy()
            f['loss']=per_pitch_losses(f.y_event,matrices[name][valid],CLASSES)[0];pair.append(f)
        result=paired_bootstrap(*pair,cfg['evaluation']['bootstrap_full'],cfg['seed'])
        result['decision']='report_only_no_selection'
        comparisons.append(dict(reference=reference,candidate=candidate,**result))
    scores=pd.concat(all_scores,ignore_index=True)
    scores.to_parquet(output/'scores.parquet',index=False)
    for suffix,by in [('pitcher',['pitcher_anon_id']),('pitcher_type',['pitcher_anon_id','auto_pitch_type'])]:
        aggregate(scores,by).to_parquet(output/(suffix+'_aggregates.parquet'),index=False)
    pitcher_counts=evaluation.groupby('pitcher_anon_id').size().rename('n').reset_index().sort_values(['n','pitcher_anon_id'],ascending=[False,True]).head(3)
    cases=[]
    for pid in pitcher_counts.pitcher_anon_id:
        selected=scores.loc[scores.pitcher_anon_id.eq(pid)]
        cases.append(dict(pitcher_anon_id=pid,selection='three_largest_common_pitch_counts_tie_ID_no_outcomes',
            evidence=aggregate(selected,['pitcher_anon_id','auto_pitch_type']).replace({np.nan:None}).to_dict('records'),
            interpretation='Observed mix, provisional event utility. Review probabilities and coverage; no causal recommendation.',
            unseen_training=pid not in predictor.support['pitchers']))
    write(output/'scouting_cases.json',cases)
    write(output/'metrics.json',dict(metrics=metrics,comparisons=comparisons,auxiliary=head_results,selection_on_test=False))
    write(output/'subgroups.json',subgroups)
    write(output/'calibration.json',calibration)
    write(output/'coverage.json',coverage)
    final_checks=dict(release_unchanged=verify_release(folder,release_id)['release_id']==release_id,
        no_model_selection=True,only_2026=bool(rows.year.eq(2026).all()),
        all_rows_preserved=all(v['n_total']==len(rows) for v in coverage.values()),
        common_probabilities_finite=all(np.isfinite(matrices[f]).all() for f in FEATURES),
        no_infinite_scores=bool(~np.isinf(scores.score).any()),three_scouting_cases=len(cases)==3)
    if not all(final_checks.values()):raise RuntimeError('Final evaluation checks failed')
    dataset.assert_unchanged()
    from modeling.datasets import sha256_file
    manifest=dict(status='verified',release_id=release_id,test_accessed=True,reproduction=reproduce,
        n_total=len(rows),n_common=len(evaluation),common_ids_sha256=ids_hash(evaluation.pitch_uid.tolist()),
        elapsed_seconds=time.perf_counter()-start,checks=final_checks,
        artifact_hashes={p.name:sha256_file(p) for p in output.iterdir() if p.is_file()})
    write(output/'manifest.json',manifest)
    print({'evaluation':str(output),'status':'verified','n_common':len(evaluation)},flush=True)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['freeze','smoke','evaluate'])
    parser.add_argument('--name')
    parser.add_argument('--release')
    parser.add_argument('--release-id')
    parser.add_argument('--reproduce',action='store_true')
    args=parser.parse_args()
    if args.action=='freeze':
        if not args.name:parser.error('--name required')
        freeze(args.name)
    else:
        if not args.release:parser.error('--release required')
        if args.action=='smoke':smoke(args.release)
        else:
            if not args.release_id:parser.error('--release-id required')
            evaluate(args.release,args.release_id,args.reproduce)


if __name__=='__main__':main()
