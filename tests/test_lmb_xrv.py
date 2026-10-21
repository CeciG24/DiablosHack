"""Counterexamples for count deduplication and official-feed reconstruction."""
import unittest
from experiments.lmb_xrv import clean_counts, event_class, extract_game, fit_weights


def pitch(index, code, balls, strikes, outs=0):
    return dict(index=index, isPitch=True, count=dict(balls=balls, strikes=strikes, outs=outs),
                details=dict(call={'code':code}, isInPlay=code == 'X'))


def strikeout(index, outs):
    return dict(about=dict(atBatIndex=index, inning=1, isTopInning=True, isComplete=True),
                result=dict(eventType='strikeout', homeScore=0, awayScore=0),
                count=dict(balls=0, strikes=3, outs=outs), matchup={}, runners=[],
                playEvents=[pitch(0,'C',0,1), pitch(1,'S',0,2), pitch(2,'S',0,3,outs)])


def feed():
    return dict(gamePk=123, gameData=dict(game=dict(type='R',season='2024'),
                teams={s:{'league':{'id':125}} for s in ('home','away')}),
                liveData=dict(plays={'allPlays':[strikeout(i,i+1) for i in range(3)]},
                linescore=dict(teams={s:{'runs':0} for s in ('home','away')},
                               innings=[dict(num=1,home={'runs':0},away={'runs':0})])))


class LmbExtractionTests(unittest.TestCase):
    def test_count_is_before_pitch_and_fouls_are_deduplicated(self):
        p = strikeout(0,1)
        p['playEvents'] = [pitch(0,'C',0,1), pitch(1,'F',0,2), pitch(2,'F',0,2),
                           pitch(3,'F',0,2), pitch(4,'S',0,3,1)]
        counts, terminal, category, n = clean_counts(p)
        self.assertEqual(counts, ['0-0','0-1','0-2'])
        self.assertEqual((terminal,category,n), ('0-2','whiff',5))

    def test_wild_pitch_or_steal_before_terminal_pitch_is_excluded(self):
        p = strikeout(0,1)
        p['runners'] = [dict(movement=dict(start='1B',end='2B'),details={'playIndex':1})]
        with self.assertRaisesRegex(ValueError, 'runner_action'):
            clean_counts(p)

    def test_hbp_counter_increment_is_not_a_ball_outcome_or_next_precount(self):
        p = strikeout(0,0)
        p['result']['eventType'] = 'hit_by_pitch'
        p['playEvents'] = [pitch(0,'H',1,0)]
        self.assertEqual(clean_counts(p), (['0-0'],'0-0','hit_by_pitch',1))
        p['playEvents'] = [pitch(0,'H',0,0)]
        self.assertEqual(clean_counts(p), (['0-0'],'0-0','hit_by_pitch',1))

    def test_nonpitch_automatic_ball_cannot_be_a_physical_pitch(self):
        p = strikeout(0,1)
        p['playEvents'].insert(0, dict(isPitch=False,count=dict(balls=1,strikes=0)))
        with self.assertRaisesRegex(ValueError, 'nonpitch_count'):
            clean_counts(p)

    def test_unknown_calls_and_bad_count_transitions_are_rejected(self):
        self.assertIsNone(event_class(pitch(0,'Z',0,0)))
        p = strikeout(0,1)
        p['playEvents'][0]['count']['strikes'] = 2
        with self.assertRaisesRegex(ValueError, 'inconsistent_count'):
            clean_counts(p)

    def test_interference_cannot_be_assigned_contact_value(self):
        p = strikeout(0,0)
        p['result']['eventType'] = 'catcher_interf'
        p['playEvents'] = [pitch(0,'X',0,0)]
        with self.assertRaisesRegex(ValueError,'unsupported_terminal'):
            clean_counts(p)

    def test_completed_half_has_zero_remaining_runs_and_correct_outs(self):
        rows, reasons = extract_game(feed(),2024)
        self.assertEqual([r['state'] for r in rows], ['0-0','1-0','2-0'])
        self.assertEqual([r['after_outs'] for r in rows], [1,2,3])
        self.assertTrue(all(r['remaining_runs'] == 0 and r['clean'] for r in rows))
        self.assertEqual(dict(reasons), {})

    def test_walkoff_half_is_not_treated_as_zero_future_runs(self):
        f = feed()
        p = strikeout(3,0)
        p.update(count=dict(balls=0,strikes=0,outs=0), playEvents=[pitch(0,'X',0,0)],
                 result=dict(eventType='home_run', homeScore=1, awayScore=0))
        p['about']['isTopInning'] = False
        f['liveData']['plays']['allPlays'].append(p)
        f['liveData']['linescore']['teams']['home']['runs'] = 1
        f['liveData']['linescore']['innings'][0]['home']['runs'] = 1
        rows, reasons = extract_game(f,2024)
        self.assertEqual(len(rows),3)
        self.assertEqual(reasons['incomplete_half_inning_excluded'],1)

    def test_league_season_and_score_must_match(self):
        for kind in ('league','season','score'):
            f = feed()
            if kind == 'league': f['gameData']['teams']['home']['league']['id'] = 1
            if kind == 'season': f['gameData']['game']['season'] = '2025'
            if kind == 'score': f['liveData']['linescore']['teams']['home']['runs'] = 1
            with self.assertRaises(ValueError):
                extract_game(f,2024)

    def test_fit_refuses_future_year_and_inadequate_support(self):
        with self.assertRaisesRegex(ValueError,'exclusively on 2024'):
            fit_weights([],2025)
        with self.assertRaisesRegex(ValueError,'24 base-out'):
            fit_weights([])
        with self.assertRaisesRegex(ValueError,'Every fitting row'):
            fit_weights([{'year':2025}])


if __name__ == '__main__':
    unittest.main()
