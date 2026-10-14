"""Audit saved final evaluation without opening a second dataset query or selecting models."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from modeling.release import read,verify_release
from modeling.datasets import sha256_file,ids_hash
from modeling.inference import ReleasePredictor
from modeling.scoring import PROBS
from modeling.baselines import CLASSES,EventBaseline
from modeling.metrics import multiclass_metrics,per_pitch_losses,paired_bootstrap
from modeling.phase8 import diagnostic_simulator


def check(folder):
    folder=Path(folder)
    lock=verify_release(folder)
    output=folder/'evaluation'
    m=read(output/'manifest.json')
    assert m['status']=='verified' and m['release_id']==lock['release_id'] and all(m['checks'].values())
    for name,expected in m['artifact_hashes'].items():
        path=(output/name).resolve()
        assert path.is_relative_to(output.resolve()) and sha256_file(path)==expected
    cohort=pd.read_parquet(output/'evaluation_cohort.parquet')
    assert cohort.year.eq(2026).all() and ids_hash(cohort.pitch_uid.tolist())==m['common_ids_sha256']
    predictor=ReleasePredictor(folder)
    scores=pd.read_parquet(output/'scores.parquet')
    matrices={}
    for family in ('stuff','location','pitching'):
        saved=pd.read_parquet(output/(family+'_inference.parquet')).set_index('pitch_uid')
        selected=saved.loc[cohort.pitch_uid]
        matrices[family]=selected[PROBS].to_numpy()
        assert len(saved)==m['n_total'] and len(selected)==m['n_common']
        actual=predictor.predict(cohort.head(1000),family)
        np.testing.assert_allclose(actual[PROBS],selected[PROBS].head(1000),atol=1e-12,rtol=0)
        scale=predictor.scales[family].metadata
        p=selected[PROBS]
        expected=100+10*(p.p_whiff+p.p_called_strike-.5*p.p_ball-p.p_hit_by_pitch-scale['mu'])/scale['sigma']
        np.testing.assert_allclose(selected.score,expected,atol=1e-12,rtol=0)
        outside=scores.loc[scores.family.eq(family)&~scores.in_common_evaluation_cohort]
        assert outside.score.isna().all() and outside.score_status.ne('ok').all()
    matrices['B1']=EventBaseline.load(folder/'B1.json').predict(cohort)[0]
    env=pd.read_parquet(output/'environment_diagnostic.parquet')
    matrices['environment']=env[PROBS].to_numpy()
    np.testing.assert_allclose(diagnostic_simulator(folder).predict(cohort.head(1000))[PROBS],env[PROBS].head(1000),atol=1e-12,rtol=0,equal_nan=True)
    metrics=read(output/'metrics.json')
    for row in metrics['metrics']:
        p=matrices[row['model']];valid=np.isfinite(p).all(axis=1)
        recalculated=multiclass_metrics(cohort.loc[valid,'y_event'],p[valid],CLASSES)
        for key,value in recalculated.items():np.testing.assert_allclose(value,row[key],atol=1e-12)
    cfg=read(folder/'config.json')
    for row in metrics['comparisons']:
        a,b=row['reference'],row['candidate']
        valid=np.isfinite(matrices[a]).all(axis=1)&np.isfinite(matrices[b]).all(axis=1)
        pair=[]
        for name in (a,b):
            frame=cohort.loc[valid,['pitch_uid','game_anon_id','y_event']].copy()
            frame['loss']=per_pitch_losses(frame.y_event,matrices[name][valid],CLASSES)[0];pair.append(frame)
        result=paired_bootstrap(*pair,cfg['evaluation']['bootstrap_full'],cfg['seed'])
        for key in ('delta_candidate_minus_reference','ci_low','ci_high'):
            np.testing.assert_allclose(result[key],row[key],atol=1e-12)
        assert row['decision']=='report_only_no_selection'
    for suffix,by in [('pitcher',['pitcher_anon_id']),('pitcher_type',['pitcher_anon_id','auto_pitch_type'])]:
        keys=['family','score_version','reference_id','partition']+by
        expected=scores.groupby(keys,dropna=False).score.agg(['size','count','mean']).reset_index()
        actual=pd.read_parquet(output/(suffix+'_aggregates.parquet'))
        joined=actual.merge(expected,on=keys,validate='one_to_one')
        assert len(actual)==len(expected)==len(joined)
        np.testing.assert_array_equal(joined.n_total,joined['size'])
        np.testing.assert_array_equal(joined.n_valid,joined['count'])
        np.testing.assert_allclose(joined.score,joined['mean'],atol=1e-12,equal_nan=True)
    cases=read(output/'scouting_cases.json')
    counts=cohort.groupby('pitcher_anon_id').size().rename('n').reset_index().sort_values(['n','pitcher_anon_id'],ascending=[False,True]).head(3)
    assert [c['pitcher_anon_id'] for c in cases]==counts.pitcher_anon_id.tolist()
    return dict(status='verified',release_id=lock['release_id'],n_total=m['n_total'],n_common=m['n_common'],
                global_metrics=5,paired_comparisons=5,scouting_cases=3,dataset_reopened=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('release')
    print(check(p.parse_args().release))
