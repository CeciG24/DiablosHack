"""Audit a saved F10 post-release run without retraining or touching 2026."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from modeling.baselines import CLASSES, EventBaseline
from modeling.datasets import ROOT, ModelingDataset, ids_hash, join_pitches, sha256_file
from modeling.metrics import multiclass_metrics, paired_bootstrap, per_pitch_losses
from modeling.release import read, verify_release
from postrelease.stuff_v3 import (BINARY, HEAD_TARGETS, REFERENCE_INPUTS, StuffV3Model, attach_relative,
                                  build_relative_reference, load_head_targets, to_index, to_index_within_type)
from postrelease.phase10 import EVENT_MODELS


def head_loss(group):
    p = np.column_stack([1 - group.p_positive, group.p_positive])
    return group[['pitch_uid', 'game_anon_id']].assign(
        y_event=group.label.astype(int).to_numpy(),
        loss=per_pitch_losses(group.label.astype(int), p, list(BINARY))[0])


def check(experiment_id):
    dataset = ModelingDataset()
    cfg = dataset.config['F10']
    folder = ROOT / 'artifacts/modeling' / experiment_id / 'F10'
    m = read(folder / 'manifest.json')
    assert m['status'] == 'verified' and m['phase_id'] == 'F10' and not m['smoke']
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
    heads = pd.read_parquet(folder / 'head_predictions.parquet')
    events = pd.read_parquet(folder / 'event_predictions.parquet')
    assert set(heads.model) == {'base', 'refA', 'refB', 'prevalence'} and set(heads['head']) == set(HEAD_TARGETS)
    assert set(events.model) == {'B1'} | set(EVENT_MODELS)
    assert not heads.duplicated(['pitch_uid', 'head', 'model']).any() and not events.duplicated(['pitch_uid', 'model']).any()
    saved = read(folder / 'metrics.json')
    columns = ['p_' + c for c in CLASSES]
    for row in saved['metrics']:
        if row['task'] == 'head':
            part = heads.loc[heads['head'].eq(row['head']) & heads.model.eq(row['model'])
                             & heads.partition.eq(row['partition']) & heads.label.notna()]
            recalc = head_loss(part).loss.mean()
            np.testing.assert_allclose(recalc, row['log_loss'], atol=1e-12)
            assert row['n'] == len(part) and row['n_games'] == part.game_anon_id.nunique()
        else:
            part = events.loc[events.model.eq(row['model']) & events.partition.eq(row['partition'])]
            recalc = multiclass_metrics(part.y_event, part[columns].to_numpy(), CLASSES)
            for key, value in recalc.items():
                np.testing.assert_allclose(value, row[key], atol=1e-12)
    selection = read(folder / 'selection.json')
    for key, value in selection.items():
        best = min(value['trials'], key=lambda r: (r['development_log_loss'], r['candidate_id']))
        assert value['selected'] == best and not value['review_used_for_selection']
    run_cfg = read(folder / 'config.json')
    args = (run_cfg['evaluation']['bootstrap_full'], run_cfg['seed'], run_cfg['evaluation']['bootstrap_confidence'],
            run_cfg['evaluation']['promotion_min_relative_log_loss_reduction'])
    review = heads.loc[heads.partition.eq('phase_review') & heads.label.notna()]
    revents = events.loc[events.partition.eq('phase_review')]
    covered = set(heads.loc[heads.partition.eq('phase_review') & heads.has_reference & heads.model.eq('refB'), 'pitch_uid'])

    def hl(head, model, subset=None):
        g = review.loc[review['head'].eq(head) & review.model.eq(model)].sort_values('pitch_uid')
        return head_loss(g if subset is None else g.loc[g.pitch_uid.isin(subset)])

    def el(model):
        g = revents.loc[revents.model.eq(model)].sort_values('pitch_uid')
        return g[['pitch_uid', 'game_anon_id', 'y_event']].assign(
            loss=per_pitch_losses(g.y_event, g[columns].to_numpy(), CLASSES)[0])

    expected = {}
    for head in HEAD_TARGETS:
        for v in ('base', 'refA', 'refB'):
            expected[f'{head}:{v}_vs_prevalence'] = (hl(head, 'prevalence'), hl(head, v))
        for v in ('refA', 'refB'):
            expected[f'{head}:{v}_vs_base'] = (hl(head, 'base'), hl(head, v))
        expected[f'{head}:refB_vs_base_with_reference_only'] = (hl(head, 'base', covered), hl(head, 'refB', covered))
    expected['event:stuff_count_vs_B1'] = (el('B1'), el('event_stuff_count'))
    for v in ('refA', 'refB'):
        expected[f'event:{v}_vs_stuff_count'] = (el('event_stuff_count'), el(f'event_stuff_count_{v}'))
    assert set(expected) == set(saved['comparisons'])
    for key, (ref, cand) in expected.items():
        result = paired_bootstrap(ref, cand, *args)
        for field in ('delta_candidate_minus_reference', 'ci_low', 'ci_high'):
            np.testing.assert_allclose(result[field], saved['comparisons'][key][field], atol=1e-12)
        assert result['decision'] == saved['comparisons'][key]['decision']
    whiff = {v: saved['comparisons'][f'whiff_given_swing:{v}_vs_base'] for v in ('refA', 'refB')}
    decision = ('adopt_refB_deployable' if whiff['refB']['ci_high'] < 0 else
                'refA_diagnostic_only' if whiff['refA']['ci_high'] < 0 else 'retain_base')
    assert decision == saved['scientific_decision'] == m['scientific_decision']
    live = dataset.load(phase='F10')
    rows = join_pitches(live['aligned']['stuff'], live['context']).sort_values('pitch_uid').reset_index(drop=True)
    rows = load_head_targets(dataset, rows)
    assert ids_hash(rows.pitch_uid.tolist()) == m['cohort']['common_ids_sha256']
    refs = build_relative_reference(rows[REFERENCE_INPUTS], cfg['reference_min_fastballs'])
    saved_refs = pd.read_parquet(folder / 'reference_profiles.parquet')
    keys = ['pitcher_anon_id', 'reference_year', 'reference_type', 'fb_n']
    assert refs[keys].equals(saved_refs[keys])
    np.testing.assert_allclose(refs.drop(columns=keys), saved_refs.drop(columns=keys), atol=1e-12, rtol=0)
    frames = {'base': rows.assign(has_reference=False), 'refA': attach_relative(rows, refs, 'same_season'),
              'refB': attach_relative(rows, refs.loc[refs.reference_year.eq(2024)], 'prior_season_at_inference')}
    for (path, variant, head) in [(f'models/{h}/{v}', v, h) for h in HEAD_TARGETS for v in ('base', 'refA', 'refB')]:
        model = StuffV3Model.load(folder / path)
        assert model.metadata['fit_ids_sha256'] == ids_hash(
            rows.loc[rows.partition.eq('train') & rows[HEAD_TARGETS[head]].notna(), 'pitch_uid'].tolist())
        frame = frames[variant]
        frame = frame.loc[~frame.partition.eq('train')].head(2000)
        saved_p = heads.loc[heads['head'].eq(head) & heads.model.eq(variant)].set_index('pitch_uid').loc[frame.pitch_uid, 'p_positive']
        np.testing.assert_allclose(model.predict(frame)[:, 1], saved_p.to_numpy(), atol=1e-12, rtol=0)
    for name, variant in EVENT_MODELS.items():
        model = StuffV3Model.load(folder / 'models' / name)
        frame = frames[variant].loc[~frames[variant].partition.eq('train')].head(2000)
        saved_p = events.loc[events.model.eq(name)].set_index('pitch_uid').loc[frame.pitch_uid, columns]
        np.testing.assert_allclose(model.predict(frame), saved_p.to_numpy(), atol=1e-12, rtol=0)
    for name in ('B1',):
        f1 = ROOT / 'artifacts/modeling' / cfg['f1_reference_experiment'] / 'F1/models' / (name + '.json')
        assert sha256_file(folder / (name + '.json')) == sha256_file(f1)
        EventBaseline.load(folder / (name + '.json'))
    scales = read(folder / 'index_scales.json')
    index = pd.read_parquet(folder / 'stuff_v3_index.parquet')
    cal = index.loc[index.partition.eq('calibration')]
    assert scales['global']['n'] == len(cal)
    np.testing.assert_allclose(to_index(index.p_whiff_given_swing, scales['global']), index.index_global, atol=1e-9)
    frame = index.rename(columns={'p_whiff_given_swing': 'score'})
    np.testing.assert_allclose(to_index_within_type(frame, 'score', scales['within_type']), index.index_within_type, atol=1e-9)
    assert set(index.partition) == {'development', 'calibration', 'phase_review'}
    return dict(status='verified', experiment=experiment_id, decision=saved['scientific_decision'],
                selected_variant=saved['selected_variant'], n_models=len(HEAD_TARGETS) * 3 + len(EVENT_MODELS),
                comparisons=len(expected), dataset_reopened=False, test_previously_exposed=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('experiment_id')
    print(check(p.parse_args().experiment_id))
