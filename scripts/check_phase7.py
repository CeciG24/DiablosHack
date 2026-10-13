"""Independently reproduce F7 formulas, fixed references and coverage aggregates."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from modeling.datasets import ROOT, ModelingDataset, ids_hash, sha256_file
from modeling.phase7 import sources
from modeling.scoring import S0,S1,PROBS


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def formula(frame,version):
    value=frame.p_whiff+frame.p_called_strike-.5*frame.p_ball-frame.p_hit_by_pitch
    if version==S1:
        value=value+frame.p_in_play*(.5*frame.p_weak_given_in_play-frame.p_hard_given_in_play)
    return value.to_numpy()


def check(name):
    folder=ROOT/'artifacts/modeling'/name/'F7'
    if not folder.resolve().is_relative_to((ROOT/'artifacts/modeling').resolve()):
        raise ValueError('Invalid experiment')
    manifest=read(folder/'manifest.json')
    assert manifest['status']=='verified' and manifest['test_accessed'] is False
    for filename,digest in manifest['artifact_hashes'].items():
        path=(folder/filename).resolve()
        assert path.is_relative_to(folder.resolve()) and sha256_file(path)==digest
    for filename,digest in manifest['code_hashes'].items():
        assert sha256_file(ROOT/filename)==digest,filename
    dataset=ModelingDataset()
    f6,f4,predictions,population=sources(dataset,manifest['smoke'])
    saved=read(folder/'config.json')
    for key in ('score','F7','protocol_A','seed'):
        assert saved[key]==dataset.config[key]
    assert manifest['data_manifest_sha256']==dataset.manifest_hash
    for phase,path in [('F4',f4),('F6',f6)]:
        assert manifest['dependencies'][phase]==sha256_file(path/'manifest.json')
    pd.testing.assert_frame_equal(population,pd.read_parquet(folder/'population.parquet'))
    ids=pd.read_parquet(folder/'reference_ids.parquet')
    assert ids.year.eq(2025).all() and ids.partition.eq('calibration').all()
    reference_hash=ids_hash(ids.pitch_uid.tolist())
    policy=read(folder/'policy.json')
    assert policy['reference_id']==reference_hash and policy['published_score_version']==S0
    counts={}
    for label,version in [('scores',S0),('experimental_contact_scores',S1)]:
        output=pd.read_parquet(folder/(label+'.parquet'))
        assert len(output)==3*len(population) and not output.duplicated(['family','pitch_uid']).any()
        assert output.score_version.eq(version).all()
        for family in ('stuff','location','pitching'):
            data=predictions.loc[predictions.family.eq(family)].set_index('pitch_uid')
            actual=output.loc[output.family.eq(family)].set_index('pitch_uid')
            assert set(actual.index)==set(population.pitch_uid)
            known=actual.index.intersection(data.index)
            np.testing.assert_array_equal(actual.loc[known,PROBS],data.loc[known,PROBS])
            if version==S1 and family=='stuff':
                assert actual.score.isna().all() and actual.score_status.eq('verified_contact_head_unavailable').all()
                continue
            ref=data.loc[data.partition.eq('calibration')]
            assert ids_hash(ref.index.tolist())==reference_hash
            normal=read(folder/(family+'_'+version+'.json'))
            ref_values=formula(ref,version)
            np.testing.assert_allclose([normal['mu'],normal['sigma']],[ref_values.mean(),ref_values.std(ddof=0)],atol=1e-14,rtol=0)
            assert normal['sigma']>1e-12 and normal['ddof']==0 and normal['reference_id']==reference_hash
            z=100+10*(ref_values-normal['mu'])/normal['sigma']
            np.testing.assert_allclose([z.mean(),z.std(ddof=0)],[100,10],atol=1e-6)
            expected=100+10*(formula(data.loc[known],version)-normal['mu'])/normal['sigma']
            np.testing.assert_allclose(actual.loc[known,'score'],expected,atol=1e-12,rtol=0)
            missing=actual.index.difference(known)
            assert actual.loc[missing,'score'].isna().all() and actual.loc[missing,'score_status'].ne('ok').all()
            assert not np.isinf(actual.score).any()
        for suffix,by in [('pitcher',['pitcher_anon_id']),('pitcher_type',['pitcher_anon_id','auto_pitch_type'])]:
            keys=['family','score_version','reference_id','partition']+by
            grouped=output.groupby(keys,dropna=False)
            expected=grouped.score.agg(['size','count','mean']).reset_index().rename(columns={'size':'n_total','count':'n_valid','mean':'score'})
            actual=pd.read_parquet(folder/(label+'_'+suffix+'.parquet'))
            joined=actual.merge(expected,on=keys,validate='one_to_one',suffixes=('_actual','_expected'))
            assert len(joined)==len(expected)==len(actual)
            for c in ('n_total','n_valid','score'):
                np.testing.assert_allclose(joined[c+'_actual'],joined[c+'_expected'],atol=1e-12,rtol=0,equal_nan=True)
            np.testing.assert_allclose(actual.coverage,actual.n_valid/actual.n_total)
            assert actual.loc[actual.n_valid.eq(0),'score_status'].eq('no_valid_predictions').all()
        counts[label]=len(output)
    scenarios=pd.read_parquet(folder/'environment_score_deltas.parquet')
    original=pd.read_parquet(f6/'simulation_deltas.parquet')
    original=original.loc[original.pitch_uid.isin(population.pitch_uid)].reset_index(drop=True)
    pd.testing.assert_frame_equal(scenarios[original.columns].reset_index(drop=True),original)
    normal=read(folder/('pitching_'+S0+'.json'))
    for side in ('source','target'):
        source=scenarios.rename(columns={side+'_'+p:p for p in PROBS})
        expected=100+10*(formula(source,S0)-normal['mu'])/normal['sigma']
        np.testing.assert_allclose(scenarios[side+'_score'],expected,atol=1e-12,rtol=0,equal_nan=True)
    np.testing.assert_allclose(scenarios.delta_score,scenarios.target_score-scenarios.source_score,atol=1e-12,equal_nan=True)
    assert scenarios.reference_id.eq(reference_hash).all() and not scenarios.recommendation_allowed.any()
    sensitivity=read(folder/'contact_sensitivity.json')
    assert len(sensitivity)==24
    for row in sensitivity:
        data=predictions.loc[predictions.family.eq(row['family'])]
        ref=data.loc[data.partition.eq('calibration')]
        dev=data.loc[data.partition.eq('development') & data.pitch_uid.isin(population.pitch_uid)]
        assert row['partition']=='development' and not row['selected']
        assert row['development_id']==ids_hash(dev.pitch_uid.tolist())
        assert row['relative_change'] in (-.25,.25)
        def changed(frame):
            return sum(frame['p_'+c]*w for c,w in row['weights'].items()).to_numpy()+frame.p_in_play.to_numpy()*(row['contact_weights'][0]*frame.p_weak_given_in_play.to_numpy()+row['contact_weights'][1]*frame.p_hard_given_in_play.to_numpy())
        r,d=changed(ref),changed(dev)
        np.testing.assert_allclose([row['mu'],row['sigma']],[r.mean(),r.std(ddof=0)],atol=1e-14)
        base=100+10*(formula(dev,S1)-formula(ref,S1).mean())/formula(ref,S1).std(ddof=0)
        variant=100+10*(d-r.mean())/r.std(ddof=0)
        np.testing.assert_allclose([row['mean_absolute_score_change'],row['max_absolute_score_change'],row['spearman_correlation']],
            [np.abs(variant-base).mean(),np.abs(variant-base).max(),pd.Series(base).corr(pd.Series(variant),method='spearman')],atol=1e-11)
    dataset.assert_unchanged()
    return dict(status='verified',experiment=name,reference_n=len(ids),population_n=len(population),
                rows=counts,environment_rows=len(scenarios),sensitivity_variants=len(sensitivity),test_accessed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment_id')
    args=parser.parse_args()
    print(json.dumps(check(args.experiment_id),indent=2))
