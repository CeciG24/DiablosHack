import unittest
from threading import RLock

import pandas as pd

from backend.score_cache import score_frame
from tests.test_backend import Predictor


class PhysicalPredictor(Predictor):
    def records(self, rows, family):
        output = super().records(rows, family)
        for row, prediction in zip(rows, output):
            prediction['score'] = 100 + row['induced_vert_break']
        return output


class ScoreCacheTests(unittest.TestCase):
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
