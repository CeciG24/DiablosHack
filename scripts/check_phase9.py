"""Audit a saved F9 post-release run without retraining or touching 2026."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from modeling.baselines import CLASSES, EventBaseline
from modeling.datasets import ROOT, ids_hash, join_pitches, sha256_file
from modeling.datasets import ModelingDataset
from modeling.metrics import multiclass_metrics, per_pitch_losses, paired_bootstrap
from modeling.models import StuffModel
from modeling.release import read, verify_release
from postrelease.stuff_v2 import STUFF_V2, StuffV2Model


def check(experiment_id):
    dataset = ModelingDataset()
    cfg = dataset.config['F9']
    folder = ROOT / 'artifacts/modeling' / experiment_id / 'F9'
    m = read(folder / 'manifest.json')
    assert m['status'] == 'verified' and m['phase_id'] == 'F9' and not m['smoke']
    assert m['post_release_development'] and m['test_previously_exposed'] and not m['test_accessed']
    release = ROOT / 'artifacts/modeling/releases' / cfg['release_reference']
    exposure = read(ROOT / 'artifacts/modeling/test_exposure.json')
    assert verify_release(release)['release_id'] == exposure['release_id'] == m['dependency_F8']['release_id']
    for name, expected in m['artifact_hashes'].items():
        path = (folder / name).resolve()
        assert path.is_relative_to(folder.resolve()) and sha256_file(path) == expected
    assert all(v is True for v in read(folder / 'checks.json').values())
    cohort = pd.read_parquet(folder / 'cohort.parquet')
    assert cohort.year.isin([2024, 2025]).all() and cohort.pitch_uid.is_unique
    f2 = ROOT / 'artifacts/modeling' / cfg['f2_reference_experiment'] / 'F2'
    assert read(f2 / 'manifest.json')['cohort']['common_ids_sha256'] == m['cohort']['common_ids_sha256']
    assert ids_hash(cohort.pitch_uid.tolist()) == m['cohort']['common_ids_sha256']
    predictions = pd.read_parquet(folder / 'predictions.parquet')
    assert set(predictions.model) == {'B0', 'B1', 'Stuff', 'StuffV2'}
    assert predictions.year.eq(2025).all() and not predictions.duplicated(['pitch_uid', 'model']).any()
    saved = read(folder / 'metrics.json')
    for row in saved['metrics']:
        part = predictions.loc[predictions.model.eq(row['model']) & predictions.partition.eq(row['partition'])]
        recalc = multiclass_metrics(part.y_event, part[['p_' + c for c in CLASSES]].to_numpy(), CLASSES)
        for key, value in recalc.items():
            np.testing.assert_allclose(value, row[key], atol=1e-12)
        assert row['n_games'] == part.game_anon_id.nunique()
    selection = read(folder / 'selection.json')
    best = min(selection['trials'], key=lambda r: (r['development_log_loss'], r['candidate_id']))
    assert selection['selected'] == best and not selection['review_used_for_selection']
    review = predictions.loc[predictions.partition.eq('phase_review')]
    losses = {}
    for name, part in review.groupby('model'):
        loss, _ = per_pitch_losses(part.y_event, part[['p_' + c for c in CLASSES]].to_numpy(), CLASSES)
        losses[name] = part[['pitch_uid', 'game_anon_id', 'y_event']].assign(loss=loss)
    run_cfg = read(folder / 'config.json')
    for key, comparison in saved['comparisons'].items():
        reference = key.split('_vs_')[1]
        result = paired_bootstrap(losses[reference], losses['StuffV2'],
                                  run_cfg['evaluation']['bootstrap_full'],
                                  run_cfg['seed'])
        for field in ('delta_candidate_minus_reference', 'ci_low', 'ci_high', 'decision'):
            if field == 'decision':
                assert result[field] == comparison[field]
            else:
                np.testing.assert_allclose(result[field], comparison[field], atol=1e-12)
    model = StuffV2Model.load(folder / 'stuff_v2')
    assert model.booster.feature_name() == STUFF_V2
    assert model.metadata['fit_ids_sha256'] == ids_hash(
        cohort.loc[cohort.partition.eq('train'), 'pitch_uid'].tolist())
    live = dataset.load(phase='F9')
    train_types = set(live['aligned']['stuff'].loc[
        lambda f: f.partition.eq('train'), 'auto_pitch_type'].unique())
    assert set(model.group_stats['rel_speed']['by_type']).issubset(train_types)
    aligned = join_pitches(review.loc[review.model.eq('StuffV2'), ['pitch_uid']],
                           live['aligned']['stuff']).sort_values('pitch_uid')
    np.testing.assert_allclose(
        model.predict(aligned.head(2000)),
        review.loc[review.model.eq('StuffV2')].set_index('pitch_uid').loc[
            aligned.pitch_uid, ['p_' + c for c in CLASSES]].head(2000).to_numpy(),
        atol=1e-12, rtol=0)
    stuff_v1 = StuffModel.load(f2 / 'stuff')
    np.testing.assert_allclose(
        stuff_v1.predict(aligned.head(2000)),
        review.loc[review.model.eq('Stuff')].set_index('pitch_uid').loc[
            aligned.pitch_uid, ['p_' + c for c in CLASSES]].head(2000).to_numpy(),
        atol=1e-12, rtol=0)
    for name in ('B0', 'B1'):
        baseline = EventBaseline.load(folder / (name + '.json'))
        f1 = ROOT / 'artifacts/modeling' / cfg['f1_reference_experiment'] / 'F1/models' / (name + '.json')
        assert sha256_file(folder / (name + '.json')) == sha256_file(f1)
    return dict(status='verified', experiment=experiment_id,
                decision=saved['scientific_decision'], n_models=4,
                comparisons=len(saved['comparisons']),
                dataset_reopened=False, test_previously_exposed=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('experiment_id')
    print(check(p.parse_args().experiment_id))
