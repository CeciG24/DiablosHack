"""F10: regularized arsenal, geometry and categorical movement transport."""
import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from modeling.datasets import ROOT, META, ModelingDataset, duckdb, ids_hash, sha256_file
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler
from modeling.metrics import multiclass_metrics, per_pitch_losses, calibration_bins
from modeling.release import verify_release
from experiments.phase9 import engineer, write, RELEASE, standardized_probabilities, UTILITY, diagnostics
from experiments.phase9_predict import verify_experiment
from experiments.phase10_features import trajectory, COEFFICIENTS, PHYS, Repertoire
from experiments.phase10_models import EventModel, MovementModel, movement_support
from experiments.phase10_simulator import Simulator

F9=ROOT/'artifacts/modeling/f9-full/F9'
CATEGORIES=['No Altitude','Medium Altitude','Extreme Altitude']


def paired(rows, reference_loss, candidate_loss, cfg, smoke=False):
    """Paired mean-loss difference, whole-game percentile bootstrap."""
    if len(rows)!=len(reference_loss) or len(rows)!=len(candidate_loss) or rows.empty or not rows.pitch_uid.is_unique:
        raise ValueError('Invalid paired population')
    if not np.isfinite(reference_loss).all() or not np.isfinite(candidate_loss).all():raise ValueError('Invalid losses')
    frame=pd.DataFrame(dict(game=rows.game_anon_id.to_numpy(),delta=np.asarray(candidate_loss)-np.asarray(reference_loss)))
    g=frame.groupby('game').delta.agg(['sum','size'])
    if len(g)<2:raise ValueError('Two games required')
    rng=np.random.default_rng(cfg['seed']); draws=[]
    sums,n=g['sum'].to_numpy(),g['size'].to_numpy()
    for _ in range(20 if smoke else cfg['bootstrap_repetitions']):
        index=rng.integers(0,len(g),size=len(g));draws.append(float(sums[index].sum()/n[index].sum()))
    delta=float(frame.delta.mean());baseline=float(np.mean(reference_loss));tail=(1-cfg['confidence'])/2
    low,high=np.quantile(draws,[tail,1-tail]); improvement=-delta/baseline if baseline>0 else None
    return dict(n=len(rows),games=len(g),delta=delta,relative_improvement=improvement,ci_low=float(low),ci_high=float(high),
        confidence=cfg['confidence'],resamples=len(draws),passes=bool(not smoke and improvement is not None and improvement>=cfg['minimum_relative_improvement'] and high<0),production_promotion=False,
        scope='exploratory_reused_development_data_fixed_model_game_bootstrap')


def load_rows(dataset, smoke):
    data=dataset.load(maximum=20000 if smoke else None)
    rows=data['aligned']['pitching']
    columns=['pitch_uid','year','pitcher_anon_id','auto_pitch_type','pitcher_throws','altitude_category','extension','plate_loc_height','plate_loc_side','zone_time']+PHYS+COEFFICIENTS
    columns=list(dict.fromkeys(columns))
    with duckdb.connect(str(dataset.run/'diablos.duckdb'),read_only=True) as db:
        raw=db.execute('SELECT '+','.join(columns)+' FROM pitches WHERE year IN (2024,2025)').df()
    extra=[c for c in raw if c not in rows.columns or c=='pitch_uid']
    rows=rows.merge(raw[extra],on='pitch_uid',validate='one_to_one')
    return rows,raw.loc[raw.year.eq(2024)].copy(),data['exclusions']


def run(name, smoke=False):
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',name):raise ValueError('Invalid experiment name')
    cfg=json.loads((ROOT/'config/phase10.json').read_text(encoding='utf-8'))
    folder=ROOT/'artifacts/modeling'/name/'F10';folder.mkdir(parents=True,exist_ok=False)
    write(folder/'config.json',cfg)
    verify_experiment(F9);release_id=verify_release(RELEASE)['release_id']
    exposure={p.name:sha256_file(p) for p in [ROOT/'artifacts/modeling/test_exposure.json',ROOT/'artifacts/modeling/test_access.jsonl']}
    dataset=ModelingDataset();rows,history,exclusions=load_rows(dataset,smoke)
    history,audit=trajectory(history,cfg,audit=True);rows,row_audit=trajectory(rows,cfg)
    write(folder/'trajectory_audit.json',dict(training=audit,cohort=row_audit))
    print(f'F10 trajectory audit: {audit["coverage"]:.2%} valid history rows',flush=True)
    repertoire=Repertoire(cfg['prior_strength']).fit(history);repertoire.save(folder/'repertoire')
    rows=engineer(rows);rows.to_parquet(folder/'cohort.parquet',index=False)
    enriched=repertoire.transform(rows.loc[rows.year.eq(2025)])
    enriched.to_parquet(folder/'event_cohort.parquet',index=False)
    train=enriched.loc[enriched.partition.eq('development')];cal=enriched.loc[enriched.partition.eq('calibration')];review=enriched.loc[enriched.partition.eq('phase_review')]
    if min(len(train),len(cal),len(review))==0:raise ValueError('Missing event partition')
    summary=dict(version=cfg['version'],smoke=smoke,new_2026_access=False,release_id=release_id,checks={},events={},comparisons={},movement={},
        coverage=exclusions,event_partitions={k:dict(n=len(v),games=v.game_anon_id.nunique(),ids_sha256=ids_hash(v.pitch_uid.tolist())) for k,v in [('development',train),('calibration',cal),('review',review)]},
        history_coverage=review.groupby('history_status').size().to_dict(),trajectory_audit=audit)
    predictions=review[META+['y_event','history_status','history_n','geometry_valid']].copy()
    event_models={};losses={}
    for variant in cfg['event_variants']:
        print(f'F10 events/{variant}: train={len(train)} review={len(review)}',flush=True)
        dest=folder/'events'/variant;dest.mkdir(parents=True)
        model=EventModel(variant,cfg['seed'],cfg['threads']).fit_f10(train,cfg,smoke);model.save(dest/'model')
        raw=model.predict(review);scaler=TemperatureScaler(CLASSES).fit(cal,model.predict(cal),'y_event');scaler.save(dest/'temperature.json')
        p=scaler.transform(raw)
        summary['checks'][variant+'_reload']=bool(np.array_equal(raw,EventModel.load(dest/'model').predict(review)))
        summary['events'][variant]=dict(raw=multiclass_metrics(review.y_event,raw,CLASSES),calibrated=multiclass_metrics(review.y_event,p,CLASSES),temperature=scaler.temperature)
        losses[variant]=per_pitch_losses(review.y_event,p,CLASSES)[0]
        diagnostics(review,p,variant,dest)
        predictions[[variant+'_'+c for c in CLASSES]]=p
        event_models[variant]=(model,scaler)
    for left,right in zip(cfg['event_variants'][:-1],cfg['event_variants'][1:]):
        summary['comparisons'][right+'_vs_'+left]=paired(review,losses[left],losses[right],cfg,smoke)
    predictions.to_parquet(folder/'event_predictions.parquet',index=False)
    # Retrospective F9 comparison on exact shared IDs, not a matched training ablation.
    f9pred=pd.read_parquet(F9/'C/review_predictions.parquet')
    joined=predictions.merge(f9pred,on='pitch_uid',suffixes=('_f10','_f9'),validate='one_to_one')
    summary['F9_common_review']=dict(n=len(joined),comparison='descriptive_different_training_populations',models={})
    for old,new in [('context_physics','base'),('arsenal','regularized'),('environment','environment')]:
        oldcols=[old+'_'+c+('_f9' if old=='environment' else '') for c in CLASSES]
        newcols=[new+'_'+c+('_f10' if new=='environment' else '') for c in CLASSES]
        summary['F9_common_review']['models'][new]=dict(F9=multiclass_metrics(joined.y_event_f9,joined[oldcols],CLASSES),F10=multiclass_metrics(joined.y_event_f10,joined[newcols],CLASSES))
    # Cold-start is a feature-level diagnostic on the same review outcomes, not unseen-identity validation.
    cold=repertoire.transform(rows.loc[rows.partition.eq('phase_review')],cold_start=True)
    model,scaler=event_models['regularized']
    summary['cold_start_diagnostic']=multiclass_metrics(cold.y_event,scaler.transform(model.predict(cold)),CLASSES)
    known=set(history.pitcher_anon_id.dropna())
    unseen=~review.pitcher_anon_id.isin(known)
    summary['unseen_2024_pitchers']=dict(n=int(unseen.sum()),pitchers=int(review.loc[unseen,'pitcher_anon_id'].nunique()),metrics={})
    for variant in cfg['event_variants']:
        if unseen.any(): summary['unseen_2024_pitchers']['metrics'][variant]=multiclass_metrics(review.loc[unseen,'y_event'],predictions.loc[unseen,[variant+'_'+c for c in CLASSES]],CLASSES)
    # Only these movement learners are fit in 2024; review 2025 is untouched by their fitting.
    mtrain=rows.loc[rows.partition.eq('train') & rows.altitude_category.isin(CATEGORIES)]
    mreview=rows.loc[rows.partition.eq('phase_review') & rows.altitude_category.isin(CATEGORIES)]
    support=movement_support(mtrain,cfg);write(folder/'movement_support.json',support)
    movement_predictions=mreview[META+['auto_pitch_type','pitcher_throws','altitude_category','induced_vert_break','horz_break']].copy()
    for target in ('induced_vert_break','horz_break'):
        summary['movement'][target]={};errors={}
        for env in (False,True):
            label='environment' if env else 'control'
            print(f'F10 movement/{target}/{label}: train={len(mtrain)} review={len(mreview)}',flush=True)
            model=MovementModel(target,env,cfg['seed'],cfg['threads']).fit_f10(mtrain,cfg,smoke)
            dest=folder/'movement'/target/label;model.save(dest)
            p=model.predict(mreview);errors[label]=(p-mreview[target].to_numpy())**2
            movement_predictions[target+'_'+label]=p
            new=~mreview.pitcher_anon_id.isin(set(mtrain.pitcher_anon_id))
            summary['movement'][target][label]=dict(n=len(p),rmse_inches=float(np.sqrt(errors[label].mean())),mae_inches=float(np.abs(p-mreview[target]).mean()),unseen_pitcher_n=int(new.sum()),unseen_pitcher_rmse_inches=float(np.sqrt(errors[label][new].mean())) if new.any() else None)
            summary['checks'][target+'_'+label+'_reload']=bool(np.array_equal(p,MovementModel.load(dest).predict(mreview)))
        summary['comparisons'][target+'_environment_vs_control']=paired(mreview,errors['control'],errors['environment'],cfg,smoke)
    movement_predictions.to_parquet(folder/'movement_predictions.parquet',index=False)
    print('F10 fixed-context calibration reference',flush=True)
    distribution=json.loads((F9/'context_distribution.json').read_text(encoding='utf-8'));write(folder/'context_distribution.json',distribution)
    model,scaler=event_models['regularized']
    refp=standardized_probabilities(model,scaler,cal,distribution);value=refp@UTILITY
    sigma=float(value.std());mu=float(value.mean())
    if not np.isfinite(sigma) or sigma<=1e-12:raise ValueError('Degenerate fixed score reference')
    write(folder/'scale.json',dict(version=cfg['score_version'],mu=mu,sigma=sigma,reference_n=len(cal),reference_ids_sha256=ids_hash(cal.pitch_uid.tolist()),represents_runs=False,weights=UTILITY.tolist()))
    print('F10 supported categorical scenarios',flush=True)
    simulator=Simulator(folder,verify=False)
    sample=rows.loc[rows.partition.eq('phase_review')].sort_values('pitch_uid').head(80 if smoke else cfg['scenario_sample_max'])
    scenarios=[]
    for category in CATEGORIES:
        scenarios+=simulator.simulate(sample.to_dict('records'),category)
    write(folder/'scenarios.json',scenarios)
    scenario_frame=pd.DataFrame(scenarios)
    summaries=[]
    for (source,target),group in scenario_frame.groupby(['source','target']):
        valid=group.loc[group.status.eq('experimental')]
        row=dict(source=source,target=target,n_requested=len(group),n_supported=len(valid),mean_delta_score=float(valid.delta_score.mean()) if len(valid) else None,
                 scope='fixed_model_supported_sample_association_not_causal_not_Harp')
        if len(valid)>1:
            selected=sample.set_index('pitch_uid').loc[valid.pitch_uid].reset_index()
            # Bootstrap an average delta, no promotion interpretation for scenarios.
            if selected.game_anon_id.nunique()>=2:
                ci=paired(selected,np.ones(len(valid)),1+valid.delta_score.to_numpy(float),cfg,smoke)
                row.update(ci_low=ci['ci_low'],ci_high=ci['ci_high'],confidence=ci['confidence'])
            else:
                row['interval_status']='insufficient_games'
        summaries.append(row)
    summary['scenarios']=summaries
    same=scenario_frame.loc[scenario_frame.source.eq(scenario_frame.target)&scenario_frame.status.eq('experimental')]
    summary['checks']['same_category_zero_delta']=bool(len(same)>0 and np.allclose(same.delta_score,0,atol=1e-12))
    summary['checks']['F8_unchanged']=verify_release(RELEASE)['release_id']==release_id
    verify_experiment(F9);summary['checks']['F9_unchanged']=True
    summary['checks']['test_access_unchanged']=all(sha256_file(ROOT/'artifacts/modeling'/n)==h for n,h in exposure.items())
    summary['checks']['reference_normalization']=bool(np.isclose((100+10*(value-mu)/sigma).mean(),100) and np.isclose((100+10*(value-mu)/sigma).std(),10))
    dataset.assert_unchanged()
    if not all(summary['checks'].values()):raise AssertionError('F10 checks failed')
    write(folder/'summary.json',summary)
    write(folder/'manifest.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),data_run=dataset.run_id,data_manifest_sha256=dataset.manifest_hash,
        F9_manifest_sha256=sha256_file(F9/'manifest.json'),exposure_hashes=exposure,config_sha256=sha256_file(ROOT/'config/phase10.json'),
        source_hashes={str(p.relative_to(ROOT)).replace('\\','/'):sha256_file(p) for p in sorted((ROOT/'experiments').glob('phase10*.py'))},
        artifacts={str(p.relative_to(folder)).replace('\\','/'):sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file()}))
    print(str(folder),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True);parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args();run(args.name,args.smoke)
