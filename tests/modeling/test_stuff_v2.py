import json
from pathlib import Path
import tempfile
import unittest

from modeling.baselines import CLASSES
from modeling.datasets import STUFF, pd
from postrelease.stuff_v2 import (DERIVED, STUFF_V2, Z_FEATURES, StuffV2Model, augment,
                                  derive_local, fit_group_stats, permutation_importance_v2)
from postrelease.phase9 import select_stuff_v2
import numpy as np

PARAMS = {'num_leaves': 7, 'min_data_in_leaf': 5, 'learning_rate': .15, 'lambda_l2': 1.0}


def fixture(n=360, partition='train'):
    index = np.arange(n)
    frame = pd.DataFrame({c: 1.0 + index / n for c in STUFF})
    frame['auto_pitch_type'] = np.where(index % 2, 'Curve', 'Fastball')
    frame['pitcher_throws'] = 'Right'
    frame['rel_speed'] = 70 + 4 * (index % 6)
    frame['pitch_uid'] = [f'{partition}-{i:04}' for i in index]
    frame['game_anon_id'] = [f'{partition}-game-{i//6}' for i in index]
    frame['year'] = 2024 if partition == 'train' else 2025
    frame['partition'] = partition
    frame['y_event'] = [CLASSES[i % 6] for i in index]
    return frame


class StuffV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.training, cls.development = fixture(), fixture(120, 'development')
        cls.model = StuffV2Model(seed=7, threads=1).fit(cls.training, cls.development,
                                                        PARAMS, rounds=12, patience=3)

    def test_exact_allowlist_and_all_class_probabilities(self):
        model = self.model
        self.assertEqual(model.booster.feature_name(), STUFF_V2)
        X = model.transform(self.development)
        self.assertEqual(X.columns.tolist(), STUFF_V2)
        self.assertEqual(len(STUFF_V2), len(STUFF) + len(DERIVED) + len(Z_FEATURES))
        p = model.predict(self.development)
        self.assertEqual(p.shape, (120, 6))
        self.assertTrue(np.isfinite(p).all())
        np.testing.assert_allclose(p.sum(axis=1), 1, atol=1e-6, rtol=0)

    def test_derived_features_deterministic_and_finite(self):
        stats = fit_group_stats(self.training)
        first, second = augment(self.development, stats), augment(self.development, stats)
        self.assertTrue(first.equals(second))
        for column in DERIVED + Z_FEATURES:
            self.assertTrue(np.isfinite(first[column]).all())
        np.testing.assert_allclose(first.bauer_units,
                                   self.development.spin_rate / self.development.rel_speed)
        np.testing.assert_allclose(first.break_magnitude,
                                   np.hypot(self.development.induced_vert_break,
                                            self.development.horz_break))
        np.testing.assert_allclose(first.release_slope_v,
                                   self.development.rel_height / self.development.extension)

    def test_z_scores_use_only_training_vocabulary(self):
        stats = fit_group_stats(self.training)
        self.assertTrue(set(stats['rel_speed']['by_type']) == {'Curve', 'Fastball'})
        dev = self.development.copy()
        dev['auto_pitch_type'] = 'NeverTrained'
        augmented = augment(dev, stats)
        speed = stats['rel_speed']['global']
        np.testing.assert_allclose(
            augmented.z_rel_speed, (dev.rel_speed - speed[0]) / max(speed[1], 1e-12))

    def test_context_identity_and_outcomes_do_not_change_predictions(self):
        expected = self.model.predict(self.development)
        for column in ('balls', 'strikes', 'plate_loc_height', 'plate_loc_side', 'batter_side',
                       'altitude_category', 'pitch_uid', 'pitcher_anon_id', 'game_anon_id',
                       'year', 'y_event'):
            changed = self.development.copy(); changed[column] = 'arbitrary'
            np.testing.assert_array_equal(expected, self.model.predict(changed))

    def test_missing_columns_null_and_infinite_are_rejected(self):
        invalid = [self.development.drop(columns='rel_speed')]
        for column, value in [('rel_speed', np.nan), ('spin_rate', np.inf), ('auto_pitch_type', None)]:
            frame = self.development.copy(); frame.loc[0, column] = value; invalid.append(frame)
        frame = self.development.copy(); frame['rel_speed'] = 'invalid'; invalid.append(frame)
        for frame in invalid:
            with self.assertRaises(ValueError):
                self.model.predict(frame)

    def test_unseen_category_uses_missing_branch_and_warning(self):
        frame = self.development.copy(); frame['auto_pitch_type'] = 'NewType'
        self.assertTrue(self.model.transform(frame).auto_pitch_type.eq(-1).all())
        self.assertTrue(np.isfinite(self.model.predict(frame)).all())
        self.assertTrue(all(w == 'unknown_category:auto_pitch_type' for w in self.model.warnings(frame)))

    def test_encoder_and_stats_never_learn_development_category(self):
        dev = self.development.copy(); dev.loc[0, 'auto_pitch_type'] = 'DevelopmentOnly'
        model = StuffV2Model(7, 1).fit(self.training, dev, PARAMS, rounds=3, patience=2)
        self.assertNotIn('DevelopmentOnly', model.vocabularies['auto_pitch_type'])
        self.assertNotIn('DevelopmentOnly', model.group_stats['rel_speed']['by_type'])
        self.assertEqual(model.metadata['early_stopping_partition'], 'development')
        self.assertEqual(model.metadata['feature_derivation'], 'stuff_v2_derived_physical_v1')

    def test_fit_rejects_nontrain_or_non_development_partitions(self):
        for part in ('calibration', 'phase_review', 'test'):
            dev = self.development.copy(); dev['partition'] = part
            with self.assertRaises(PermissionError):
                StuffV2Model(7, 1).fit(self.training, dev, PARAMS)
        training = self.training.copy(); training['year'] = 2026
        with self.assertRaises(PermissionError):
            StuffV2Model(7, 1).fit(training, self.development, PARAMS)

    def test_games_and_ids_cannot_overlap_fit_and_development(self):
        for column in ('pitch_uid', 'game_anon_id'):
            dev = self.development.copy(); dev.loc[0, column] = self.training[column].iloc[0]
            with self.assertRaises(ValueError):
                StuffV2Model(7, 1).fit(self.training, dev, PARAMS)

    def test_missing_class_and_unknown_target_rejected(self):
        frame = self.training.loc[self.training.y_event.ne('hit_by_pitch')]
        with self.assertRaises(ValueError):
            StuffV2Model(7, 1).fit(frame, self.development, PARAMS)
        frame = self.training.copy(); frame.loc[0, 'y_event'] = 'unknown'
        with self.assertRaises(ValueError):
            StuffV2Model(7, 1).fit(frame, self.development, PARAMS)

    def test_native_save_load_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'saved'
            self.model.save(folder)
            loaded = StuffV2Model.load(folder)
            np.testing.assert_allclose(self.model.predict(self.development),
                                       loaded.predict(self.development), atol=1e-8, rtol=0)
            self.assertEqual(loaded.group_stats, self.model.group_stats)
            with (folder / 'model.txt').open('a') as handle:
                handle.write('\ncorrupt\n')
            with self.assertRaises(ValueError):
                StuffV2Model.load(folder)

    def test_v1_loader_rejects_v2_artifact_and_reverse(self):
        from modeling.models import StuffModel
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'saved'
            self.model.save(folder)
            with self.assertRaises(ValueError):
                StuffModel.load(folder)

    def test_retraining_reproduces_after_row_shuffle(self):
        replay = StuffV2Model(7, 1).fit(self.training.sample(frac=1, random_state=9),
                                      self.development.sample(frac=1, random_state=8),
                                      PARAMS, rounds=12, patience=3)
        np.testing.assert_allclose(self.model.predict(self.development),
                                   replay.predict(self.development), atol=1e-8, rtol=0)

    def test_permutation_requires_development_and_covers_all_features(self):
        result = permutation_importance_v2(self.model, self.development, repeats=2, seed=7)
        self.assertEqual({r['feature'] for r in result}, set(STUFF_V2))
        self.assertTrue(any(r['mean_log_loss_increase'] > 0 for r in result))
        with self.assertRaises(PermissionError):
            permutation_importance_v2(self.model, fixture(120, 'phase_review'), repeats=1, seed=7)

    def test_search_budget_cannot_exceed_twelve(self):
        with self.assertRaises(ValueError):
            select_stuff_v2(self.training, self.development, {'candidates': [PARAMS] * 13},
                            7, Path('unused'))

    def test_unfitted_and_empty_prediction(self):
        with self.assertRaises(RuntimeError):
            StuffV2Model().predict(self.development)
        with self.assertRaises(RuntimeError):
            StuffV2Model().transform(self.development)
        self.assertEqual(self.model.predict(self.development.iloc[:0]).shape, (0, 6))


if __name__ == '__main__':
    unittest.main()
