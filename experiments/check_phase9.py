"""Independent recomputation of F9 evidence without opening 2026 records."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from experiments.phase9 import ExperimentModel, CLASSES, RELEASE, write, standardized_probabilities, UTILITY
from experiments.phase9_predict import verify_experiment, ExperimentalPredictor
from modeling.models import TabularEventModel
from modeling.calibration import TemperatureScaler
from modeling.metrics import multiclass_metrics, per_pitch_losses, paired_bootstrap
from modeling.datasets import ids_hash, sha256_file
from modeling.release import verify_release


def audit(folder):
    folder = Path(folder)
    manifest = verify_experiment(folder)
    summary = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    cfg = json.loads((folder/'config.json').read_text(encoding='utf-8'))
    cohort = pd.read_parquet(folder/'cohort.parquet')
    assert cohort.year.isin([2024, 2025]).all()
    assert cohort.pitch_uid.is_unique
    checks = dict(artifact_hashes=True, only_development_years=True)
    for protocol in ('A', 'B', 'C'):
        predictions = pd.read_parquet(folder/protocol/'review_predictions.parquet')
        parts = {p:pd.read_parquet(folder/protocol/(p+'_ids.parquet')) for p in ('train', 'development', 'calibration', 'review')}
        for p, rows in parts.items():
            assert ids_hash(rows.pitch_uid.tolist()) == summary['protocols'][protocol]['partitions'][p]['ids_sha256']
        for left,right in (('train','calibration'),('train','review'),('development','calibration'),('development','review'),('calibration','review')):
            assert not set(parts[left].pitch_uid) & set(parts[right].pitch_uid)
            if protocol in ('A','C'):
                assert not set(parts[left].game_anon_id) & set(parts[right].game_anon_id)
        if protocol=='B':
            assert not set(parts['review'].pitcher_anon_id) & set(pd.concat([parts[p] for p in ('train','development','calibration')]).pitcher_anon_id)
        checks[protocol+'_partitions'] = True
        loss_frames = {}
        for variant, entry in summary['protocols'][protocol]['metrics'].items():
            p = predictions[[variant+'_'+c for c in CLASSES]].to_numpy()
            actual = multiclass_metrics(predictions.y_event, p, CLASSES)
            assert actual == entry['calibrated']
            loss = predictions[['pitch_uid','game_anon_id','y_event']].copy()
            loss['loss'] = per_pitch_losses(predictions.y_event, p, CLASSES)[0]
            loss_frames[variant] = loss
        checks[protocol+'_metrics_recomputed'] = True
        for ref,candidate in cfg['comparisons_C' if protocol=='C' else 'comparisons_AB']:
            expected = summary['comparisons'][protocol+':'+candidate+'_vs_'+ref]
            result = paired_bootstrap(loss_frames[ref],loss_frames[candidate],expected['resamples'],cfg['seed'],confidence=expected['confidence'],minimum_relative_improvement=cfg['minimum_relative_improvement'],smoke=summary['smoke'])
            for key in ('delta_candidate_minus_reference','relative_log_loss_reduction','ci_low','ci_high','decision'):
                assert result[key] == expected[key]
        checks[protocol+'_bootstrap_recomputed'] = True
    review = cohort.loc[cohort.partition.eq('phase_review')].copy()
    # Re-evaluate only 2025 to compare the actual immutable predecessor, not a refit.
    frozen = TabularEventModel.load(RELEASE/'models/stuff/event/model')
    p = frozen.predict(review)
    policy = json.loads((RELEASE/'models/stuff/event/calibration_policy.json').read_text(encoding='utf-8'))
    if policy['route']=='temperature':
        p = TemperatureScaler.load(RELEASE/'models/stuff/event/temperature.json').transform(p)
    frozen_metrics = multiclass_metrics(review.y_event,p,CLASSES)
    predictor = ExperimentalPredictor(folder)
    sample = review.iloc[:4].copy()
    records = sample.to_dict('records')
    records.append(dict(records[0],rel_speed=-1))
    records.append(dict(records[0],pitcher_throws='Unknown'))
    result = predictor.predict(records)
    assert all(r['status']=='experimental' for r in result[:4])
    assert all(r['status']=='invalid_input' and r['score'] is None for r in result[4:])
    saved = pd.read_parquet(folder/'standardized_scores.parquet').set_index('pitch_uid')
    np.testing.assert_allclose([r['score'] for r in result[:4]], saved.loc[sample.pitch_uid].experimental_score, atol=1e-9, rtol=0)
    changed = [{k:v for k,v in r.items() if k not in ('year','y_event','balls','strikes','batter_side','pitcher_anon_id')} for r in records[:4]]
    assert predictor.predict(changed)==result[:4]
    checks['outcome_free_inference_and_invalid_rows'] = True
    checks['saved_scores_reproduced'] = True
    aggregate = pd.read_csv(folder/'scouting.csv')
    recomputed = saved.reset_index().groupby(['pitcher_anon_id','auto_pitch_type']).experimental_score.agg(['mean','size']).reset_index()
    joined = aggregate.merge(recomputed,on=['pitcher_anon_id','auto_pitch_type'],validate='one_to_one')
    assert len(joined)==len(aggregate)==len(recomputed)
    np.testing.assert_allclose(joined.score,joined['mean'],atol=1e-9,rtol=0)
    np.testing.assert_array_equal(joined.n,joined['size'])
    checks['scouting_recomputed'] = True
    checks['F8_unchanged'] = verify_release(RELEASE)['release_id']==summary['release_id']
    checks['test_exposure_unchanged'] = sha256_file(RELEASE.parents[1]/'test_exposure.json')==manifest['test_exposure_sha256']
    assert all(checks.values())
    return dict(checks=checks, F8_stuff_on_same_2025_review=frozen_metrics,
                comparison_scope='descriptive_2025_reused_review_not_new_final_test',
                F9_manifest_sha256=sha256_file(folder/'manifest.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=audit(args.experiment)
    write(args.output,result)
    print(json.dumps(result,indent=2))
