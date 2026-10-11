import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from modeling.arsenal import (ARSENAL, ArsenalEventModel, attach_reference, build_reference, route_probabilities)
from modeling.datasets import pd
from tests.modeling.test_families import contextual
from tests.modeling.test_stuff import PARAMS


def history():
    return pd.DataFrame([dict(pitch_uid=f'{kind}-{i}', year=2024, pitcher_anon_id='p',
        auto_pitch_type=kind, rel_speed=90., induced_vert_break=12., horz_break=4., rel_height=6., rel_side=2.)
        for kind in ('Four-Seam','Sinker') for i in range(30)])


class ArsenalTests(unittest.TestCase):
    def test_future_history_rejected(self):
        for year in (2025, 2026):
            with self.assertRaises(PermissionError):
                build_reference(history().assign(year=year))

    def test_tie_minimum_and_order(self):
        h = history()
        refs = build_reference(h)
        self.assertEqual(refs[0].iloc[0].reference_fastball_type, 'Four-Seam')
        self.assertEqual(refs[0].iloc[0].fb_n, 30)
        for a,b in zip(refs, build_reference(h.sample(frac=1, random_state=2))):
            pd.testing.assert_frame_equal(a,b)
        self.assertTrue(build_reference(h.iloc[:29])[0].empty)

    def test_missing_physics_does_not_count_toward_minimum(self):
        h = history().iloc[:30].copy()
        h.loc[0,'rel_speed'] = np.nan
        self.assertTrue(build_reference(h)[0].empty)

    def test_features_and_unknown_type_usage(self):
        row = history().iloc[:1].assign(year=2025, rel_speed=95., rel_height=9., rel_side=6., auto_pitch_type='Slider')
        result = attach_reference(row, *build_reference(history()))
        self.assertEqual(result.iloc[0].historical_type_usage, 0.)
        self.assertEqual(result.iloc[0].velo_diff_vs_fb, 5.)
        self.assertEqual(result.iloc[0].release_distance_vs_fb, 5.)

    def test_outcomes_do_not_change_features(self):
        row = history().iloc[:1].assign(year=2025, y_event='whiff')
        refs = build_reference(history().assign(y_event='ball'))
        a = attach_reference(row, *refs)
        b = attach_reference(row.assign(y_event='in_play'), *refs)
        pd.testing.assert_frame_equal(a[ARSENAL],b[ARSENAL])

    def test_no_history_and_cold_start(self):
        row = history().iloc[:1].assign(year=2025)
        refs = build_reference(history())
        self.assertFalse(attach_reference(row.assign(pitcher_anon_id='new'), *refs).has_reference.any())
        cold = attach_reference(row, *refs, cold_start=True)
        self.assertFalse(cold.has_reference.any())
        self.assertTrue(cold[ARSENAL].isna().all().all())

    def test_reference_unchanged_for_future_input_without_labels(self):
        row = history().iloc[:1].assign(year=2025)
        refs = build_reference(history())
        pd.testing.assert_frame_equal(attach_reference(row,*refs)[ARSENAL],
                                      attach_reference(row.assign(year=2026),*refs)[ARSENAL])

    def test_duplicate_reference_rejected(self):
        row = history().iloc[:1].assign(year=2025)
        refs, counts, totals = build_reference(history())
        with self.assertRaises(pd.errors.MergeError):
            attach_reference(row,pd.concat([refs,refs]),counts,totals)

    def test_fit_rejects_other_partitions_and_years(self):
        for part in ('train','calibration','phase_review'):
            with self.assertRaises(PermissionError):
                ArsenalEventModel().fit(contextual(part,120),PARAMS,3)
        with self.assertRaises(PermissionError):
            ArsenalEventModel().fit(contextual('development',120).assign(year=2026),PARAMS,3)

    def test_model_roundtrip_allowlist_and_tamper(self):
        rows = contextual('development',120)
        for c in ARSENAL:
            rows[c] = np.arange(len(rows))*.01
        for with_arsenal in (False,True):
            model = ArsenalEventModel(with_arsenal,7,1).fit(rows,PARAMS,3)
            predicted = model.predict(rows)
            np.testing.assert_array_equal(predicted, model.predict(rows.assign(y_event='changed',altitude_category='changed',pitcher_anon_id='changed')))
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'model'
                model.save(path)
                np.testing.assert_array_equal(predicted,ArsenalEventModel.load(path).predict(rows))
                state=json.loads((path/'preprocessing.json').read_text())
                state['fit_year']=2024
                (path/'preprocessing.json').write_text(json.dumps(state))
                with self.assertRaises(ValueError):
                    ArsenalEventModel.load(path)

    def test_policy_preserves_order_and_fallback(self):
        base=np.full((3,6),1/6)
        control=np.array([[.5,.1,.1,.1,.1,.1]])
        arsenal=control[:,::-1].copy()
        p,routes=route_probabilities(base,control,arsenal,[False,True,False],True)
        np.testing.assert_array_equal(p[[0,2]],base[[0,2]])
        np.testing.assert_array_equal(p[1],arsenal[0])
        self.assertEqual(routes.tolist(),['fallback','arsenal','fallback'])
        p,_=route_probabilities(base,control,arsenal,[False,True,False],False)
        np.testing.assert_array_equal(p[1],control[0])
