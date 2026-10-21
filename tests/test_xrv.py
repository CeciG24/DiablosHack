"""Scientific invariants for external run weights and HTTP integration."""
import unittest
from pathlib import Path
import json
import tempfile
from fastapi.testclient import TestClient
from backend.xrv import ExternalRunValue, EVENTS
from backend.main import create_app
from backend.schemas import EXAMPLE
from tests.test_backend import Predictor, Simulator


def one_hot(event):
    return {e: float(e == event) for e in EVENTS}


class RunValueTests(unittest.TestCase):
    def setUp(self):
        self.xrv = ExternalRunValue(Path(__file__).resolve().parents[1]/'config/xrv_mlb2014.json')

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
            self.assertEqual(metadata['season'], 2024)
            self.assertEqual(metadata['league'], 'LMB')
            self.assertEqual(len(metadata['weights_sha256']), 64)
            response = client.post('/api/v1/predict', json={'records': [EXAMPLE | {'strikes': 2}]})
            self.assertEqual(response.status_code, 200, response.text)
            r = response.json()['records'][0]['pitching']['xrv']
            self.assertAlmostEqual(r['runs_per_pitch'], metadata['event_weights_by_count']['0-2']['whiff'])
            self.assertEqual(r['reference_label'], 'LMB 2024')
            physical = {k: v for k, v in EXAMPLE.items() if k not in ('balls', 'strikes')}
            r = client.post('/api/v1/predict', json={'records': [physical], 'family': 'stuff'}).json()['records'][0]['stuff']['xrv']
            self.assertEqual(r['status'], 'missing_or_invalid_count')


class DirectLmbWeightsTests(unittest.TestCase):
    def test_final_score_keeps_points_and_exposes_separate_lmb_run_value(self):
        from unittest.mock import Mock
        final = Mock()
        final.records.return_value = [dict(pitch_uid=None, status='experimental', score=103.,
            probabilities=one_hot('whiff'), model_id='fixture', score_version='F11',
            history_status='group_prior_only', history_n=0, warnings='',
            context_mode='observed_location_count_batter_side')]
        with TestClient(create_app(Predictor(), Simulator(), final_predictor=final)) as client:
            response = client.post('/api/v1/final-score', json={'records':[EXAMPLE | {'strikes':2}]})
            self.assertEqual(response.status_code,200,response.text)
            row = response.json()['records'][0]
            self.assertEqual(row['score'],103.)
            self.assertFalse(row['represents_runs'])
            self.assertEqual(row['xrv']['status'],'ok')
            self.assertAlmostEqual(row['xrv']['runs_per_pitch'],ExternalRunValue().weights(0,2)['whiff'])

    def test_active_source_support_and_builder_identity_are_auditable(self):
        import hashlib
        root = Path(__file__).resolve().parents[1]
        metadata = ExternalRunValue().metadata()
        self.assertEqual((metadata['league'],metadata['season']),('LMB',2024))
        self.assertNotIn('woba_scale',metadata)
        self.assertGreaterEqual(min(metadata['re24_support'].values()),30)
        self.assertGreaterEqual(min(metadata['count_support'].values()),100)
        self.assertEqual(metadata['builder_sha256'],hashlib.sha256((root/'experiments/lmb_xrv.py').read_bytes()).hexdigest())
        self.assertEqual(metadata['provenance']['download_manifest_sha256'],
                         hashlib.sha256((root/'docs/XRV_LMB2024_SOURCE_MANIFEST.json').read_bytes()).hexdigest())

    def fixture(self):
        weights = {f'{b}-{s}':dict(ball=.04, called_strike=-.03, whiff=-.03,
                    foul=0 if s == 2 else -.03, in_play=.02, hit_by_pitch=.3)
                   for b in range(4) for s in range(3)}
        return dict(schema_version=2, version='xrv_external_lmb2024_v1', league='LMB', season=2024,
                    units='runs_per_pitch',label='LMB 2024',in_play_policy='fixture',
                    event_weights_by_count=weights)

    def test_direct_weights_are_runs_without_mlb_woba_constants(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'weights.json'
            path.write_text(json.dumps(self.fixture()),encoding='utf-8')
            engine = ExternalRunValue(path)
            r = engine.evaluate(one_hot('hit_by_pitch'), {'balls':0,'strikes':0})
            self.assertAlmostEqual(r['runs_per_pitch'], .3)
            self.assertEqual((r['league'],r['season'],r['reference_label']),('LMB',2024,'LMB 2024'))
            self.assertIsNone(engine.metadata()['contact_mean_woba'])
            copied = engine.weights(0,0)
            copied['ball'] = 999
            self.assertEqual(engine.weights(0,0)['ball'],.04)

    def test_direct_weights_reject_incomplete_or_inconsistent_tables(self):
        for mutation in ('year','event','foul','nan'):
            cfg = self.fixture()
            if mutation == 'year': cfg['season'] = 2025
            if mutation == 'event': del cfg['event_weights_by_count']['0-0']['ball']
            if mutation == 'foul': cfg['event_weights_by_count']['0-2']['foul'] = -.1
            if mutation == 'nan': cfg['event_weights_by_count']['0-0']['in_play'] = float('nan')
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'weights.json'
                path.write_text(json.dumps(cfg),encoding='utf-8')
                with self.assertRaises(ValueError):
                    ExternalRunValue(path)


if __name__ == '__main__':
    unittest.main()
