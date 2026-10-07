import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_data import pd, np, prepare_frame, make_splits, make_arsenal, json, CONFIG

CFG=json.loads(CONFIG.read_text(encoding='utf-8'))


def fixture():
    row={'year':2024,'PitchUID':'id','game_anon_id':'g','pitcher_anon_id':'p','batter_anon_id':'b',
         'PitcherThrows':'Right','BatterSide':'Left','altitude_category':'No Altitude','AutoPitchType':'Four-Seam',
         'RelSpeed':92.,'EffectiveVelo':'91.5','SpinRate':2200.,'SpinAxis':210.,'RelHeight':6.,'RelSide':2.,
         'Extension':6.,'InducedVertBreak':15.,'HorzBreak':8.,'ExitSpeed':np.nan,'Angle':np.nan,
         'Balls':0.,'Strikes':0.,'Outs':0.,'PlateLocHeight':2.5,'PlateLocSide':.2,
         'PitchCall':'StrikeSwinging','play_result':'StrikeSwinging','is_contact':0.,'is_ball_in_play':0.,
         'is_hit_by_pitch':0.,'outside_strike_zone':0.,'hit_type':None}
    return pd.DataFrame([row])


class PreparationTests(unittest.TestCase):
    def test_strong_conflict_is_null_not_a_negative(self):
        r=fixture(); r['is_contact']=1.
        c,f,t,q,i=prepare_frame(r,CFG)
        self.assertTrue(pd.isna(t.loc[0,'y_event']))
        self.assertTrue(pd.isna(t.loc[0,'y_whiff']))
        self.assertFalse(q.loc[0,'eligible_event'])

    def test_hbp_systematic_flag_rebuilt_when_consistent(self):
        r=fixture(); r['PitchCall']='HitByPitch'; r['play_result']='HitByPitch'
        c,f,t,q,i=prepare_frame(r,CFG)
        self.assertEqual(t.loc[0,'y_hit_by_pitch'],1)
        self.assertEqual(c.loc[0,'is_hit_by_pitch'],0)
        self.assertTrue(q.loc[0,'hbp_source_flag_conflict'])

    def test_no_contact_is_not_weak_contact(self):
        c,f,t,q,i=prepare_frame(fixture(),CFG)
        self.assertTrue(pd.isna(t.loc[0,'y_weak_contact_proxy_bip']))
        self.assertEqual(t.loc[0,'y_whiff_given_swing'],1)
        self.assertTrue(pd.isna(t.loc[0,'y_chase_given_outside']))

    def test_physical_mask_preserves_source(self):
        raw=fixture(); raw['Extension']=-2.
        c,f,t,q,i=prepare_frame(raw,CFG)
        self.assertEqual(raw.loc[0,'Extension'],-2.)
        self.assertTrue(pd.isna(c.loc[0,'extension']))
        self.assertFalse(q.loc[0,'eligible_stuff_default'])

    def test_unknown_event_not_labeled_ball(self):
        raw=fixture(); raw['PitchCall']='Undefined'; raw['play_result']='NeutralPlay'
        c,f,t,q,i=prepare_frame(raw,CFG)
        self.assertTrue(pd.isna(t.loc[0,'y_event']))
        self.assertTrue(pd.isna(t.loc[0,'y_swing']))

    def test_split_assignment_independent_of_row_order(self):
        raw=pd.concat([fixture()]*5,ignore_index=True)
        raw['PitchUID']=['a','b','c','d','e']; raw['pitcher_anon_id']=['x','x','z','y',None]
        clean,*_=prepare_frame(raw,CFG)
        a=make_splits(clean,CFG).set_index('pitch_uid').sort_index()
        b=make_splits(clean.sample(frac=1,random_state=9),CFG).set_index('pitch_uid').sort_index()
        pd.testing.assert_frame_equal(a,b)
        self.assertEqual(a.loc['a','pitcher_split'],a.loc['b','pitcher_split'])
        self.assertEqual(a.loc['e','pitcher_split'],'excluded_missing_pitcher')

    def test_future_pitch_does_not_change_past_arsenal(self):
        raw=pd.concat([fixture()]*32,ignore_index=True)
        raw['PitchUID']=[str(i) for i in range(32)]
        raw.loc[30,'year']=2025; raw.loc[31,'year']=2026
        clean,*_=prepare_frame(raw,CFG)
        a,_=make_arsenal(clean,CFG)
        clean.loc[31,'rel_speed']=105.
        b,_=make_arsenal(clean,CFG)
        pd.testing.assert_frame_equal(a.loc[a.pitch_uid.ne('31')].reset_index(drop=True),b.loc[b.pitch_uid.ne('31')].reset_index(drop=True))
        self.assertFalse(a.loc[a.pitch_uid.eq('0'),'has_prior_fastball_reference'].iloc[0])
        self.assertEqual(a.loc[a.pitch_uid.eq('30'),'source_max_year'].iloc[0],2024)


if __name__=='__main__': unittest.main()
