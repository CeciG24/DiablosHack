import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from modeling.inference import ReleasePredictor
from modeling.release import digest,verify_release,authorize_test
from modeling.api import request
from modeling.scoring import FixedScale,S0
from modeling.datasets import sha256_file
from tests.modeling.test_scoring import reference
from tests.modeling.test_environment import rows
from tests.modeling.test_stuff import PARAMS
from modeling.models import TabularEventModel


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train,cls.dev=rows(),rows('development',180)
        for data in (cls.train,cls.dev):
            for column in ('spin_axis_sin','spin_axis_cos'):data[column]=data[column].clip(-1,1)
        cls.model=TabularEventModel(7,1,'pitching','A').fit(cls.train,cls.dev,PARAMS,6,2)
        cls.predictor=ReleasePredictor.__new__(ReleasePredictor)
        cls.predictor.lock=dict(release_id='test',data_run='fixture')
        cls.predictor.support=dict(pitchers=cls.train.pitcher_anon_id.unique().tolist(),numeric_bounds={c:[-1e9,1e9] for c in cls.model.numeric})
        cls.predictor.contract=dict(physical_review_bounds={},altitude_categories=['No Altitude','Medium Altitude','Extreme Altitude'])
        cls.predictor.models={'pitching':cls.model}
        cls.predictor.scales={'pitching':FixedScale.fit(reference(),'pitching',S0,'fixture')}
        cls.predictor.scalers={'pitching':None}
        cls.predictor.heads={'pitching':{}}

    def test_lock_tamper_and_wrong_id(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);(folder/'model.txt').write_text('frozen')
            lock=dict(files={'model.txt':sha256_file(folder/'model.txt')},code_hashes={})
            lock['release_id']=digest(lock)
            (folder/'release_lock.json').write_text(json.dumps(lock))
            self.assertEqual(verify_release(folder,lock['release_id'],False)['release_id'],lock['release_id'])
            with self.assertRaises(ValueError):verify_release(folder,'wrong',False)
            (folder/'model.txt').write_text('changed')
            with self.assertRaises(ValueError):verify_release(folder,lock['release_id'],False)

    def test_authorization_fails_before_dataset_access(self):
        with patch('modeling.release.verify_release',side_effect=ValueError('bad lock')),patch('modeling.release.ModelingDataset') as data:
            with self.assertRaises(ValueError):authorize_test('missing','wrong')
            data.assert_not_called()

    def test_mixed_rows_and_no_history(self):
        batch=self.dev.head(5).copy()
        batch.loc[batch.index[0],'rel_speed']=np.nan
        batch.loc[batch.index[1],'balls']=4
        batch.loc[batch.index[2],'auto_pitch_type']='unseen'
        batch.loc[batch.index[3],'pitcher_anon_id']='unseen'
        result=self.predictor.predict(batch)
        self.assertEqual(len(result),5)
        self.assertTrue(result.loc[:1,'score'].isna().all())
        self.assertIn('unknown_category',result.loc[2,'warnings'])
        self.assertIn('no_history',result.loc[3,'warnings'])

    def test_duplicate_ids_and_missing_columns(self):
        batch=self.dev.head(2).copy();batch['pitch_uid']='same'
        result=self.predictor.predict(batch)
        self.assertEqual(result.pitch_uid.tolist(),['same','same'])
        self.assertTrue(self.predictor.predict(batch.drop(columns='rel_speed')).status.eq('invalid_input').all())

    def test_outcomes_and_environment_not_used(self):
        batch=self.dev.head(4).copy()
        before=self.predictor.predict(batch)
        batch['y_event']='invented';batch['altitude_category']='unknown'
        after=self.predictor.predict(batch)
        np.testing.assert_array_equal(before.score,after.score)

    def test_empty_and_unsupported_family(self):
        self.assertTrue(self.predictor.predict([]).empty)
        out=self.predictor.predict(self.dev.head(2),'arsenal')
        self.assertTrue(out.status.eq('unsupported_model').all())
        self.assertTrue(out.score.isna().all())

    def test_json_api_nulls_and_protocol(self):
        result=request(self.predictor,dict(family='pitching',records=[{}]))
        self.assertIsNone(result['records'][0]['pitching_plus'])
        self.assertTrue(all(v is None for v in result['records'][0]['probabilities'].values()))
        json.dumps(result,allow_nan=False)
        with self.assertRaises(ValueError):request(self.predictor,{'records':'wrong'})
