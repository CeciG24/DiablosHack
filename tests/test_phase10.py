import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from experiments.phase9 import engineer
from experiments.phase10 import paired
from experiments.phase10_features import trajectory, Repertoire, REGULARIZED, GEOMETRY, POINTS
from experiments.phase10_models import EventModel, MovementModel, EVENT_FEATURES, MOVEMENT_FEATURES, movement_support, scenario_support
from tests.modeling.test_families import contextual
from tests.modeling.test_stuff import PARAMS

CFG=json.loads((Path(__file__).parents[1]/'config/phase10.json').read_text(encoding='utf-8'))


def fixture(partition='train',n=360):
    rows=contextual(partition,n)
    rows['auto_pitch_type']=np.where(np.arange(n)%4<2,'Four-Seam','Slider')
    rows['pitcher_throws']=np.where(np.arange(n)%2,'Left','Right')
    rows['pitcher_anon_id']=['pitcher-'+str(i%12) for i in range(n)]
    rows['altitude_category']=np.where(np.arange(n)%3,'No Altitude','Extreme Altitude')
    rows['rel_height']=6.;rows['rel_side']=1.;rows['extension']=6.;rows['zone_time']=.4
    for axis,start,end,accel in [('x',54.5,17/12,0.),('y',6.,rows.plate_loc_height,-8.),('z',-1.,-rows.plate_loc_side,0.)]:
        rows['pitch_trajectory_'+axis+'c0']=start
        rows['pitch_trajectory_'+axis+'c1']=(end-start-accel*.4**2)/.4
        rows['pitch_trajectory_'+axis+'c2']=accel
    return rows


class Phase10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train,_=trajectory(fixture(),CFG,audit=True)
        cls.dev,_=trajectory(fixture('development',120),CFG)
        cls.rep=Repertoire(30).fit(cls.train)
        cls.enriched=cls.rep.transform(engineer(cls.dev))
        cls.cfg=dict(CFG,parameters=PARAMS,event_rounds=8,movement_rounds=8,threads=1)
        cls.event=EventModel('regularized',threads=1).fit_f10(cls.enriched,cls.cfg)
        cls.movement=MovementModel('horz_break',True,threads=1).fit_f10(cls.train,cls.cfg)

    def test_trajectory_recovers_known_planes(self):
        out,audit=trajectory(fixture(),CFG,audit=True)
        self.assertEqual(audit['valid'],len(out))
        for plane in (40,20,8):
            t=(54.5-plane)/((54.5-17/12)/.4)
            expected=6+out.pitch_trajectory_yc1*t-8*t*t
            np.testing.assert_allclose(out['geo_'+str(plane)+'_height'],expected,atol=1e-8)

    def test_axis_mismatch_rejected_and_invalid_rows_flagged(self):
        bad=fixture();bad['pitch_trajectory_zc0']=9
        with self.assertRaises(ValueError):trajectory(bad,CFG,audit=True)
        out,_=trajectory(bad,CFG)
        self.assertTrue(out.geometry_valid.eq(0).all())
        self.assertTrue(out[POINTS].isna().all().all())

    def test_audit_and_history_reject_future(self):
        with self.assertRaises(PermissionError):trajectory(self.dev,CFG,audit=True)
        with self.assertRaises(PermissionError):Repertoire().fit(self.dev)
        with self.assertRaises(PermissionError):movement_support(self.dev,CFG)

    def test_regularization_sparse_reference_and_usage_sum(self):
        out=self.rep.transform(engineer(self.dev))
        np.testing.assert_allclose(out[[f'ars_{i}_usage' for i in range(8)]].sum(axis=1),1)
        self.assertTrue(out[[f'ars_{i}_reliability' for i in range(8)]].ge(0).all().all())
        self.assertTrue(out[[f'ars_{i}_reliability' for i in range(8)]].lt(1).all().all())
        self.assertTrue(np.isfinite(out[REGULARIZED+GEOMETRY]).all().all())

    def test_unknown_pitcher_uses_explicit_prior_and_cold_start_matches(self):
        unknown=self.rep.transform(engineer(self.dev.assign(pitcher_anon_id='unseen')))
        cold=self.rep.transform(engineer(self.dev),cold_start=True)
        np.testing.assert_array_equal(unknown[REGULARIZED+GEOMETRY],cold[REGULARIZED+GEOMETRY])
        self.assertTrue(unknown.history_n.eq(0).all())
        self.assertTrue(unknown.history_status.eq('group_prior_only').all())

    def test_history_order_and_outcome_invariance(self):
        other=Repertoire(30).fit(self.train.sample(frac=1,random_state=7).assign(y_event='unused'))
        np.testing.assert_allclose(self.enriched[REGULARIZED+GEOMETRY],other.transform(engineer(self.dev))[REGULARIZED+GEOMETRY],atol=1e-12)
        changed=self.rep.transform(engineer(self.dev.assign(y_event='unused',pitch_uid='duplicate')))
        np.testing.assert_array_equal(self.enriched[REGULARIZED+GEOMETRY],changed[REGULARIZED+GEOMETRY])

    def test_missing_geometry_uses_flag_and_finite_values(self):
        rows=engineer(self.dev.drop(columns=POINTS+['geometry_valid']))
        out=self.rep.transform(rows)
        self.assertTrue(out[GEOMETRY].eq(0).all().all())

    def test_movement_excludes_outcome_and_measured_movement(self):
        self.assertFalse(set(MOVEMENT_FEATURES)&{'induced_vert_break','horz_break','y_event','pitcher_anon_id','plate_loc_height','plate_loc_side'})
        changed=self.dev.assign(horz_break=999,induced_vert_break=-999,y_event='unused',pitcher_anon_id='new')
        np.testing.assert_array_equal(self.movement.predict(self.dev),self.movement.predict(changed))

    def test_geometry_ablation_controls_own_trajectory(self):
        self.assertTrue(set(POINTS).issubset(EVENT_FEATURES['trajectory']))
        self.assertTrue(set(EVENT_FEATURES['trajectory']).issubset(EVENT_FEATURES['geometry']))
        self.assertFalse(set(POINTS)&set(EVENT_FEATURES['regularized']))
        self.assertNotIn('altitude_category',EVENT_FEATURES['geometry'])

    def test_event_and_movement_fit_partition_guards(self):
        with self.assertRaises(PermissionError):MovementModel('horz_break').fit_f10(self.dev,self.cfg)
        with self.assertRaises(PermissionError):EventModel('base').fit_f10(engineer(self.train),self.cfg)

    def test_save_reload_and_model_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            self.rep.save(folder/'rep'); self.event.save(folder/'event');self.movement.save(folder/'movement')
            np.testing.assert_array_equal(self.enriched[REGULARIZED+GEOMETRY],Repertoire.load(folder/'rep').transform(engineer(self.dev))[REGULARIZED+GEOMETRY])
            np.testing.assert_array_equal(self.event.predict(self.enriched),EventModel.load(folder/'event').predict(self.enriched))
            np.testing.assert_array_equal(self.movement.predict(self.dev),MovementModel.load(folder/'movement').predict(self.dev))
            with (folder/'movement/model.txt').open('a') as handle:handle.write('\nchanged')
            with self.assertRaises(ValueError):MovementModel.load(folder/'movement')

    def test_support_rejects_unknown_category_and_out_of_range(self):
        cfg=dict(CFG,movement_support_min_rows=1,movement_overlap_min_pitches=1,movement_overlap_min_pitchers=1)
        support=movement_support(self.train,cfg)
        self.assertTrue(all(x!='supported_marginal_ranges_only' for x in scenario_support(self.dev,'Harp Helu',support)))
        row=self.train.iloc[:1].copy();row['rel_speed']=500
        self.assertEqual(scenario_support(row,row.altitude_category.iloc[0],support)[0],'outside_training_range')

    def test_paired_bootstrap_known_difference(self):
        result=paired(self.dev,np.ones(len(self.dev)),np.full(len(self.dev),.8),CFG)
        self.assertAlmostEqual(result['delta'],-.2)
        self.assertAlmostEqual(result['ci_low'],-.2)
        self.assertTrue(result['passes'])
        with self.assertRaises(ValueError):paired(self.dev.iloc[:1],np.ones(2),np.ones(2),CFG)


if __name__=='__main__':unittest.main()
