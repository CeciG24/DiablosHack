"""Scientific invariants for external run weights and HTTP integration."""
import unittest
from fastapi.testclient import TestClient
from backend.xrv import ExternalRunValue, EVENTS
from backend.main import create_app
from backend.schemas import EXAMPLE
from tests.test_backend import Predictor, Simulator


def one_hot(event):
    return {e: float(e == event) for e in EVENTS}


class RunValueTests(unittest.TestCase):
    def setUp(self):
        self.xrv = ExternalRunValue()

    def test_all_counts_follow_transitions_and_two_strike_fouls(self):
        for b in range(4):
            for s in range(3):
                w = self.xrv.weights(b, s)
                self.assertGreater(w['ball'], 0)
                self.assertLess(w['called_strike'], 0)
                self.assertEqual(w['whiff'], w['called_strike'])
                self.assertEqual(w['foul'], 0 if s == 2 else w['called_strike'])
        self.assertAlmostEqual(self.xrv.weights(3, 2)['ball'], (.689-.384)/1.304)
        self.assertAlmostEqual(self.xrv.weights(3, 2)['whiff'], -.384/1.304)
        self.assertAlmostEqual(self.xrv.weights(0, 0)['called_strike'], (.262-.310)/1.304)

    def test_in_play_comes_from_external_contact_totals(self):
        expected = ((41595-8137-849-4186)*.892 + 8137*1.283 + 849*1.635 + 4186*2.135) / (165614-37441+1277+1343)
        self.assertAlmostEqual(self.xrv.contact_woba, expected)
        # Same contact value at every count, before subtracting starting expectation.
        self.assertAlmostEqual(self.xrv.weights(0, 0)['in_play']*1.304+.310,
                               self.xrv.weights(3, 2)['in_play']*1.304+.384)

    def test_weighted_value_and_units(self):
        p = {e: 1/6 for e in EVENTS}
        r = self.xrv.evaluate(p, {'balls': 1, 'strikes': 2})
        self.assertEqual(r['status'], 'ok')
        self.assertAlmostEqual(r['runs_per_pitch'], sum(self.xrv.weights(1, 2).values())/6)
        self.assertAlmostEqual(r['runs_per_100'], 100*r['runs_per_pitch'])
        self.assertAlmostEqual(sum(r['contributions'].values()), r['runs_per_pitch'])

    def test_missing_count_is_not_assumed_zero_zero(self):
        for count in ({}, {'balls': 0}, {'balls': True, 'strikes': 0}, {'balls': 4, 'strikes': 2}):
            r = self.xrv.evaluate(one_hot('ball'), count)
            self.assertEqual(r['status'], 'missing_or_invalid_count')
            self.assertIsNone(r['runs_per_pitch'])

    def test_invalid_predictions_do_not_create_run_estimates(self):
        for p in ({}, one_hot('ball') | {'in_play': float('nan')},
                  one_hot('ball') | {'foul': .1}, one_hot('ball') | {'ball': True}):
            self.assertEqual(self.xrv.evaluate(p, {'balls': 0, 'strikes': 0})['status'], 'invalid_event_probabilities')
        r = self.xrv.evaluate(one_hot('ball'), {'balls': 0, 'strikes': 0}, 'invalid_input')
        self.assertIsNone(r['runs_per_pitch'])

    def test_count_reference_uses_same_units_and_weights(self):
        class CountBaseline:
            def predict(self, frame):
                import numpy as np
                return np.array([[.4, .15, .1, .15, .19, .01]]), ['group']
        baseline = CountBaseline()
        xrv = ExternalRunValue(baseline=baseline)
        import pandas as pd
        count = {'balls': 3, 'strikes': 2}
        p, _ = baseline.predict(pd.DataFrame([count]))
        r = xrv.evaluate(dict(zip(EVENTS, p[0].tolist())), count)
        self.assertAlmostEqual(r['delta_vs_count_baseline'], 0)

    def test_http_provenance_and_missing_context(self):
        class CompletePredictor(Predictor):
            def records(self, rows, family):
                return [r | {'probabilities': one_hot('whiff')} for r in super().records(rows, family)]
        with TestClient(create_app(CompletePredictor(), Simulator())) as client:
            metadata = client.get('/api/v1/xrv').json()
            self.assertEqual(metadata['season'], 2014)
            self.assertEqual(len(metadata['weights_sha256']), 64)
            response = client.post('/api/v1/predict', json={'records': [EXAMPLE | {'strikes': 2}]})
            self.assertEqual(response.status_code, 200, response.text)
            r = response.json()['records'][0]['pitching']['xrv']
            self.assertAlmostEqual(r['runs_per_pitch'], -.196/1.304)
            physical = {k: v for k, v in EXAMPLE.items() if k not in ('balls', 'strikes')}
            r = client.post('/api/v1/predict', json={'records': [physical], 'family': 'stuff'}).json()['records'][0]['stuff']['xrv']
            self.assertEqual(r['status'], 'missing_or_invalid_count')


if __name__ == '__main__':
    unittest.main()
