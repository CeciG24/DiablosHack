import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from modeling.calibration import TemperatureScaler, calibration_decision
from modeling.contact import (HEADS, AuxiliaryModel, average_precision, derive_targets, head_metrics,
                              joint_contact_probabilities, sample_support, smoothed_prevalence)
from modeling.datasets import pd
from modeling.metrics import multiclass_metrics
from modeling.phase4 import calibrate, train_head
from tests.modeling.test_families import contextual
from tests.modeling.test_stuff import PARAMS


def auxiliary_rows(partition='train', n=360):
    rows = contextual(partition, n)
    rows['contact'] = [HEADS['contact'][i % 3] for i in range(n)]
    rows['groundball'] = [HEADS['groundball'][i % 2] for i in range(n)]
    rows['chase'] = [HEADS['chase'][i % 2] for i in range(n)]
    rows['game_cv_fold'] = np.arange(n) % 5
    return rows


class CalibrationContactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train = auxiliary_rows()
        cls.dev = auxiliary_rows('development', 240)
        cls.model = AuxiliaryModel('pitching', 'contact', 7, 1).fit(cls.train, cls.dev, PARAMS, 8, 3)

    def test_temperature_only_sees_2025_calibration(self):
        p = np.tile([.2, .3, .5], (240, 1))
        for partition in ('train', 'development', 'phase_review', 'test'):
            rows = auxiliary_rows(partition, 240)
            with self.assertRaises(PermissionError):
                TemperatureScaler(HEADS['contact']).fit(rows, p, 'contact')
        rows = auxiliary_rows('calibration', 240)
        rows['year'] = 2026
        with self.assertRaises(PermissionError):
            TemperatureScaler(HEADS['contact']).fit(rows, p, 'contact')

    def test_temperature_improves_overconfidence_and_normalizes(self):
        rows = auxiliary_rows('calibration', 240)
        p = np.tile([.95, .03, .02], (240, 1))
        scaler = TemperatureScaler(HEADS['contact']).fit(rows, p, 'contact')
        self.assertGreater(scaler.temperature, 1)
        transformed = scaler.transform(p)
        np.testing.assert_allclose(transformed.sum(axis=1), 1, atol=1e-12)
        self.assertLess(multiclass_metrics(rows.contact, transformed, HEADS['contact'])['multiclass_log_loss'],
                        multiclass_metrics(rows.contact, p, HEADS['contact'])['multiclass_log_loss'])

    def test_scaler_reload_and_invalid_temperature(self):
        rows = auxiliary_rows('calibration', 240)
        p = np.tile([.8, .1, .1], (240, 1))
        scaler = TemperatureScaler(HEADS['contact']).fit(rows, p, 'contact')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'temperature.json'
            scaler.save(path)
            np.testing.assert_array_equal(scaler.transform(p), TemperatureScaler.load(path).transform(p))
            state = json.loads(path.read_text()); state['temperature'] = -1
            path.write_text(json.dumps(state))
            with self.assertRaises(ValueError):
                TemperatureScaler.load(path)

    def test_identity_fallback_and_tolerance(self):
        self.assertEqual(calibration_decision(1., 1.0001), 'identity')
        self.assertEqual(calibration_decision(1., .99), 'temperature')
        with self.assertRaises(ValueError):
            calibration_decision(1., .99, .01)
        p = np.array([[0., .5, .5]])
        np.testing.assert_array_equal(TemperatureScaler(HEADS['contact']).transform(p), p)

    def test_nulls_are_not_contact_negatives(self):
        rows = pd.DataFrame({'y_event':['in_play','in_play','in_play','ball','in_play'],
            'y_weak_contact_proxy_bip':[1,0,0,None,None], 'y_hard_contact_bip':[0,0,1,None,None],
            'y_groundball_bip':[0,1,None,None,None], 'y_chase_given_outside':[1,None,None,0,None]})
        result = derive_targets(rows)
        self.assertEqual(result.contact.iloc[:3].tolist(), ['weak','medium','hard'])
        self.assertTrue(result.contact.iloc[3:].isna().all())
        self.assertTrue(result.groundball.iloc[2:].isna().all())
        self.assertEqual(result.chase.iloc[3], 'take')

    def test_contradictory_and_non_bip_labels_rejected(self):
        for weak, hard, event in [(1,1,'in_play'), (None,0,'in_play'), (1,0,'ball')]:
            rows = pd.DataFrame({'y_event':[event], 'y_weak_contact_proxy_bip':[weak], 'y_hard_contact_bip':[hard],
                                 'y_groundball_bip':[None], 'y_chase_given_outside':[None]})
            with self.assertRaises(ValueError):
                derive_targets(rows)

    def test_minimum_rows_and_class_sizes(self):
        self.assertTrue(sample_support(self.train, 'contact', HEADS['contact'])['sufficient'])
        self.assertFalse(sample_support(self.train.head(199), 'contact', HEADS['contact'])['sufficient'])
        rows = self.train.copy(); rows['contact'] = 'weak'; rows.loc[:18,'contact'] = 'hard'
        self.assertFalse(sample_support(rows,'contact',HEADS['contact'])['sufficient'])

    def test_prevalence_train_only_and_smoothing(self):
        p = smoothed_prevalence(self.train,'contact',HEADS['contact'])
        np.testing.assert_allclose(p, [1/3]*3)
        with self.assertRaises(PermissionError):
            smoothed_prevalence(self.dev,'contact',HEADS['contact'])

    def test_joint_probabilities_and_exclusivity(self):
        event = np.tile([.2,.2,.1,.1,.3,.1],(2,1))
        conditional = np.tile([.1,.4,.5],(2,1))
        joint = joint_contact_probabilities(event,conditional)
        np.testing.assert_allclose(joint, np.tile([.03,.12,.15],(2,1)))
        self.assertTrue(np.all(joint[:,0]+joint[:,2] <= event[:,4]))
        with self.assertRaises(ValueError):
            joint_contact_probabilities(event, np.tile([.8,.2,.7],(2,1)))

    def test_auxiliary_reload_and_feature_invariance(self):
        expected = self.model.predict(self.dev)
        changed = self.dev.copy(); changed['altitude_category']='arbitrary'; changed['contact']='unknown'
        np.testing.assert_array_equal(expected,self.model.predict(changed))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model'; self.model.save(path)
            np.testing.assert_array_equal(expected,AuxiliaryModel.load(path).predict(self.dev))
            with (path/'model.txt').open('a') as f: f.write('corrupt')
            with self.assertRaises(ValueError): AuxiliaryModel.load(path)

    def test_auxiliary_rejects_calibration_review_and_null_fit_targets(self):
        for part in ('calibration','phase_review','test'):
            with self.assertRaises(PermissionError):
                AuxiliaryModel('stuff','contact',7,1).fit(self.train,auxiliary_rows(part),PARAMS,4,2)
        rows=self.train.copy(); rows.loc[0,'contact']=pd.NA
        with self.assertRaises(ValueError): AuxiliaryModel('stuff','contact',7,1).fit(rows,self.dev,PARAMS,4,2)

    def test_two_class_model_returns_joint_distribution(self):
        model=AuxiliaryModel('location','groundball',7,1).fit(self.train,self.dev,PARAMS,4,2)
        p=model.predict(self.dev)
        self.assertEqual(p.shape,(240,2))
        np.testing.assert_allclose(p.sum(axis=1),1,atol=1e-12)

    def test_binary_metrics_and_tied_PR_auc(self):
        self.assertEqual(average_precision([0,1,0,1],[.5]*4),.5)
        self.assertEqual(average_precision([0,1],[.1,.9]),1.)
        result=head_metrics(['no','yes'],np.array([[.8,.2],[.1,.9]]),['no','yes'])
        self.assertAlmostEqual(result['binary_yes']['brier'],.025)

    def test_insufficient_head_returns_null_and_no_inferential_metrics(self):
        cfg=json.loads(Path('config/modeling_contract.json').read_text())
        rows=pd.concat([auxiliary_rows(p,12) for p in ('train','development','calibration','phase_review')],ignore_index=True)
        with tempfile.TemporaryDirectory() as tmp:
            p, decision=train_head(rows,rows.loc[rows.partition.ne('train')],'stuff','contact',Path(tmp)/'head',cfg,True,{})
            self.assertIsNone(p)
            self.assertEqual(decision['status'],'insufficient_data')
            self.assertIsNone(decision['comparison'])
            self.assertFalse((Path(tmp)/'head/model').exists())

    def test_sparse_calibration_keeps_identity(self):
        cfg=json.loads(Path('config/modeling_contract.json').read_text())
        rows=pd.concat([auxiliary_rows('calibration',12),auxiliary_rows('phase_review',240),auxiliary_rows('development',240)],ignore_index=True)
        p=np.tile([.2,.3,.5],(len(rows),1))
        with tempfile.TemporaryDirectory() as tmp:
            selected, _, policy=calibrate(rows,p,'contact',HEADS['contact'],Path(tmp),cfg,auxiliary=True,smoke=True)
            self.assertEqual(policy['route'],'identity')
            np.testing.assert_array_equal(p,selected)
            self.assertFalse((Path(tmp)/'temperature.json').exists())
