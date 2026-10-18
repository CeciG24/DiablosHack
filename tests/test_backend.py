"""HTTP contracts with synthetic doubles; optional private-artifact integration."""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.schemas import EXAMPLE


class Predictor:
    lock = {'release_id': 'fixture'}
    contract = {'physical_review_bounds': {}, 'altitude_categories': ['No Altitude']}

    def records(self, rows, family):
        return [dict(family=family, status='ok', score=100+i*10,
                     stuff_plus=100 if family == 'stuff' else None,
                     location_plus=100 if family == 'location' else None,
                     pitching_plus=100 if family == 'pitching' else None,
                     probabilities={'whiff': .2}, conditional_probabilities={},
                     warnings='', score_version='fixture', provisional=True) for i, r in enumerate(rows)]


class Simulator:
    def simulate(self, rows, target):
        return [dict(pitch_uid=r.get('pitch_uid'), source=r['altitude_category'], target=target,
                     status='experimental', reason='supported', delta_score=0,
                     source_score=100, target_score=100, scope='fixture', score_version='fixture') for r in rows]


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.context = TestClient(create_app(Predictor(), Simulator()))
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)

    def test_swagger_and_openapi(self):
        self.assertEqual(self.client.get('/docs').status_code, 200)
        schema = self.client.get('/openapi.json').json()
        self.assertIn('/api/v1/simulate', schema['paths'])
        self.assertIn('PredictionResponse', schema['components']['schemas'])
        self.assertEqual(self.client.get('/ready').status_code, 200)

    def test_scores_and_summary(self):
        payload = {'records': [EXAMPLE, EXAMPLE]}
        result = self.client.post('/api/v1/predict', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(set(result.json()['records'][0]), {'stuff', 'location', 'pitching'})
        summary = self.client.post('/api/v1/summary', json=payload).json()
        self.assertEqual(summary['pitchers'][0]['pitching_plus'], 105)
        self.assertEqual(summary['arsenal'][0]['coverage'], 1)
        self.assertEqual(self.client.post('/api/v1/movement-map', json=payload).json()['records'][0]['ivb'], 16)

    def test_validation(self):
        for updates in ({'rel_speed': -1}, {'balls': True}, {'rel_speed': True}, {'spin_axis_cos': .5},
                        {'altitude_category': 'Harp Helu'}, {'y_event': 'whiff'}):
            response = self.client.post('/api/v1/predict', json={'records': [EXAMPLE | updates]})
            self.assertEqual(response.status_code, 422, response.text)
        for records in ([], [EXAMPLE]*201):
            self.assertEqual(self.client.post('/api/v1/predict', json={'records': records}).status_code, 422)
        physical = {k: v for k, v in EXAMPLE.items() if k not in ('balls', 'strikes', 'batter_side', 'plate_loc_height', 'plate_loc_side')}
        self.assertEqual(self.client.post('/api/v1/predict', json={'records': [physical], 'family': 'stuff'}).status_code, 200)
        self.assertEqual(self.client.post('/api/v1/predict', json={'records': [physical]}).status_code, 422)

    def test_simulation_and_recommendations(self):
        payload = {'records': [EXAMPLE], 'target': 'No Altitude'}
        self.assertEqual(self.client.post('/api/v1/simulate', json=payload).json()['records'][0]['delta_score'], 0)
        self.assertEqual(self.client.post('/api/v1/recommendations', json=payload).json()['supported'], 1)
        payload['target'] = 'Harp Helu'
        self.assertEqual(self.client.post('/api/v1/simulate', json=payload).status_code, 422)

    def test_body_limit(self):
        response = self.client.post('/api/v1/predict', content=b' '*1_000_001)
        self.assertEqual(response.status_code, 413)

    def test_missing_artifacts(self):
        with patch('backend.main.ReleasePredictor', side_effect=FileNotFoundError), patch('backend.main.Simulator', side_effect=ValueError):
            with self.assertLogs('backend.main', level='ERROR'), TestClient(create_app()) as client:
                self.assertEqual(client.get('/health').status_code, 200)
                self.assertEqual(client.get('/ready').status_code, 503)
                self.assertEqual(client.get('/docs').status_code, 200)
                self.assertEqual(client.post('/api/v1/predict', json={'records': [EXAMPLE]}).status_code, 503)


@unittest.skipUnless(os.getenv('DIABLOS_INTEGRATION') == '1', 'requires private F8/F10 artifacts')
class RealModelTests(unittest.TestCase):
    def test_real_models(self):
        with TestClient(create_app()) as client:
            self.assertEqual(client.get('/ready').status_code, 200)
            response = client.post('/api/v1/predict', json={'records': [EXAMPLE]})
            self.assertEqual(response.status_code, 200, response.text)
            for family, row in response.json()['records'][0].items():
                self.assertEqual(row['status'], 'ok')
                self.assertAlmostEqual(sum(row['probabilities'].values()), 1)
                direct = client.app.state.predictor.records([EXAMPLE], family)[0]
                self.assertAlmostEqual(row['score'], direct['score'])
            for route in ('summary', 'movement-map', 'recommendations'):
                result = client.post('/api/v1/'+route, json={'records': [EXAMPLE]})
                self.assertEqual(result.status_code, 200, result.text)
            response = client.post('/api/v1/simulate', json={'records': [EXAMPLE], 'target': 'No Altitude'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['records'][0]['delta_score'], 0)
            response = client.post('/api/v1/simulate', json={'records': [EXAMPLE], 'target': 'Extreme Altitude'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['records'][0]['status'], 'experimental')
            mixed = [EXAMPLE | {'pitch_uid': 'first'}, EXAMPLE | {'auto_pitch_type': 'Unknown'}]
            response = client.post('/api/v1/simulate', json={'records': mixed})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIsNone(response.json()['records'][1]['pitch_uid'])
            self.assertEqual(response.json()['records'][1]['status'], 'unsupported')
            self.assertIsNone(response.json()['records'][1]['delta_score'])
            physical = {k: v for k, v in EXAMPLE.items() if k not in ('balls', 'strikes', 'batter_side', 'plate_loc_height', 'plate_loc_side')}
            response = client.post('/api/v1/simulate', json={'records': [physical]})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['records'][0]['contact_status'], 'unavailable')
            self.assertEqual(client.get('/api/v1/validation').status_code, 200)


if __name__ == '__main__':
    unittest.main()
