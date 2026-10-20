"""Synthetic regressions for the separate, arsenal-aware combined score."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from experiments.final_score import split_rows
from experiments.phase10_features import REGULARIZED, Repertoire, trajectory
from experiments.phase9 import write
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler
from modeling.datasets import PITCHING, sha256_file
from modeling.final_score import CombinedEventModel, FinalScorePredictor, VERSION, WEIGHTS
from tests.modeling.test_stuff import PARAMS
from tests.test_phase10 import CFG, fixture


class FinalScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        history, _ = trajectory(fixture(), CFG, audit=True)
        cls.history = history
        cls.repertoire = Repertoire().fit(history)
        cls.rows = fixture('development', 180).assign(spin_axis_sin=0., spin_axis_cos=1.)
        cls.prepared = cls.repertoire.transform(cls.rows)
        cls.model = CombinedEventModel(threads=1).fit(cls.prepared, PARAMS, 8)

    def artifact(self, folder):
        self.model.save(folder/'combined/model')
        self.repertoire.save(folder/'repertoire')
        cal = self.prepared.assign(partition='calibration')
        TemperatureScaler(CLASSES).fit(cal, self.model.predict(cal), 'y_event').save(
            folder/'combined/temperature.json')
        write(folder/'scale.json', dict(version=VERSION, weights=WEIGHTS.tolist(),
                                       mu=0., sigma=.1, reference_n=len(cal)))
        write(folder/'input_bounds.json', {'rel_speed': [30, 110]})
        write(folder/'manifest.json', dict(artifacts={
            str(p.relative_to(folder)): sha256_file(p) for p in folder.rglob('*') if p.is_file()}))
        return FinalScorePredictor(folder)

    def test_allowlist_has_all_four_components_and_no_outcomes_or_ids(self):
        self.assertEqual(self.model.features, PITCHING+REGULARIZED)
        self.assertTrue({'plate_loc_height', 'plate_loc_side', 'balls', 'strikes', 'batter_side'}.issubset(self.model.features))
        self.assertFalse(set(self.model.features) & {'pitch_uid', 'pitcher_anon_id', 'y_event', 'year', 'altitude_category'})

    def test_fit_and_history_reject_review_or_future(self):
        for year, partition in ((2026, 'development'), (2025, 'phase_review'), (2025, 'calibration')):
            with self.assertRaises(PermissionError):
                CombinedEventModel(threads=1).fit(self.prepared.assign(year=year, partition=partition), PARAMS, 2)
        with self.assertRaises(PermissionError):
            Repertoire().fit(self.history.assign(year=2025))
        roles = [fixture(role, 36) for role in ('development', 'calibration', 'phase_review')]
        rows = pd.concat(roles, ignore_index=True)
        self.assertEqual(len(split_rows(rows)), 3)
        with self.assertRaises(PermissionError):
            split_rows(rows.assign(year=2026))
        with self.assertRaises(ValueError):
            split_rows(rows.assign(game_anon_id='leaking-game'))

    def test_history_is_recomputed_and_location_context_preserved(self):
        prepared = self.repertoire.transform(self.rows)
        for column in PITCHING:
            pd.testing.assert_series_equal(prepared[column], self.rows[column], check_names=False)
        cold = self.repertoire.transform(self.rows.assign(pitcher_anon_id='new-pitcher'))
        self.assertTrue(cold.history_status.eq('group_prior_only').all())
        self.assertFalse(np.array_equal(prepared[REGULARIZED], cold[REGULARIZED]))

    def test_reload_batch_invalid_rows_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            predictor = self.artifact(Path(tmp))
            rows = self.rows.iloc[:3].to_dict('records')
            expected = predictor.records(rows)
            self.assertTrue(all(r['status'] == 'experimental' for r in expected))
            self.assertTrue(all(r['history_n'] > 0 for r in expected))
            self.assertAlmostEqual(sum(expected[0]['probabilities'].values()), 1.)
            p = np.array(list(expected[0]['probabilities'].values()))
            self.assertAlmostEqual(expected[0]['score'], 100+10*(p@WEIGHTS)/.1)
            changed = [r | {'y_event': 'garbage', 'ars_0_usage': 999, 'year': 2026} for r in rows]
            self.assertEqual([r['score'] for r in expected], [r['score'] for r in predictor.records(changed)])
            self.assertEqual(predictor.records(rows[:1])[0]['score'], expected[0]['score'])
            mixed = predictor.records([rows[0], rows[1] | {'balls': None}, rows[2]])
            self.assertIsNone(mixed[1]['score'])
            self.assertEqual(mixed[1]['status'], 'invalid_input')
            self.assertEqual(mixed[2]['score'], expected[2]['score'])
            for update in ({'balls': True}, {'strikes': .5}, {'plate_loc_side': np.inf},
                           {'batter_side': 'unknown'}, {'spin_axis_cos': 0.}, {'spin_axis_sin': 2.}):
                self.assertEqual(predictor.records([rows[0] | update])[0]['status'], 'invalid_input')
            prior = predictor.records([rows[0] | {'pitcher_anon_id': 'unknown'}])[0]
            self.assertEqual(prior['history_status'], 'group_prior_only')
            self.assertEqual(prior['history_n'], 0)
            self.assertIn('group_prior_only', prior['warnings'])
            self.assertEqual(FinalScorePredictor(Path(tmp)).records(rows), expected)
            with (Path(tmp)/'combined/model/model.txt').open('a') as handle:
                handle.write('\ncorrupt')
            with self.assertRaises(ValueError):
                FinalScorePredictor(Path(tmp))


if __name__ == '__main__':
    unittest.main()
