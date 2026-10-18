"""Recompute F10 evidence and exercise the simulator without reading final-test rows."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from modeling.datasets import ROOT, sha256_file, ids_hash
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler
from modeling.metrics import multiclass_metrics, per_pitch_losses
from modeling.release import verify_release
from modeling.models import TabularEventModel
from experiments.phase9 import RELEASE, write
from experiments.phase9_predict import verify_experiment
from experiments.phase10 import paired, F9
from experiments.phase10_models import EventModel, MovementModel
from experiments.phase10_features import Repertoire, REGULARIZED, GEOMETRY, POINTS
from experiments.phase10_simulator import Simulator


def audit(folder):
    folder=Path(folder);manifest=verify_experiment(folder)
    summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    cfg=json.loads((folder/'config.json').read_text(encoding='utf-8'))
    checks={'artifact_hashes':True}
    for name,digest in manifest['source_hashes'].items():
        if sha256_file(ROOT/name)!=digest:raise ValueError('Source changed: '+name)
    if sha256_file(ROOT/'config/phase10.json')!=manifest['config_sha256']:raise ValueError('Config changed')
    checks['source_and_config_hashes']=True
    rows=pd.read_parquet(folder/'cohort.parquet');events=pd.read_parquet(folder/'event_cohort.parquet')
    assert rows.year.isin([2024,2025]).all() and events.year.eq(2025).all()
    assert rows.pitch_uid.is_unique and events.pitch_uid.is_unique
    roles={r:events.loc[events.partition.eq(r)] for r in ('development','calibration','phase_review')}
    for a,b in [('development','calibration'),('development','phase_review'),('calibration','phase_review')]:
        assert not set(roles[a].game_anon_id)&set(roles[b].game_anon_id)
    checks['authorized_years_and_event_game_partitions']=True
    repertoire=Repertoire.load(folder/'repertoire')
    remade=repertoire.transform(rows.loc[rows.year.eq(2025)])
    np.testing.assert_array_equal(remade.pitch_uid,events.pitch_uid)
    np.testing.assert_allclose(remade[REGULARIZED+GEOMETRY+POINTS],events[REGULARIZED+GEOMETRY+POINTS],atol=1e-12,rtol=0)
    checks['repertoire_features_recomputed']=True
    review=roles['phase_review'];prediction=pd.read_parquet(folder/'event_predictions.parquet')
    np.testing.assert_array_equal(review.pitch_uid,prediction.pitch_uid)
    loss={}
    for variant in cfg['event_variants']:
        p=prediction[[variant+'_'+c for c in CLASSES]].to_numpy()
        assert multiclass_metrics(review.y_event,p,CLASSES)==summary['events'][variant]['calibrated']
        loss[variant]=per_pitch_losses(review.y_event,p,CLASSES)[0]
        model=EventModel.load(folder/'events'/variant/'model');scaler=TemperatureScaler.load(folder/'events'/variant/'temperature.json')
        np.testing.assert_array_equal(scaler.transform(model.predict(review.iloc[:100])),p[:100])
        assert model.metadata['fit_ids_sha256']==ids_hash(roles['development'].pitch_uid.tolist())
        assert scaler.state['fit_ids_sha256']==ids_hash(roles['calibration'].pitch_uid.tolist())
    checks['events_metrics_reload_and_fit_ids']=True
    for left,right in zip(cfg['event_variants'][:-1],cfg['event_variants'][1:]):
        assert paired(review,loss[left],loss[right],cfg,summary['smoke'])==summary['comparisons'][right+'_vs_'+left]
    checks['event_bootstraps_recomputed']=True
    f9=pd.read_parquet(F9/'C/review_predictions.parquet')
    joined=prediction.merge(f9,on='pitch_uid',suffixes=('_f10','_f9'),validate='one_to_one')
    assert joined.y_event_f10.equals(joined.y_event_f9)
    assert len(joined)==summary['F9_common_review']['n']
    for old,new in [('context_physics','base'),('arsenal','regularized'),('environment','environment')]:
        for version,name,suffix in [('F9',old,'_f9'),('F10',new,'_f10')]:
            cols=[name+'_'+c+(suffix if name=='environment' else '') for c in CLASSES]
            assert multiclass_metrics(joined.y_event_f9,joined[cols],CLASSES)==summary['F9_common_review']['models'][new][version]
    checks['F9_same_population_metrics_recomputed']=True
    m=pd.read_parquet(folder/'movement_predictions.parquet')
    checks['movement_only_2025_review']=bool(m.year.eq(2025).all() and m.partition.eq('phase_review').all())
    subgroups=[]
    for target in ('induced_vert_break','horz_break'):
        errors={}
        for label in ('control','environment'):
            errors[label]=(m[target+'_'+label].to_numpy()-m[target].to_numpy())**2
            assert float(np.sqrt(errors[label].mean()))==summary['movement'][target][label]['rmse_inches']
            model=MovementModel.load(folder/'movement'/target/label)
            sample=rows.set_index('pitch_uid').loc[m.pitch_uid.iloc[:100]].reset_index()
            np.testing.assert_array_equal(model.predict(sample),m[target+'_'+label].iloc[:100])
        assert paired(m,errors['control'],errors['environment'],cfg,summary['smoke'])==summary['comparisons'][target+'_environment_vs_control']
        for category,idx in m.groupby('altitude_category').groups.items():
            subgroups.append(dict(target=target,category=category,n=len(idx),control_rmse=float(np.sqrt(errors['control'][idx].mean())),environment_rmse=float(np.sqrt(errors['environment'][idx].mean()))))
    checks['movement_metrics_reload_bootstraps']=True
    simulator=Simulator(folder)
    scenarios=json.loads((folder/'scenarios.json').read_text(encoding='utf-8'))
    valid=[r for r in scenarios if r['status']=='experimental']
    assert valid
    # Reproduce saved records using only outcome-free features.
    sample_records=valid[:5]
    for result in sample_records:
        input_row=rows.loc[rows.pitch_uid.eq(result['pitch_uid'])].drop(columns=['y_event','year','partition']).to_dict('records')
        reproduced=simulator.simulate(input_row,result['target'])[0]
        for field in ('source_score','target_score','delta_score','target_ivb','target_hb'):
            np.testing.assert_allclose(reproduced[field],result[field],atol=1e-9,rtol=0)
        same=simulator.simulate(input_row,result['source'])[0]
        assert abs(same['delta_score'])<1e-12
        assert simulator.simulate(input_row,'Harp Helu')[0]['status']=='unsupported'
        bad=dict(input_row[0],rel_speed=-1)
        assert simulator.simulate([bad],result['target'])[0]['status']=='invalid_input'
    assert simulator.simulate([], 'No Altitude')==[]
    checks['simulator_outcome_free_same_category_invalid_unknown']=True
    checks['F8_unchanged']=verify_release(RELEASE)['release_id']==summary['release_id']
    verify_experiment(F9)
    checks['F9_unchanged']=sha256_file(F9/'manifest.json')==manifest['F9_manifest_sha256']
    checks['test_access_unchanged']=all(sha256_file(ROOT/'artifacts/modeling'/name)==digest for name,digest in manifest['exposure_hashes'].items())
    frozen=TabularEventModel.load(RELEASE/'models/pitching/event/model')
    p=frozen.predict(review)
    policy=json.loads((RELEASE/'models/pitching/event/calibration_policy.json').read_text(encoding='utf-8'))
    if policy['route']=='temperature':p=TemperatureScaler.load(RELEASE/'models/pitching/event/temperature.json').transform(p)
    production_metrics=multiclass_metrics(review.y_event,p,CLASSES)
    checks['F8_pitching_comparison_2025_only']=bool(review.year.eq(2025).all())
    assert all(checks.values())
    return dict(checks=checks,movement_by_altitude=subgroups,manifest_sha256=sha256_file(folder/'manifest.json'),n_saved_supported_scenarios=len(valid),F8_pitching_same_review=production_metrics)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=audit(args.experiment);write(args.output,result);print(json.dumps(result,indent=2))
