"""Reproduce F6 models, calibration, paired metrics, subgroups and scenario intervals."""
import argparse
import json
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from modeling.baselines import CLASSES
from modeling.datasets import ModelingDataset, ids_hash, pd, sha256_file
from modeling.environment import (ENV, PROBS, EnvironmentEventModel, EnvironmentSimulator,
                                  cohort_delta_interval, training_support)
from modeling.metrics import multiclass_metrics
from modeling.phase4 import compare_head
from modeling.phase6 import load_rows, read, subgroup_metrics, verify_f5
from scripts.check_phase4 import assert_same, check_calibration


def check(experiment):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}',experiment):
        raise ValueError('Invalid experiment')
    dataset = ModelingDataset()
    f5_folder,f4_folder = verify_f5(dataset)
    folder = ROOT/'artifacts/modeling'/experiment/'F6'
    manifest,cfg = read(folder/'manifest.json'),read(folder/'config.json')
    assert manifest['status']=='verified' and not manifest['test_accessed'] and manifest['protocol_id']=='A'
    assert manifest['data_manifest_sha256']==dataset.manifest_hash
    assert manifest['dependencies']=={'F5':sha256_file(f5_folder/'manifest.json'),'F4':sha256_file(f4_folder/'manifest.json')}
    for name,digest in manifest['artifact_hashes'].items():
        path=(folder/name).resolve()
        assert path.is_relative_to(folder.resolve()) and sha256_file(path)==digest,name
    for name,digest in manifest['code_hashes'].items():
        assert sha256_file(ROOT/name)==digest,name
    checks=read(folder/'checks.json')
    assert checks and all(v is True for v in checks.values())
    rows,_=load_rows(dataset,manifest['smoke'])
    pd.testing.assert_frame_equal(rows,pd.read_parquet(folder/'cohort.parquet'))
    training=rows.loc[rows.partition.eq('train')].reset_index(drop=True)
    evaluation=rows.loc[rows.partition.ne('train')].reset_index(drop=True)
    selected={}
    for name in ('control','environment'):
        model=EnvironmentEventModel.load(folder/name/'model')
        assert model.metadata['fit_ids_sha256']==ids_hash(training.pitch_uid.tolist())
        assert model.metadata['development_ids_sha256']==ids_hash(rows.loc[rows.partition.eq('development'),'pitch_uid'].tolist())
        raw=model.predict(evaluation)
        saved=pd.read_parquet(folder/name/'predictions.parquet')
        assert saved.pitch_uid.tolist()==evaluation.pitch_uid.tolist()
        np.testing.assert_array_equal(raw,saved[['raw_'+c for c in CLASSES]].to_numpy())
        chosen,temperature,_=check_calibration(folder/name,evaluation,raw,'y_event',CLASSES,cfg,manifest['smoke'],False)
        # check_calibration independently refits the scalar and checks metrics and bootstrap.
        np.testing.assert_array_equal(chosen,saved[['selected_'+c for c in CLASSES]].to_numpy())
        np.testing.assert_array_equal(temperature,saved[['temperature_'+c for c in CLASSES]].to_numpy())
        selected[name]=saved[['selected_'+c for c in CLASSES]].to_numpy()
        if name=='environment':
            assert_same(training_support(training,model.numeric,cfg['F6']['minimum_support_rows']),
                        read(folder/'environment_support.json'))
    mask=evaluation.partition.eq('phase_review').to_numpy()
    review=evaluation.loc[mask].reset_index(drop=True)
    metrics=read(folder/'metrics.json')
    paired=compare_head(review,'y_event',CLASSES,selected['control'][mask],selected['environment'][mask],cfg,manifest['smoke'])
    assert_same(paired,metrics['comparison'])
    policy=read(folder/'policy.json')
    assert policy['promote_environment']==(metrics['sufficient_for_comparison'] and paired['decision']=='promote')
    for metric in metrics['metrics']:
        part=evaluation.partition.eq(metric['partition']).to_numpy()
        reproduced=multiclass_metrics(evaluation.loc[part,'y_event'],selected[metric['model']][part],CLASSES)
        assert_same(reproduced,{k:metric[k] for k in reproduced})
    public=pd.read_parquet(folder/'predictions.parquet')
    assert public.pitch_uid.tolist()==evaluation.pitch_uid.tolist()
    for name in ('control','environment','selected'):
        matrix=selected[policy['prediction_branch']] if name=='selected' else selected[name]
        np.testing.assert_array_equal(public[[name+'_'+c for c in CLASSES]].to_numpy(),matrix)
    if not manifest['smoke']:
        old=pd.read_parquet(f4_folder/'pitching/event/predictions.parquet').set_index('pitch_uid').loc[evaluation.pitch_uid]
        np.testing.assert_array_equal(old[['selected_'+c for c in CLASSES]].to_numpy(),selected['control'])
    subgroups=subgroup_metrics(training,review,selected['control'][mask],selected['environment'][mask],cfg,manifest['smoke'])
    assert_same(subgroups,read(folder/'subgroup_metrics.json'))
    simulator=EnvironmentSimulator.load(folder)
    pd.testing.assert_frame_equal(simulator.predict(evaluation.drop(columns='y_event')),pd.read_parquet(folder/'input_support.parquet'))
    saved=pd.read_parquet(folder/'simulation_deltas.parquet')
    intervals=[]
    for category in simulator.model.vocabularies[ENV]:
        scenario=simulator.simulate(review.drop(columns='y_event'),category)
        pd.testing.assert_frame_equal(scenario,saved.loc[saved.target_environment.eq(category)].reset_index(drop=True))
        interval=cohort_delta_interval(scenario,review,cfg['evaluation']['bootstrap_smoke' if manifest['smoke'] else 'bootstrap_full'],
            cfg['seed'],cfg['evaluation']['bootstrap_confidence'],cfg['F6']['minimum_support_rows'],manifest['smoke'])
        interval['target_environment']=category
        intervals.append(interval)
    assert_same(intervals,read(folder/'simulation_intervals.json'))
    dataset.assert_unchanged()
    return dict(experiment=experiment,status='verified',checks_passed=len(checks),
        artifact_hashes_verified=len(manifest['artifact_hashes']),prediction_rows=len(public),
        scenario_rows=len(saved),max_prediction_difference=0.0,metrics_reproduced=len(metrics['metrics']),
        subgroups_reproduced=len(subgroups),scenario_intervals_reproduced=len(intervals),
        scientific_decision=metrics['scientific_decision'],test_accessed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=check(args.experiment)
    text=json.dumps(result,indent=2)+'\n'
    if args.output:
        args.output.write_text(text,encoding='utf-8')
    print(text)
