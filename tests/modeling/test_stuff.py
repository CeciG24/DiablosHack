import copy
import json
from pathlib import Path
import tempfile
import unittest

from modeling.baselines import CLASSES
from modeling.datasets import STUFF, pd
from modeling.models import StuffModel, permutation_importance
from modeling.phase2 import select_stuff
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


class StuffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.training, cls.development = fixture(), fixture(120, 'development')
        cls.model = StuffModel(seed=7, threads=1).fit(cls.training, cls.development, PARAMS, rounds=12, patience=3)

    def test_exact_allowlist_and_all_class_probabilities(self):
        model = self.model
        self.assertEqual(model.booster.feature_name(), STUFF)
        X = model.transform(self.development)
        self.assertEqual(X.columns.tolist(), STUFF)
        p = model.predict(self.development)
        self.assertEqual(p.shape, (120, 6))
        self.assertTrue(np.isfinite(p).all())
        np.testing.assert_allclose(p.sum(axis=1), 1, atol=1e-6, rtol=0)

    def test_context_identity_and_outcomes_do_not_change_predictions(self):
        expected = self.model.predict(self.development)
        for column in ('balls', 'strikes', 'plate_loc_height', 'plate_loc_side', 'batter_side',
                       'altitude_category', 'pitch_uid', 'pitcher_anon_id', 'game_anon_id', 'year', 'y_event'):
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

    def test_encoder_vocabulary_never_learns_development_category(self):
        dev = self.development.copy(); dev.loc[0, 'auto_pitch_type'] = 'DevelopmentOnly'
        model = StuffModel(7, 1).fit(self.training, dev, PARAMS, rounds=3, patience=2)
        self.assertNotIn('DevelopmentOnly', model.vocabularies['auto_pitch_type'])
        self.assertEqual(model.metadata['early_stopping_partition'], 'development')
        self.assertEqual(model.metadata['fit_rows'], len(self.training))

    def test_fit_rejects_nontrain_or_non_development_partitions(self):
        for part in ('calibration', 'phase_review', 'test'):
            dev = self.development.copy(); dev['partition'] = part
            with self.assertRaises(PermissionError):
                StuffModel(7, 1).fit(self.training, dev, PARAMS)
        training = self.training.copy(); training['year'] = 2026
        with self.assertRaises(PermissionError):
            StuffModel(7, 1).fit(training, self.development, PARAMS)

    def test_games_and_ids_cannot_overlap_fit_and_development(self):
        for column in ('pitch_uid', 'game_anon_id'):
            dev = self.development.copy(); dev.loc[0, column] = self.training[column].iloc[0]
            with self.assertRaises(ValueError):
                StuffModel(7, 1).fit(self.training, dev, PARAMS)

    def test_missing_class_and_unknown_target_rejected(self):
        frame = self.training.loc[self.training.y_event.ne('hit_by_pitch')]
        with self.assertRaises(ValueError):
            StuffModel(7, 1).fit(frame, self.development, PARAMS)
        frame = self.training.copy(); frame.loc[0, 'y_event'] = 'unknown'
        with self.assertRaises(ValueError):
            StuffModel(7, 1).fit(frame, self.development, PARAMS)

    def test_native_save_load_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'saved'
            self.model.save(folder)
            loaded = StuffModel.load(folder)
            np.testing.assert_allclose(self.model.predict(self.development), loaded.predict(self.development), atol=1e-8, rtol=0)
            with (folder / 'model.txt').open('a') as handle:
                handle.write('\ncorrupt\n')
            with self.assertRaises(ValueError):
                StuffModel.load(folder)

    def test_retraining_reproduces_after_row_shuffle(self):
        replay = StuffModel(7, 1).fit(self.training.sample(frac=1, random_state=9),
                                    self.development.sample(frac=1, random_state=8), PARAMS, rounds=12, patience=3)
        np.testing.assert_allclose(self.model.predict(self.development), replay.predict(self.development), atol=1e-8, rtol=0)

    def test_permutation_requires_development_and_detects_signal(self):
        result = permutation_importance(self.model, self.development, repeats=2, seed=7)
        self.assertEqual({r['feature'] for r in result}, set(STUFF))
        speed = next(r for r in result if r['feature'] == 'rel_speed')
        self.assertGreater(speed['mean_log_loss_increase'], 0)
        with self.assertRaises(PermissionError):
            permutation_importance(self.model, fixture(120, 'phase_review'), repeats=1, seed=7)

    def test_search_budget_cannot_exceed_twelve(self):
        with self.assertRaises(ValueError):
            select_stuff(self.training, self.development, {'candidates': [PARAMS]*13}, 7, Path('unused'))

    def test_unfitted_and_empty_prediction(self):
        with self.assertRaises(RuntimeError):
            StuffModel().predict(self.development)
        self.assertEqual(self.model.predict(self.development.iloc[:0]).shape, (0, 6))


if __name__ == '__main__':
    unittest.main()
