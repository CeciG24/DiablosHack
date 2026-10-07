import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from modeling.baselines import CLASSES, EventBaseline
from modeling.datasets import pd
from modeling.metrics import (calibration_bins, multiclass_metrics, paired_bootstrap,
                              validate_probabilities, write_calibration_svg)
import numpy as np


def training_frame():
    return pd.DataFrame({
        'pitch_uid': ['a', 'b', 'c', 'd'], 'year': [2024] * 4,
        'partition': ['train'] * 4, 'balls': [0, 0, 1, 1], 'strikes': [0] * 4,
        'auto_pitch_type': ['Fastball', 'Curve', 'Fastball', 'Fastball'],
        'y_event': ['ball', 'ball', 'whiff', 'foul']})


class BaselineTests(unittest.TestCase):
    def test_global_pseudocount_and_absent_classes(self):
        model = EventBaseline('B0').fit(training_frame())
        p, routes = model.predict(pd.DataFrame(index=range(2)))
        np.testing.assert_allclose(p, np.tile([.3, .1, .2, .2, .1, .1], (2, 1)))
        self.assertEqual(routes.tolist(), ['global'] * 2)
        validate_probabilities(p)

    def test_group_smoothing_uses_global_prior(self):
        frame = training_frame()
        model = EventBaseline('B1').fit(frame)
        p, _ = model.predict(frame)
        np.testing.assert_allclose(p[0], (np.array([2, 0, 0, 0, 0, 0]) + 20 * model.global_probabilities) / 22)
        np.testing.assert_allclose(p[2], (np.array([0, 0, 1, 1, 0, 0]) + 20 * model.global_probabilities) / 22)

    def test_b2_conditions_on_type_as_well_as_count(self):
        frame = training_frame()
        model = EventBaseline('B2').fit(frame)
        p, _ = model.predict(frame)
        self.assertEqual(len(model.state['group_counts']), 3)
        np.testing.assert_allclose(p[0], (np.array([1, 0, 0, 0, 0, 0]) + 20 * model.global_probabilities) / 21)

    def test_unseen_and_missing_groups_use_global(self):
        for name in ('B1', 'B2'):
            model = EventBaseline(name).fit(training_frame())
            unseen = pd.DataFrame({'balls': [3., np.nan], 'strikes': [2, 0], 'auto_pitch_type': ['New', None]})
            p, route = model.predict(unseen)
            np.testing.assert_array_equal(p, np.tile(model.global_probabilities, (2, 1)))
            self.assertEqual(route.tolist(), ['fallback_global'] * 2)
        model = EventBaseline('B2').fit(training_frame())
        unseen = pd.DataFrame({'balls': [0], 'strikes': [0], 'auto_pitch_type': ['New']})
        self.assertEqual(model.predict(unseen)[1].tolist(), ['fallback_global'])

    def test_nontraining_rows_rejected(self):
        for year, partition in [(2025, 'development'), (2025, 'calibration'), (2025, 'phase_review'), (2026, 'test'), (2024, 'development')]:
            frame = training_frame(); frame.loc[0, ['year', 'partition']] = [year, partition]
            with self.assertRaises(PermissionError):
                EventBaseline('B1').fit(frame)

    def test_null_unknown_target_or_duplicate_ids_rejected(self):
        for label in (None, 'unknown'):
            frame = training_frame(); frame.loc[0, 'y_event'] = label
            with self.assertRaises(ValueError):
                EventBaseline('B0').fit(frame)
        frame = training_frame(); frame.loc[1, 'pitch_uid'] = 'a'
        with self.assertRaises(ValueError):
            EventBaseline('B0').fit(frame)

    def test_invalid_context_and_smoothing_rejected(self):
        for strength in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                EventBaseline('B1', strength=strength)
        for value in (4, -1, 0.5):
            frame = training_frame(); frame['balls'] = value
            with self.assertRaises(ValueError):
                EventBaseline('B1').fit(frame)
        with self.assertRaises(ValueError):
            EventBaseline('B1').fit(training_frame().drop(columns='balls'))

    def test_fit_is_order_independent_and_predictions_ignore_outcomes(self):
        frame = training_frame()
        for name in ('B0', 'B1', 'B2'):
            model = EventBaseline(name).fit(frame)
            shuffled = EventBaseline(name).fit(frame.sample(frac=1, random_state=9))
            self.assertEqual(model.state, shuffled.state)
            before = json.dumps(model.state, sort_keys=True)
            expected, _ = model.predict(frame)
            changed = frame.copy(); changed['y_event'] = 'hit_by_pitch'; changed['year'] = 2025
            actual, _ = model.predict(changed)
            np.testing.assert_array_equal(expected, actual)
            self.assertEqual(before, json.dumps(model.state, sort_keys=True))

    def test_save_reload_and_bad_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'model.json'
            for name in ('B0', 'B1', 'B2'):
                model = EventBaseline(name).fit(training_frame()); model.save(path)
                loaded = EventBaseline.load(path)
                for expected, actual in zip(model.predict(training_frame()), loaded.predict(training_frame())):
                    np.testing.assert_array_equal(expected, actual)
            state = json.loads(path.read_text()); state['global_counts'][0] += 1
            path.write_text(json.dumps(state))
            with self.assertRaises(ValueError):
                EventBaseline.load(path)


class MetricsTests(unittest.TestCase):
    def test_uniform_and_perfect_metrics(self):
        uniform = multiclass_metrics(CLASSES, np.full((6, 6), 1 / 6), CLASSES)
        self.assertAlmostEqual(uniform['multiclass_log_loss'], np.log(6))
        self.assertAlmostEqual(uniform['multiclass_brier_sum_over_classes'], 5 / 6)
        perfect = multiclass_metrics(CLASSES, np.eye(6), CLASSES)
        self.assertEqual(perfect['multiclass_log_loss'], 0)
        self.assertEqual(perfect['multiclass_brier_sum_over_classes'], 0)

    def test_invalid_probabilities_and_labels(self):
        for values in ([.2] * 6, [float('nan')] * 6, [float('inf')] * 6, [-1, 2, 0, 0, 0, 0]):
            with self.assertRaises(ValueError):
                validate_probabilities([values])
        for labels in (['invalid'], [None], []):
            with self.assertRaises(ValueError):
                multiclass_metrics(labels, [[1 / 6] * 6], CLASSES)

    def test_calibration_fixed_edges_empty_bins_and_one(self):
        rows = calibration_bins(['ball', 'whiff', 'ball'],
                                [[0, 1, 0, 0, 0, 0], [.1, .9, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0]], CLASSES)
        self.assertEqual(len(rows), 60)
        ball = [r for r in rows if r['class'] == 'ball']
        self.assertEqual([ball[i]['n'] for i in (0, 1, 9)], [1, 1, 1])
        self.assertEqual(ball[9]['positives'], 1)
        self.assertIsNone(ball[2]['observed_frequency'])
        self.assertIsNone(ball[2]['mean_probability'])
        self.assertEqual(sum(r['positives'] for r in ball), 2)

    def test_bootstrap_resamples_whole_games_pitch_weighted(self):
        reference = pd.DataFrame({'pitch_uid': [str(i) for i in range(10)],
                                  'game_anon_id': ['a'] + ['b'] * 9,
                                  'y_event': ['ball'] * 10, 'loss': [3.] * 10})
        candidate = reference.copy(); candidate.loc[0, 'loss'] = 1
        result = paired_bootstrap(reference, candidate, 500, 123)
        self.assertAlmostEqual(result['delta_candidate_minus_reference'], -.2)
        self.assertEqual(result['ci_low'], -2)
        self.assertEqual(result['ci_high'], 0)
        self.assertEqual(result['decision'], 'inconclusive')
        shuffled = paired_bootstrap(reference, candidate.sample(frac=1, random_state=7), 500, 123)
        self.assertEqual(result, shuffled)

    def test_promotion_requires_effect_and_interval_and_full_run(self):
        ref = pd.DataFrame({'pitch_uid': ['a', 'b'], 'game_anon_id': ['x', 'y'], 'y_event': ['ball'] * 2, 'loss': [1.] * 2})
        candidate = ref.copy(); candidate['loss'] = .9
        self.assertEqual(paired_bootstrap(ref, candidate, 20, 1)['decision'], 'promote')
        self.assertEqual(paired_bootstrap(ref, candidate, 20, 1, smoke=True)['decision'], 'inconclusive')
        candidate['loss'] = .999
        self.assertEqual(paired_bootstrap(ref, candidate, 20, 1)['decision'], 'inconclusive')
        candidate['loss'] = 1.1
        self.assertEqual(paired_bootstrap(ref, candidate, 20, 1)['decision'], 'inconclusive')

    def test_bootstrap_rejects_unpaired_population_and_targets(self):
        ref = pd.DataFrame({'pitch_uid': ['a', 'b'], 'game_anon_id': ['x', 'y'], 'y_event': ['ball'] * 2, 'loss': [1.] * 2})
        cases = [ref.iloc[:1], pd.concat([ref, ref])]
        for column, value in [('y_event', 'whiff'), ('game_anon_id', 'wrong')]:
            changed = ref.copy(); changed.loc[0, column] = value; cases.append(changed)
        for case in cases:
            with self.assertRaises(ValueError):
                paired_bootstrap(ref, case, 20, 1)

    def test_single_game_has_no_inferential_interval(self):
        ref = pd.DataFrame({'pitch_uid': ['a'], 'game_anon_id': ['x'], 'y_event': ['ball'], 'loss': [1.]})
        result = paired_bootstrap(ref, ref, 20, 1)
        self.assertEqual(result['reason'], 'insufficient_games')
        self.assertIsNone(result['ci_high'])
        self.assertFalse(result['scientific_evidence'])

    def test_calibration_chart_is_valid_svg(self):
        rows = [dict(r, model=name, partition='development') for name in ('B0', 'B1', 'B2')
                for r in calibration_bins(CLASSES, np.eye(6), CLASSES)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'curve.svg'
            write_calibration_svg(path, rows, 'development', CLASSES)
            tree = ET.parse(path)
            self.assertEqual(len(tree.findall('.//{http://www.w3.org/2000/svg}circle')), 36)


if __name__ == '__main__':
    unittest.main()
