"""HTTP contracts with synthetic doubles; optional private-artifact integration."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.schemas import EXAMPLE


class Predictor:
    lock = {'release_id': 'fixture'}
    contract = {'physical_review_bounds': {}, 'altitude_categories': ['No Altitude']}

    def predict(self, rows, family):
        import pandas as pd
        return pd.DataFrame({'score': [r['score'] for r in self.records(rows, family)]})

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

    def test_final_score_is_separate_and_requires_verified_model_and_context(self):
        payload = {'records': [EXAMPLE]}
        self.assertEqual(self.client.post('/api/v1/final-score', json=payload).status_code, 503)
        model = Mock()
        model.records.return_value = [dict(pitch_uid=None, status='experimental', score=103.,
            probabilities={'whiff': .2, 'ball': .8}, model_id='fixture', score_version='F11',
            history_status='group_prior_only', history_n=0, warnings='group_prior_only',
            context_mode='observed_location_count_batter_side')]
        self.client.app.state.final_predictor = model
        response = self.client.post('/api/v1/final-score', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['records'][0]['score'], 103.)
        self.assertEqual(response.json()['records'][0]['history_n'], 0)
        missing = {'records': [{k: v for k, v in EXAMPLE.items() if k != 'balls'}]}
        self.assertEqual(self.client.post('/api/v1/final-score', json=missing).status_code, 422)
        injected = {'records': [EXAMPLE | {'ars_0_usage': .5}]}
        self.assertEqual(self.client.post('/api/v1/final-score', json=injected).status_code, 422)
        self.assertEqual(set(self.client.post('/api/v1/predict', json=payload).json()['records'][0]),
                         {'stuff', 'location', 'pitching'})

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

    def test_stuff_comparison_rescores_projected_shape_without_changing_context(self):
        payload = {'records': [EXAMPLE], 'target': 'Extreme Altitude'}
        simulator = self.client.app.state.simulator
        simulator.simulate = Mock(return_value=[dict(source='No Altitude', target='Extreme Altitude',
            status='experimental', reason='supported', delta_score=-8, source_score=90, target_score=82,
            target_ivb=12., target_hb=-6., scope='fixture', score_version='F10')])
        predictor = self.client.app.state.predictor
        original = predictor.records
        predictor.records = Mock(side_effect=original)
        result = self.client.post('/api/v1/simulate', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        row = result.json()['records'][0]
        comparison = row['stuff_comparison']
        self.assertEqual((comparison['source_score'], comparison['target_score'], comparison['delta_score']),
                         (100, 110, 10))
        self.assertEqual(row['delta_score'], -8)  # F10 is not relabeled as Stuff+.
        self.assertIsNone(comparison['interval'])
        self.assertEqual(comparison['interval_reason'], 'individual_uncertainty_not_estimated')
        rows, family = predictor.records.call_args.args
        self.assertEqual(family, 'stuff')
        self.assertEqual(rows[0]['induced_vert_break'], EXAMPLE['induced_vert_break'])
        self.assertEqual(rows[1]['induced_vert_break'], 12.)
        self.assertEqual(rows[1]['horz_break'], -6.)
        for field in ('plate_loc_side', 'plate_loc_height', 'balls', 'strikes', 'rel_speed', 'spin_rate'):
            self.assertEqual(rows[0][field], rows[1][field])

    def test_unsupported_or_missing_movement_never_fabricates_stuff_delta(self):
        base = dict(source='No Altitude', target='Extreme Altitude', reason='unsupported',
                    delta_score=None, scope='fixture', score_version='F10')
        predictor = self.client.app.state.predictor
        predictor.records = Mock()
        for extra in ({'status': 'unsupported', 'target_ivb': 12., 'target_hb': -6.},
                      {'status': 'experimental'}):
            self.client.app.state.simulator.simulate = Mock(return_value=[base | extra])
            row = self.client.post('/api/v1/simulate',
                json={'records': [EXAMPLE], 'target': 'Extreme Altitude'}).json()['records'][0]
            self.assertEqual(row['stuff_comparison']['status'], 'unavailable')
            self.assertIsNone(row['stuff_comparison']['delta_score'])
        predictor.records.assert_not_called()

    def test_validation_evidence(self):
        evidence = self.client.get('/api/v1/validation').json()
        self.assertIn('altitude_holdout', evidence)

    def test_scouting_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp)/'scouting.csv'
            csv_path.write_text('pitcher_anon_id,auto_pitch_type,n,games,score,provisional,scope\n'
                                'p1,Four-Seam,300,10,105.0,False,x\n'
                                'p2,Slider,20,3,95.0,True,x\n', encoding='utf-8')
            with patch.dict(os.environ, {'DIABLOS_SCOUTING': str(csv_path)}):
                records = self.client.get('/api/v1/scouting', params={'min_n': 0}).json()['records']
                self.assertEqual(records[0]['pitcher_anon_id'], 'p1')
                filtered = self.client.get('/api/v1/scouting', params={'min_n': 100}).json()['records']
                self.assertEqual(len(filtered), 1)
            env = {k: v for k, v in os.environ.items() if k != 'DIABLOS_SCOUTING'}
            with patch('backend.main.ROOT', Path(tmp)), patch.dict(os.environ, env, clear=True):
                self.assertEqual(self.client.get('/api/v1/scouting').status_code, 503)

    def test_profile_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'docs').mkdir()
            with patch('backend.main.ROOT', Path(tmp)):
                self.assertEqual(self.client.get('/api/v1/profile').status_code, 404)
                (Path(tmp)/'docs'/'F10_IDEAL_PROFILE.json').write_text('{"h1": "demo"}', encoding='utf-8')
                self.assertEqual(self.client.get('/api/v1/profile').json()['h1'], 'demo')

    def _fake_review(self, client):
        """Injecta un frame review y escenarios mínimos para /pitchers y /pitcher/{id}."""
        import pandas as pd
        rows = [dict(pitch_uid=f'u{i}', year=2025, game_anon_id='g1', pitcher_anon_id='p1',
                     pitcher_split='dev', game_cv_fold=0, partition='phase_review',
                     auto_pitch_type='Four-Seam' if i % 2 else 'Slider',
                     altitude_category='No Altitude' if i < 3 else 'Extreme Altitude',
                     experimental_score=105.0, pitcher_throws='Right', rel_speed=93.0,
                     spin_rate=2300.0, spin_axis_sin=0.5, spin_axis_cos=-0.866,
                     rel_height=6.0, rel_side=1.8, extension=6.2, induced_vert_break=16.0,
                     horz_break=-8.0, plate_loc_height=2.5, plate_loc_side=0.0,
                     balls=0, strikes=0, batter_side='Right') for i in range(5)]
        client.app.state.review = pd.DataFrame(rows)
        client.app.state.scenarios = pd.DataFrame([
            dict(pitch_uid='u4', pitcher_anon_id='p1', auto_pitch_type='Four-Seam',
                 source='No Altitude', target='Extreme Altitude', delta_score=-4.0,
                 score_version='v', scope='s'),
            dict(pitch_uid='u1', pitcher_anon_id='p1', auto_pitch_type='Four-Seam',
                 source='No Altitude', target='Extreme Altitude', delta_score=-6.0,
                 score_version='v', scope='s'),
        ])

    def test_pitchers_and_bundle_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, 'DIABLOS_F9': tmp}
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(self.client.get('/api/v1/pitchers').status_code, 503)
        self._fake_review(self.client)
        pitchers = self.client.get('/api/v1/pitchers', params={'min_n': 1}).json()
        self.assertEqual(pitchers['records'][0]['pitcher_anon_id'], 'p1')
        self.assertEqual(self.client.get('/api/v1/pitcher/nadie').status_code, 404)
        bundle = self.client.get('/api/v1/pitcher/p1').json()
        self.assertEqual(bundle['n'], 5)
        self.assertEqual(bundle['throws'], 'Right')
        self.assertEqual(len(bundle['pitches']), 5)
        self.assertIn('stuff_plus', bundle['pitches'][0])
        self.assertEqual(set(bundle['summaries']), {'stuff', 'location', 'pitching'})
        delta = [d for d in bundle['deltas']
                 if d['auto_pitch_type'] == 'Four-Seam' and d['scenario_b'] == 'Extreme Altitude'][0]
        self.assertAlmostEqual(delta['delta_score'], -5.0)
        self.assertEqual(delta['n_simulated'], 2)

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
