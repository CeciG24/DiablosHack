import json
import tempfile
from pathlib import Path
import unittest
import numpy as np
from experiments.phase9 import (ExperimentModel, FEATURES, engineer, context_distribution,
                                standardized_probabilities)
from modeling.calibration import TemperatureScaler
from modeling.baselines import CLASSES
from tests.modeling.test_families import contextual
from tests.modeling.test_stuff import PARAMS


class Phase9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train = engineer(contextual())
        cls.dev = engineer(contextual('development', 120))
        cls.cfg = dict(parameters=PARAMS, maximum_rounds=8, patience=3, version='test', fixed_rounds_C=8)
        cls.model = ExperimentModel('context_physics', threads=1).fit_experiment(cls.train, cls.dev, cls.cfg)

    def test_allowlists_exclude_outcomes_ids_location_and_environment(self):
        forbidden = {'pitch_uid', 'pitcher_anon_id', 'year', 'y_event', 'plate_loc_height', 'plate_loc_side'}
        for features in FEATURES.values():
            self.assertFalse(forbidden & set(features))
        self.assertNotIn('altitude_category', FEATURES['context_physics'])
        self.assertNotIn('balls', FEATURES['engineered'])

    def test_engineering_is_row_local_and_rejects_invalid_hand_speed(self):
        raw = contextual()
        np.testing.assert_array_equal(engineer(raw).hand_hb, engineer(raw.iloc[::-1]).iloc[::-1].hand_hb)
        for col, value in [('rel_speed', 0), ('pitcher_throws', 'unknown')]:
            changed = raw.copy()
            changed.loc[0, col] = value
            with self.assertRaises(ValueError):
                engineer(changed)

    def test_standardization_invariant_to_observed_context_and_batch(self):
        dist = context_distribution(self.train)
        scaler = TemperatureScaler(CLASSES)
        rows = self.dev.iloc[:8]
        expected = standardized_probabilities(self.model, scaler, rows, dist)
        changed = rows.assign(balls=3, strikes=2, batter_side='Left', y_event='invalid', pitcher_anon_id='unknown')
        np.testing.assert_array_equal(expected, standardized_probabilities(self.model, scaler, changed, dist))
        np.testing.assert_array_equal(expected[:1], standardized_probabilities(self.model, scaler, rows.iloc[:1], dist))
        np.testing.assert_allclose(expected.sum(axis=1), 1)

    def test_standardization_weights_cannot_use_review_or_future(self):
        with self.assertRaises(PermissionError):
            context_distribution(self.dev)
        with self.assertRaises(PermissionError):
            context_distribution(self.train.assign(year=2026))
        with self.assertRaises(ValueError):
            standardized_probabilities(self.model, TemperatureScaler(CLASSES), self.dev, [])

    def test_serialization_and_tampered_native_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)/'model'
            self.model.save(dest)
            np.testing.assert_array_equal(self.model.predict(self.dev), ExperimentModel.load(dest).predict(self.dev))
            with (dest/'model.txt').open('a', encoding='utf-8') as f:
                f.write('\ncorrupt')
            with self.assertRaises(ValueError):
                ExperimentModel.load(dest)

    def test_no_future_fit_and_protocol_C_guard(self):
        with self.assertRaises(PermissionError):
            ExperimentModel('physical').fit_experiment(self.train.assign(year=2026), self.dev, self.cfg)
        with self.assertRaises(PermissionError):
            ExperimentModel('context_physics', 'C').fit_experiment(self.train, self.dev, self.cfg)

    def test_predictions_ignore_outcomes_and_identity(self):
        changed = self.dev.assign(y_event='garbage', pitch_uid='duplicate', pitcher_anon_id='new')
        np.testing.assert_array_equal(self.model.predict(self.dev), self.model.predict(changed))


if __name__ == '__main__':
    unittest.main()
