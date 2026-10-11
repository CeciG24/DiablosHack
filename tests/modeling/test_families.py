import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from modeling.baselines import EventBaseline
from modeling.datasets import FEATURES, join_pitches
from modeling.models import StuffModel, TabularEventModel
from modeling.phase3 import family_decisions, select_model
from modeling.protocols import assign_pitcher_partitions
from tests.modeling.test_stuff import fixture, PARAMS


def contextual(partition='train', n=360):
    rows = fixture(n, partition)
    rows['plate_loc_height'] = 1 + np.arange(n) % 6 / 2
    rows['plate_loc_side'] = np.arange(n) % 3 - 1.0
    rows['balls'] = np.arange(n) % 4
    rows['strikes'] = np.arange(n) % 3
    rows['batter_side'] = 'Right'
    rows['pitcher_anon_id'] = [partition + '-pitcher-' + str(i % 12) for i in range(n)]
    rows['pitcher_split'] = 'train' if partition == 'train' else 'validation'
    return rows


class FamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train, cls.dev = contextual(), contextual('development', 120)
        cls.models = {f: TabularEventModel(7, 1, f).fit(cls.train, cls.dev, PARAMS, 8, 3) for f in FEATURES}

    def test_exact_family_features_and_excluded_input_invariance(self):
        for family, model in self.models.items():
            self.assertEqual(model.booster.feature_name(), FEATURES[family])
            changed = self.dev.copy()
            for column in set(FEATURES['pitching'] + ['altitude_category', 'y_event', 'pitch_uid']) - set(FEATURES[family]):
                changed[column] = 'should never enter X'
            np.testing.assert_array_equal(model.predict(self.dev), model.predict(changed))

    def test_location_and_pitching_save_reload_and_corrupt_feature_schema(self):
        for family in ('location', 'pitching'):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / family
                self.models[family].save(path)
                loaded = TabularEventModel.load(path)
                np.testing.assert_array_equal(loaded.predict(self.dev), self.models[family].predict(self.dev))
                meta_path = path / 'preprocessing.json'
                metadata = json.loads(meta_path.read_text())
                metadata['features'].append('altitude_category')
                meta_path.write_text(json.dumps(metadata))
                with self.assertRaises(ValueError):
                    TabularEventModel.load(path)

    def test_batter_category_is_train_only_and_unknown_warns(self):
        dev = self.dev.copy()
        dev['batter_side'] = 'Unseen'
        model = TabularEventModel(7, 1, 'location').fit(self.train, dev, PARAMS, 4, 2)
        self.assertEqual(model.vocabularies['batter_side'], ['Right'])
        self.assertTrue(all('unknown_category:batter_side' in w for w in model.warnings(dev)))
        self.assertTrue(np.isfinite(model.predict(dev)).all())

    def test_context_missing_nonfinite_and_invalid_counts_rejected(self):
        for column, value in [('plate_loc_height', np.nan), ('plate_loc_side', np.inf), ('balls', 4), ('strikes', .5)]:
            changed = self.dev.copy()
            changed[column] = value
            for family in ('location', 'pitching'):
                with self.assertRaises(ValueError):
                    self.models[family].predict(changed)

    def test_stuff_wrapper_cannot_load_contextual_family(self):
        with self.assertRaises(ValueError):
            StuffModel(family='location')

    def test_pitcher_assignment_stable_and_separates_validation_games(self):
        rows = contextual('development', 360)
        rows.loc[::2, 'year'] = 2024
        expected = assign_pitcher_partitions(rows, 'seed')
        actual = assign_pitcher_partitions(rows.sample(frac=1, random_state=7), 'seed')
        self.assertTrue(expected.equals(actual))
        self.assertEqual(set(expected.partition), {'development', 'calibration'})
        self.assertTrue(expected.groupby('game_anon_id').partition.nunique().eq(1).all())
        self.assertEqual(set(expected.year), {2024, 2025})

    def test_pitcher_assignment_rejects_2026_and_inconsistent_ids(self):
        rows = self.train.copy()
        rows.loc[0, 'year'] = 2026
        with self.assertRaises(PermissionError):
            assign_pitcher_partitions(rows, 'seed')
        rows = self.train.copy()
        rows.loc[0, 'pitcher_split'] = 'test'
        with self.assertRaises(ValueError):
            assign_pitcher_partitions(rows, 'seed')

    def test_B_fits_real_years_allows_shared_games_and_preserves_provenance(self):
        train, dev = self.train.copy(), self.dev.copy()
        train.loc[::2, 'year'] = 2025
        dev.loc[::2, 'year'] = 2024
        dev['game_anon_id'] = train.game_anon_id.iloc[:len(dev)].to_numpy()
        model = TabularEventModel(7, 1, 'pitching', 'B').fit(train, dev, PARAMS, 4, 2)
        self.assertEqual(model.metadata['fit_years'], [2024, 2025])
        self.assertEqual(model.metadata['protocol_id'], 'B')
        baseline = EventBaseline('B1').fit(train, protocol='B')
        with tempfile.TemporaryDirectory() as tmp:
            model.save(Path(tmp) / 'model')
            baseline.save(Path(tmp) / 'B1.json')
            np.testing.assert_array_equal(model.predict(dev), TabularEventModel.load(Path(tmp) / 'model').predict(dev))
            np.testing.assert_array_equal(baseline.predict(dev)[0], EventBaseline.load(Path(tmp) / 'B1.json').predict(dev)[0])

    def test_B_rejects_test_pitchers_and_unauthorized_seasons(self):
        for column, value in [('year', 2026), ('pitcher_split', 'test'), ('partition', 'phase_review')]:
            rows = self.train.copy()
            rows[column] = value
            with self.assertRaises(PermissionError):
                TabularEventModel(7, 1, 'location', 'B').fit(rows, self.dev, PARAMS, 4, 2)
            with self.assertRaises(PermissionError):
                EventBaseline('B1').fit(rows, protocol='B')
        dev = self.dev.copy()
        dev['pitcher_anon_id'] = self.train.pitcher_anon_id.iloc[:len(dev)].to_numpy()
        with self.assertRaises(ValueError):
            TabularEventModel(7, 1, 'stuff', 'B').fit(self.train, dev, PARAMS, 4, 2)

    def test_review_and_calibration_never_used_for_selection(self):
        for part in ('calibration', 'phase_review'):
            dev = self.dev.copy()
            dev['partition'] = part
            for protocol in ('A', 'B'):
                with self.assertRaises(PermissionError):
                    TabularEventModel(7, 1, 'location', protocol).fit(self.train, dev, PARAMS, 4, 2)

    def test_join_by_ID_preserves_labels_when_rows_shuffled(self):
        left = self.dev[['pitch_uid']].sample(frac=1, random_state=7)
        joined = join_pitches(left, self.dev[['pitch_uid', 'y_event']])
        self.assertEqual(joined.y_event.tolist(), left.pitch_uid.map(self.dev.set_index('pitch_uid').y_event).tolist())
        with self.assertRaises(ValueError):
            join_pitches(left, self.dev.iloc[[0, 0]])

    def test_pitching_promotion_requires_both_comparisons(self):
        comparisons = {key: {'decision': 'promote'} for key in ('Stuff_vs_B1', 'Location_vs_B1', 'Pitching_vs_Location', 'Pitching_vs_B1')}
        self.assertEqual(family_decisions(comparisons, False)['predictive_reference'], 'Pitching')
        for key in ('Pitching_vs_Location', 'Pitching_vs_B1'):
            changed = dict(comparisons, **{key: {'decision': 'inconclusive'}})
            self.assertEqual(family_decisions(changed, False)['predictive_reference'], 'Location')
        self.assertEqual(family_decisions(comparisons, True)['scientific_decision'], 'inconclusive')

    def test_search_budget(self):
        with self.assertRaises(ValueError):
            select_model(self.train, self.dev, {'candidates': [PARAMS] * 13}, 7, Path('unused'), 'location', 'A', False)
