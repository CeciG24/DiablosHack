import unittest
from threading import RLock
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.profiler import reference_summary
from backend.schemas import EXAMPLE
from backend.score_cache import score_frame
from tests.test_backend import Predictor


class PhysicalPredictor(Predictor):
    def records(self, rows, family):
        output = super().records(rows, family)
        for row, prediction in zip(rows, output):
            prediction['score'] = 100 + row['induced_vert_break']
        return output


class MovementSimulator:
    def simulate(self, rows, target):
        output = []
        for r in rows:
            supported = r['rel_speed'] >= 50
            change = 0 if target == r['altitude_category'] else -3
            output.append(dict(source=r['altitude_category'], target=target,
                status='experimental' if supported else 'unsupported', reason='fixture',
                delta_score=-99, source_score=200, target_score=101,
                target_ivb=r['induced_vert_break']+change if supported else None,
                target_hb=r['horz_break'] if supported else None, scope='fixture', score_version='F10'))
        return output


class ProfilerTests(unittest.TestCase):
    def entry(self, key, weight=1, **updates):
        return dict(key=key, weight=weight, observed_n=1,
                    pitch={k: v for k, v in (EXAMPLE | updates).items() if k != 'pitcher_anon_id'})

    def test_evaluation_uses_paired_support_and_never_relabels_f10(self):
        with TestClient(create_app(PhysicalPredictor(), MovementSimulator())) as client:
            response = client.post('/api/v1/profiler/evaluate', json=dict(mode='profiles',
                target='Extreme Altitude', entries=[self.entry('a', 25), self.entry('b', 75, rel_speed=40)]))
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result['summary']['source_score'], 116)
            self.assertEqual(result['summary']['target_score'], 113)
            self.assertEqual(result['summary']['paired_source_score'], 116)
            self.assertEqual(result['summary']['delta'], -3)
            self.assertEqual(result['summary']['coverage'], .25)
            self.assertIsNone(result['records'][1]['target_score'])
            self.assertTrue(result['representative'])
            self.assertFalse(result['arsenal_in_model'])
            self.assertIsNone(result['summary']['interval'])

    def test_observed_rows_and_reference_validation(self):
        with TestClient(create_app(PhysicalPredictor(), MovementSimulator())) as client:
            data = dict(mode='pitches', entries=[self.entry('a')], target='No Altitude')
            self.assertEqual(client.post('/api/v1/profiler/evaluate', json=data).json()['summary']['delta'], 0)
            injected = self.entry('a')
            injected['pitch']['pitcher_anon_id'] = 'invented'
            for entries in ([self.entry('a', 2)], [self.entry('a'), self.entry('a')], [injected]):
                self.assertEqual(client.post('/api/v1/profiler/evaluate', json=data | {'entries': entries}).status_code, 422)
            self.assertEqual(client.get('/api/v1/profiler/reference?season=2024').status_code, 422)

    def test_reference_is_filtered_by_hand_year_and_physical_completeness(self):
        frame = pd.DataFrame([EXAMPLE | dict(pitch_uid=str(i), year=y, pitcher_anon_id='p',
            pitcher_throws=hand, rel_speed=speed) for i, (y, hand, speed) in enumerate([
                (2025, 'Right', 90), (2026, 'Right', 100), (2026, 'Left', 92),
                (2024, 'Right', 95), (2026, 'Right', None), (2026, None, 92)])])
        result = reference_summary(frame, (2025, 2026), 'Right', 'fixture')
        self.assertEqual(result['complete_n'], 2)
        self.assertEqual(result['excluded_n'], 1)
        self.assertEqual(result['by_year'], {'2025': 1, '2026': 1})
        self.assertEqual(result['groups'][0]['quantiles']['rel_speed']['p50'], 95)
        arrow = frame.convert_dtypes(dtype_backend='pyarrow')
        self.assertEqual(reference_summary(arrow, (2025, 2026), 'Right', 'fixture')['complete_n'], 2)
        with patch('backend.profiler.reference_frame', return_value=(frame, 'fixture')) as read:
            with TestClient(create_app(PhysicalPredictor(), MovementSimulator())) as client:
                response = client.get('/api/v1/profiler/reference?season=2026&hand=Left')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['complete_n'], 1)
                client.get('/api/v1/profiler/reference?season=2025')
                self.assertEqual(read.call_count, 1)

    def test_cache_chunks_release_inference_lock_and_preserve_row_order(self):
        frame = pd.DataFrame({'induced_vert_break': range(7)})
        predictor = PhysicalPredictor()
        # Use a small counted context instead of testing interpreter-specific lock scheduling.
        class CountLock:
            count = 0
            def __enter__(self): self.count += 1
            def __exit__(self, *args): pass
        inference = CountLock()
        score_frame(frame, predictor, None, RLock(), inference, batch_size=3)
        self.assertEqual(inference.count, 9)
        self.assertEqual(frame.stuff_plus.tolist(), list(range(100, 107)))
        self.assertTrue(frame.attrs['f8_scored'])
        score_frame(frame, predictor, None, RLock(), inference, batch_size=3)
        self.assertEqual(inference.count, 9)
