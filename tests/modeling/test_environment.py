import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from modeling.baselines import CLASSES
from modeling.datasets import PITCHING, pd
from modeling.environment import (ENV, MODE, PROBS, EnvironmentEventModel, EnvironmentSimulator,
                                  cohort_delta_interval, training_support)
from modeling.models import TabularEventModel
from modeling.phase6 import subgroup_metrics
from tests.modeling.test_families import contextual
from tests.modeling.test_stuff import PARAMS


def rows(partition='train',n=360):
    result=contextual(partition,n)
    result[ENV]=np.array(['No Altitude','Medium Altitude','Extreme Altitude'])[np.arange(n)//6%3]
    return result


class EnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train,cls.dev=rows(),rows('development',180)
        cls.model=EnvironmentEventModel(True,7,1).fit(cls.train,cls.dev,PARAMS,6,2,1)
        cls.simulator=EnvironmentSimulator(cls.model)

    def test_allowlist_and_only_training_vocabulary(self):
        self.assertEqual(self.model.features,PITCHING+[ENV])
        self.assertEqual(self.model.vocabularies[ENV],sorted(self.train[ENV].unique()))
        with self.assertRaisesRegex(ValueError,'unsupported_environment'):
            EnvironmentEventModel(True,7,1).fit(self.train,self.dev.assign(altitude_category='new'),PARAMS,3,2)

    def test_fit_rejects_review_and_future(self):
        for invalid in (rows('phase_review'),self.train.assign(year=2026)):
            with self.assertRaises(PermissionError):
                EnvironmentEventModel(True,7,1).fit(invalid,self.dev,PARAMS,3,2)

    def test_support_never_fits_on_calibration(self):
        with self.assertRaises(PermissionError):
            training_support(rows('calibration'),self.model.numeric)

    def test_unknown_environment_null_and_no_harp_mapping(self):
        for category in ('new','Harp Helu','sea level',None):
            result=self.simulator.simulate(self.dev.head(5),category)
            self.assertTrue(result.status.eq('unsupported_environment').all())
            self.assertTrue(result[['delta_'+p for p in PROBS]].isna().all().all())

    def test_unknown_source_also_rejected(self):
        result=self.simulator.simulate(self.dev.head(3).assign(altitude_category='unknown'),'No Altitude')
        self.assertTrue(result.status.eq('unsupported_environment').all())

    def test_mixed_invalid_batch_keeps_rows_and_order(self):
        inputs=self.dev.head(4).copy()
        inputs.loc[0,'rel_speed']=np.nan
        inputs.loc[1,ENV]='new'
        inputs.loc[2,'balls']=5
        output=self.simulator.predict(inputs)
        self.assertEqual(output.pitch_uid.tolist(),inputs.pitch_uid.tolist())
        self.assertEqual(output.status.tolist(),['invalid_input','unsupported_environment','invalid_input','ok'])
        self.assertTrue(output.loc[:2,PROBS].isna().all().all())
        self.assertAlmostEqual(output.loc[3,PROBS].sum(),1.)

    def test_same_environment_zero_delta(self):
        result=self.simulator.simulate(self.dev,self.dev[ENV].to_numpy())
        np.testing.assert_array_equal(result[['delta_'+p for p in PROBS]],0.)

    def test_scenario_changes_only_category_and_keeps_ivb_and_arsenal(self):
        inputs=self.dev.head(12).copy()
        inputs['velo_diff_vs_fb']=5.
        snapshot=inputs.copy(deep=True)
        with patch.object(self.model,'predict',wraps=self.model.predict) as predict:
            self.simulator.simulate(inputs,'No Altitude')
            source,target=[call.args[0] for call in predict.call_args_list]
            pd.testing.assert_frame_equal(source.drop(columns=ENV),target.drop(columns=ENV))
            self.assertTrue(target[ENV].eq('No Altitude').all())
        pd.testing.assert_frame_equal(inputs,snapshot)

    def test_outside_support_warning_no_recommendation(self):
        output=self.simulator.predict(self.dev.head(4).assign(induced_vert_break=1e6))
        self.assertTrue(output.input_support_status.eq('outside_support').all())
        self.assertTrue(output.warnings.str.contains('induced_vert_break').all())
        self.assertFalse(output.recommendation_allowed.any())

    def test_unknown_pitch_type_warns(self):
        output=self.simulator.predict(self.dev.head(3).assign(auto_pitch_type='unknown'))
        self.assertTrue(output.status.eq('ok').all())
        self.assertTrue(output.input_support_status.eq('outside_support').all())

    def test_model_reload_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'model'
            self.model.save(folder)
            loaded=EnvironmentEventModel.load(folder)
            np.testing.assert_array_equal(self.model.predict(self.dev),loaded.predict(self.dev))
            metadata=json.loads((folder/'preprocessing.json').read_text())
            metadata['environment_support']['categories']=['wrong']
            (folder/'preprocessing.json').write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                EnvironmentEventModel.load(folder)

    def test_stuff_location_and_control_invariant(self):
        changed=self.dev.assign(altitude_category='unseen')
        for family in ('stuff','location','pitching'):
            model=TabularEventModel(7,1,family).fit(self.train,self.dev,PARAMS,3,2)
            np.testing.assert_array_equal(model.predict(self.dev),model.predict(changed))

    def test_outcomes_and_ids_are_not_predictors(self):
        original=self.model.predict(self.dev)
        changed=self.dev.assign(y_event='wrong',pitcher_anon_id='new',pitch_uid='ignored')
        np.testing.assert_array_equal(original,self.model.predict(changed))

    def test_empty_input_is_supported(self):
        self.assertEqual(len(self.simulator.predict(self.dev.iloc[:0])),0)

    def test_cluster_interval_is_pitch_weighted_and_reproducible(self):
        frame=pd.DataFrame(dict(pitch_uid=['a','b','c'],status='ok',input_support_status='within_checked_support'))
        for p in PROBS:
            frame['delta_'+p]=[.1,.1,-.2]
        games=pd.DataFrame(dict(pitch_uid=['a','b','c'],game_anon_id=['g1','g1','g2']))
        result=cohort_delta_interval(frame,games,20,7,minimum=2)
        self.assertAlmostEqual(result['classes']['ball']['mean_delta'],0.)
        self.assertIn('not_individual_not_causal',result['scope'])
        self.assertEqual(result,cohort_delta_interval(frame.sample(frac=1,random_state=2),games,20,7,minimum=2))
        frame.loc[2,'input_support_status']='outside_support'
        sparse=cohort_delta_interval(frame,games,20,7,minimum=2)
        self.assertEqual(sparse['status'],'insufficient_data')
        self.assertEqual(sparse['n_excluded'],1)
        self.assertEqual(sparse['classes'],{})

    def test_cluster_requires_valid_game_join(self):
        scenario=self.simulator.simulate(self.dev.head(4),'No Altitude')
        with self.assertRaises(ValueError):
            cohort_delta_interval(scenario,self.dev.head(3),20,7)

    def test_subgroups_do_not_rank_insufficient_samples(self):
        cfg={'evaluation':{'auxiliary_min_rows_per_fit_and_review':200,
            'auxiliary_min_each_class_per_fit_and_review':20}}
        review=rows('phase_review',12)
        p=self.model.predict(review)
        groups=subgroup_metrics(self.train,review,p,p,cfg,True)
        self.assertTrue(all(g['status']=='insufficient_data' and g['metrics'] is None and g['comparison'] is None for g in groups))
        self.assertTrue(all(not g['ranking_allowed'] for g in groups))

    def test_simulator_always_labels_association_and_experimental(self):
        result=self.simulator.simulate(self.dev.head(3),'No Altitude')
        self.assertTrue(result.environment_mode.eq(MODE).all())
        self.assertTrue(result.candidate_status.eq('experimental').all())
        self.assertFalse(result.recommendation_allowed.any())
