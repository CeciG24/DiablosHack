import tempfile
from pathlib import Path
import unittest

import numpy as np

from modeling.baselines import CLASSES
from modeling.datasets import STUFF, pd
from postrelease.phase10 import select_model
from postrelease.stuff_v3 import (BINARY, CONTEXT, REL, REFERENCE_INPUTS, StuffV3Model, attach_relative,
                                  auc, build_relative_reference, index_scale, reference_years, to_index,
                                  to_index_within_type, type_variance_share, within_type_correlation,
                                  within_type_scale)

PARAMS = {'num_leaves': 7, 'min_data_in_leaf': 5, 'learning_rate': .15, 'lambda_l2': 1.0}


def fixture(n=480, partition='train', year=None, pitchers=8):
    index = np.arange(n)
    rng = np.random.default_rng(3 if partition == 'train' else 4)
    frame = pd.DataFrame({c: 1.0 + rng.random(n) for c in STUFF})
    frame['auto_pitch_type'] = np.where(index % 3 == 0, 'Slider', np.where(index % 3 == 1, 'Four-Seam', 'Sinker'))
    frame['pitcher_throws'] = 'Right'
    frame['rel_speed'] = 85 + 10 * rng.random(n)
    frame['pitcher_anon_id'] = [f'p{i % pitchers}' for i in index]
    frame['pitch_uid'] = [f'{partition}-{i:04}' for i in index]
    frame['game_anon_id'] = [f'{partition}-game-{i // 6}' for i in index]
    frame['year'] = year or (2024 if partition == 'train' else 2025)
    frame['partition'] = partition
    frame['y_event'] = [CLASSES[i % 6] for i in index]
    frame['y_head'] = (frame.rel_speed + rng.normal(0, 3, n) > 90).astype(float)
    frame['balls'], frame['strikes'] = index % 4, index % 3
    return frame


class StuffV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train, cls.dev = fixture(), fixture(240, 'development')
        cls.refs = build_relative_reference(pd.concat([cls.train, cls.dev])[REFERENCE_INPUTS], minimum=10)
        cls.train_r = attach_relative(cls.train, cls.refs, 'same_season')
        cls.dev_r = attach_relative(cls.dev, cls.refs, 'same_season')

    def test_reference_uses_only_physical_covariates_and_is_order_invariant(self):
        with self.assertRaises(ValueError):
            build_relative_reference(self.train[REFERENCE_INPUTS + ['y_event']], 10)
        shuffled = build_relative_reference(self.train[REFERENCE_INPUTS].sample(frac=1, random_state=1), 10)
        base = build_relative_reference(self.train[REFERENCE_INPUTS], 10)
        key = ['pitcher_anon_id', 'reference_year']
        np.testing.assert_allclose(base.sort_values(key).fb_speed.to_numpy(),
                                   shuffled.sort_values(key).fb_speed.to_numpy(), atol=1e-9)

    def test_reference_requires_minimum_fastballs_and_ignores_breaking_balls(self):
        refs = build_relative_reference(self.train[REFERENCE_INPUTS], minimum=10_000)
        self.assertTrue(refs.empty)
        refs = build_relative_reference(self.train[REFERENCE_INPUTS], minimum=10)
        self.assertTrue(refs.reference_type.isin(['Four-Seam', 'Sinker']).all())
        frame = attach_relative(self.train, refs.iloc[0:0], 'same_season')
        self.assertFalse(frame.has_reference.any())
        self.assertTrue(frame[REL].isna().all().all())

    def test_relative_features_are_differences_to_reference(self):
        row = self.train_r.loc[self.train_r.has_reference].iloc[0]
        ref = self.refs.loc[self.refs.pitcher_anon_id.eq(row.pitcher_anon_id) & self.refs.reference_year.eq(2024)].iloc[0]
        self.assertAlmostEqual(row.rel_d_speed, row.rel_speed - ref.fb_speed)
        self.assertAlmostEqual(row.rel_d_ivb, row.induced_vert_break - ref.fb_ivb)
        self.assertAlmostEqual(row.rel_d_release, np.hypot(row.rel_height - ref.fb_height, row.rel_side - ref.fb_side))

    def test_prior_season_mode_never_reads_evaluation_year(self):
        prior = self.refs.loc[self.refs.reference_year.eq(2024)]
        years = reference_years(pd.concat([self.train, self.dev]), 'prior_season_at_inference')
        self.assertEqual(set(years), {2024})
        attached = attach_relative(self.dev, prior, 'prior_season_at_inference')
        self.assertTrue(attached.has_reference.any())
        only_current = self.refs.loc[self.refs.reference_year.eq(2025)]
        self.assertFalse(attach_relative(self.dev, only_current, 'prior_season_at_inference').has_reference.any())
        self.assertTrue(attach_relative(self.dev, only_current, 'same_season').has_reference.any())
        with self.assertRaises(ValueError):
            reference_years(self.dev, 'unknown')

    def test_head_model_allowlist_probabilities_and_missing_reference(self):
        model = StuffV3Model(STUFF + REL, BINARY, 7, 1, 'refA').fit(self.train_r, self.dev_r, 'y_head', PARAMS, 15, 3)
        self.assertEqual(model.booster.feature_name(), STUFF + REL)
        p = model.predict(self.dev_r)
        self.assertEqual(p.shape, (240, 2))
        np.testing.assert_allclose(p.sum(axis=1), 1, atol=1e-6, rtol=0)
        none = self.dev_r.copy()
        none[REL] = np.nan
        self.assertTrue(np.isfinite(model.predict(none)).all())
        self.assertTrue(all('insufficient_arsenal_reference' in w for w in model.warnings(none)))
        with self.assertRaises(ValueError):
            StuffV3Model(STUFF + ['plate_loc_height'], BINARY)

    def test_missing_physics_unseen_category_and_context_invariance(self):
        model = StuffV3Model(STUFF, BINARY, 7, 1, 'base').fit(self.train_r, self.dev_r, 'y_head', PARAMS, 15, 3)
        expected = model.predict(self.dev_r)
        changed = self.dev_r.copy()
        for column in CONTEXT + ['plate_loc_side', 'pitcher_anon_id', 'y_event', 'year']:
            changed[column] = 'ignored_context'
        np.testing.assert_array_equal(expected, model.predict(changed))
        missing = self.dev_r.copy()
        missing.loc[missing.index[0], 'spin_rate'] = np.nan
        with self.assertRaises(ValueError):
            model.predict(missing)
        unknown = self.dev_r.copy()
        unknown['auto_pitch_type'] = '__unknown__'
        self.assertTrue(np.isfinite(model.predict(unknown)).all())
        self.assertTrue(all('unknown_category' in w for w in model.warnings(unknown)))

    def test_event_model_uses_count_and_is_deterministic(self):
        features = STUFF + CONTEXT
        first = StuffV3Model(features, CLASSES, 7, 1, 'base', 'event').fit(self.train_r, self.dev_r, 'y_event', PARAMS, 10, 3)
        second = StuffV3Model(features, CLASSES, 7, 1, 'base', 'event').fit(self.train_r, self.dev_r, 'y_event', PARAMS, 10, 3)
        np.testing.assert_array_equal(first.predict(self.dev_r), second.predict(self.dev_r))
        bad = self.dev_r.copy()
        bad.loc[bad.index[0], 'balls'] = 9
        with self.assertRaises(ValueError):
            first.predict(bad)

    def test_save_load_roundtrip_and_tamper_rejection(self):
        model = StuffV3Model(STUFF + REL, BINARY, 7, 1, 'refB').fit(self.train_r, self.dev_r, 'y_head', PARAMS, 10, 3)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'm'
            model.save(folder)
            loaded = StuffV3Model.load(folder)
            np.testing.assert_array_equal(model.predict(self.dev_r), loaded.predict(self.dev_r))
            (folder / 'model.txt').write_text((folder / 'model.txt').read_text() + '\n')
            with self.assertRaises(ValueError):
                StuffV3Model.load(folder)

    def test_fit_rejects_wrong_partitions_and_overlap(self):
        model = StuffV3Model(STUFF, BINARY, 7, 1)
        with self.assertRaises(PermissionError):
            model.fit(self.dev_r, self.dev_r, 'y_head', PARAMS, 5, 2)
        overlap = self.dev_r.copy()
        overlap['game_anon_id'] = self.train_r.game_anon_id.iloc[:len(overlap)].to_numpy()
        with self.assertRaises(ValueError):
            model.fit(self.train_r, overlap, 'y_head', PARAMS, 5, 2)
        with self.assertRaises(ValueError):
            model.fit(self.train_r, self.dev_r, 'y_head', dict(PARAMS, extra=1), 5, 2)

    def test_selection_is_argmin_on_development_and_smoke_limits_budget(self):
        candidates = [PARAMS, dict(PARAMS, num_leaves=15)]
        with tempfile.TemporaryDirectory() as tmp:
            model, selection = select_model(STUFF, BINARY, self.train_r, self.dev_r, 'y_head', candidates, 7, 1, 12, 3,
                                            Path(tmp) / 'c', 'base', 'head', False)
            best = min(selection['trials'], key=lambda r: (r['development_log_loss'], r['candidate_id']))
            self.assertEqual(selection['selected'], best)
            self.assertFalse(selection['review_used_for_selection'])
            _, smoke = select_model(STUFF, BINARY, self.train_r, self.dev_r, 'y_head', candidates, 7, 1, 12, 3,
                                    Path(tmp) / 's', 'base', 'head', True)
            self.assertEqual(len(smoke['trials']), 1)

    def test_index_scaling_and_type_diagnostics(self):
        rng = np.random.default_rng(1)
        frame = pd.DataFrame({'auto_pitch_type': np.repeat(['A', 'B'], 500), 'score': np.r_[rng.normal(.2, .02, 500), rng.normal(.4, .02, 500)]})
        scale = index_scale(frame.score)
        index = to_index(frame.score, scale)
        self.assertAlmostEqual(index.mean(), 100, places=9)
        self.assertAlmostEqual(index.std(ddof=0), 10, places=9)
        typed = within_type_scale(frame, 'score')
        within = to_index_within_type(frame, 'score', typed)
        for pitch_type in 'AB':
            self.assertAlmostEqual(within[frame.auto_pitch_type.eq(pitch_type).to_numpy()].mean(), 100, places=9)
        self.assertGreater(type_variance_share(frame.score, frame.auto_pitch_type), .95)
        self.assertLess(type_variance_share(within, frame.auto_pitch_type), 1e-9)
        labels = (frame.score.to_numpy() > frame.groupby('auto_pitch_type').score.transform('median').to_numpy()).astype(float)
        self.assertGreater(within_type_correlation(frame.score, frame.auto_pitch_type, labels), .7)
        unseen = pd.DataFrame({'auto_pitch_type': ['Z'], 'score': [.3]})
        self.assertTrue(np.isfinite(to_index_within_type(unseen, 'score', typed)).all())
        with self.assertRaises(ValueError):
            index_scale([1.0, 1.0])

    def test_auc_matches_known_values(self):
        self.assertEqual(auc([0, 0, 1, 1], [.1, .2, .8, .9]), 1.0)
        self.assertEqual(auc([0, 1, 0, 1], [.5, .5, .5, .5]), .5)
        self.assertIsNone(auc([1, 1], [.1, .2]))


if __name__ == '__main__':
    unittest.main()
