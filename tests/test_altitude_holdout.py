import json
import unittest
import numpy as np
import pandas as pd
from modeling.datasets import ROOT
from experiments.altitude_holdout import (HoldoutMovementModel, ORDINAL, make_fold, prepare, metrics)

CFG = json.loads((ROOT/'config/altitude_holdout.json').read_text(encoding='utf-8'))
CFG = dict(CFG, rounds=6, threads=1, parameters=dict(CFG['parameters'], min_data_in_leaf=5))


def synthetic(n=240, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for year in (2024, 2025):
        for k, category in enumerate(CFG['categories']):
            m = n//3
            frame = pd.DataFrame(dict(
                pitch_uid=[f'{year}-{k}-{i}' for i in range(m)], year=year,
                game_anon_id=[f'g-{year}-{k}-{i % 8}' for i in range(m)], pitcher_anon_id=[f'p{i % 12}' for i in range(m)],
                altitude_category=category, auto_pitch_type=rng.choice(['Four-Seam', 'Slider'], m), pitcher_throws=rng.choice(['Left', 'Right'], m),
                rel_speed=rng.normal(90, 4, m), spin_rate=rng.normal(2200, 200, m), spin_axis_sin=rng.uniform(-1, 1, m), spin_axis_cos=rng.uniform(-1, 1, m),
                rel_height=rng.normal(5.8, .3, m), rel_side=rng.normal(1.5, .4, m), extension=rng.normal(6.2, .3, m)))
            base = frame.rel_speed*.1-k*1.5
            frame['induced_vert_break'] = base+rng.normal(0, .5, m)
            frame['horz_break'] = -base+rng.normal(0, .5, m)
            rows.append(frame)
    return prepare(pd.concat(rows, ignore_index=True), CFG)


class AltitudeHoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = synthetic()

    def test_ordinal_encoding_follows_config(self):
        mapped = self.rows.groupby('altitude_category')[ORDINAL].first().to_dict()
        self.assertEqual(mapped, {k: float(v) for k, v in CFG['ordinal'].items()})

    def test_fold_excludes_heldout_category_and_future_years(self):
        for heldout in CFG['categories']:
            train, shifted, indomain = make_fold(self.rows, heldout, CFG)
            self.assertNotIn(heldout, set(train.altitude_category))
            self.assertTrue(train.year.eq(2024).all() and shifted.year.eq(2025).all() and indomain.year.eq(2025).all())
            self.assertTrue(shifted.altitude_category.eq(heldout).all() and indomain.altitude_category.ne(heldout).all())
            self.assertFalse(set(train.pitch_uid) & set(shifted.pitch_uid))

    def test_rejects_unknown_category_and_2026(self):
        with self.assertRaises(ValueError):
            make_fold(self.rows, 'Harp Helu', CFG)
        with self.assertRaises(PermissionError):
            prepare(self.rows.assign(year=2026), CFG)

    def test_rejects_game_spanning_categories(self):
        broken = self.rows.copy()
        broken.loc[broken.index[:2], 'game_anon_id'] = broken.loc[broken.index[-1], 'game_anon_id']
        with self.assertRaises(ValueError):
            prepare(broken, CFG)

    def test_fit_requires_training_year_only(self):
        train, shifted, _ = make_fold(self.rows, 'Extreme Altitude', CFG)
        with self.assertRaises(PermissionError):
            HoldoutMovementModel('induced_vert_break', 'control', CFG).fit_fold(shifted)

    def test_all_variants_fit_predict_and_are_deterministic(self):
        train, shifted, _ = make_fold(self.rows, 'Extreme Altitude', CFG)
        for variant in CFG['variants']:
            a = HoldoutMovementModel('horz_break', variant, CFG).fit_fold(train).predict(shifted)
            b = HoldoutMovementModel('horz_break', variant, CFG).fit_fold(train).predict(shifted)
            np.testing.assert_array_equal(a, b)
            self.assertTrue(np.isfinite(a).all())

    def test_control_cannot_use_altitude_feature(self):
        self.assertNotIn(ORDINAL, HoldoutMovementModel('horz_break', 'control', CFG).features)
        self.assertIn(ORDINAL, HoldoutMovementModel('horz_break', 'ordinal', CFG).features)

    def test_metrics_bias_sign_for_horizontal_orientation(self):
        rows = self.rows.iloc[:6].assign(pitcher_throws=['Left']*3+['Right']*3, horz_break=0.)
        out = metrics(rows, np.ones(6), 'horz_break')
        self.assertAlmostEqual(out['rmse_inches'], 1.)
        self.assertAlmostEqual(out['bias_oriented_inches'], 0.)


if __name__ == '__main__':
    unittest.main()
