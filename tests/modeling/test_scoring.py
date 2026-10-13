import unittest
import numpy as np
import pandas as pd
from modeling.scoring import FixedScale, S0, S1, PROBS, utility, aggregate


def reference():
    p = np.array([[.3,.2,.1,.2,.19,.01],[.2,.1,.3,.2,.19,.01],[.1,.3,.2,.2,.19,.01]])
    frame = pd.DataFrame(p,columns=PROBS)
    frame['pitch_uid'] = ['a','b','c']
    frame['family'],frame['year'],frame['partition'] = 'pitching',2025,'calibration'
    frame['pitcher_anon_id'] = 'p1'
    return frame


class ScoringTests(unittest.TestCase):
    def test_reference_and_formula(self):
        r = reference()
        scale = FixedScale.fit(r,'pitching',S0,'v1')
        out = scale.score(r)
        np.testing.assert_allclose(out.utility,[.14,.29,.44],atol=1e-14)
        self.assertAlmostEqual(out.score.mean(),100)
        self.assertAlmostEqual(out.score.std(ddof=0),10)
        self.assertTrue((np.diff(out.score)>0).all())

    def test_batch_order_and_missing(self):
        r = reference();scale = FixedScale.fit(r,'pitching',S0,'v1')
        self.assertEqual(scale.score(r).score.iloc[1],scale.score(r.iloc[[1]]).score.iloc[0])
        r.loc[0,'p_ball'] = np.nan
        r.loc[2,'p_ball'] = 2
        out = scale.score(r)
        self.assertTrue(out.score.iloc[[0,2]].isna().all())
        self.assertTrue(out.score_status.iloc[[0,2]].ne('ok').all())

    def test_reference_guards(self):
        for column,value in [('year',2026),('partition','development'),('family','stuff')]:
            r = reference();r[column] = value
            with self.assertRaises(ValueError):FixedScale.fit(r,'pitching',S0,'v1')
        r = reference();r[PROBS] = r[PROBS].iloc[0].to_numpy()
        with self.assertRaises(ValueError):FixedScale.fit(r,'pitching',S0,'v1')
        with self.assertRaises(ValueError):FixedScale.fit(pd.concat([reference(),reference()]),'pitching',S0,'v1')

    def test_contact_never_imputed(self):
        r = reference()
        self.assertTrue(np.isnan(utility(r,S1)[0]).all())
        r['p_weak_given_in_play'],r['p_medium_given_in_play'],r['p_hard_given_in_play'] = .2,.5,.3
        r['contact_status'],r['contact_route'] = 'validated','model'
        np.testing.assert_allclose(utility(r,S1)[0],utility(r,S0)[0]-.038)
        r['contact_route'] = 'smoothed_training_prevalence'
        self.assertTrue(np.isnan(utility(r,S1)[0]).all())

    def test_aggregate_denominator_and_null(self):
        r = reference();scale=FixedScale.fit(r,'pitching',S0,'v1')
        r.loc[0,'p_ball']=np.nan
        out=scale.score(r);a=aggregate(out,['pitcher_anon_id']).iloc[0]
        self.assertEqual(a.n_total,3);self.assertEqual(a.n_valid,2)
        self.assertAlmostEqual(a.coverage,2/3);self.assertEqual(a.score,out.score.mean())
        out['score']=np.nan;out['score_status']='missing'
        a=aggregate(out,['pitcher_anon_id']).iloc[0]
        self.assertTrue(pd.isna(a.score));self.assertEqual(a.score_status,'no_valid_predictions')

    def test_cross_family_rejected(self):
        r=reference();scale=FixedScale.fit(r,'pitching',S0,'v1');r['family']='stuff'
        with self.assertRaises(ValueError):scale.score(r)

    def test_nonfinite_and_wrong_sum(self):
        r=reference();r.loc[0,'p_ball']=np.inf;r.loc[1,'p_ball']=.6
        value,reason=utility(r)
        self.assertTrue(np.isnan(value[:2]).all());self.assertTrue((reason[:2]!='ok').all())
