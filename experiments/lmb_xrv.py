"""Reproducible LMB run-weight estimation from official regular-season feeds.

Raw feeds remain outside Git. Only 2024 is eligible for weight fitting.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import time
from urllib.request import urlopen

API = 'https://statsapi.mlb.com'
EVENTS = ('ball', 'called_strike', 'whiff', 'foul', 'in_play', 'hit_by_pitch')
CONTACT_RESULTS = {'single','double','triple','home_run','field_out','force_out',
                   'grounded_into_double_play','field_error','sac_fly','sac_bunt','double_play',
                   'fielders_choice','fielders_choice_out','sac_fly_double_play',
                   'sac_bunt_double_play','triple_play'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def request(path):
    for attempt in range(4):
        try:
            with urlopen(API+path, timeout=45) as response:
                return response.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1+attempt)


def download(year, root, workers=4):
    if year not in (2024, 2025):
        raise ValueError('Only 2024 fitting and 2025 validation are authorized')
    root = Path(root)/str(year)
    root.mkdir(parents=True, exist_ok=True)
    schedule_path = root/'schedule.json'
    url = f'/api/v1/schedule?sportId=23&leagueId=125&startDate={year}-01-01&endDate={year}-12-31&gameType=R'
    if not schedule_path.exists():
        schedule_path.write_bytes(request(url))
    raw_schedule = schedule_path.read_bytes()
    scheduled = {g['gamePk']: g for d in json.loads(raw_schedule)['dates'] for g in d['games']}
    games = [g for _, g in sorted(scheduled.items())
             if g['status']['detailedState'] in ('Final', 'Completed Early') and g['gameType'] == 'R']
    print(f'{year}: {len(games)} final games / {len(scheduled)} scheduled IDs', flush=True)

    def fetch(game):
        pk = game['gamePk']
        path = root/f'{pk}.json.gz'
        if path.exists():
            raw = gzip.decompress(path.read_bytes())
        else:
            raw = request(f'/api/v1.1/game/{pk}/feed/live')
            parsed = json.loads(raw)
            if parsed.get('gamePk') != pk:
                raise ValueError('Feed identity mismatch')
            temporary = path.with_suffix('.building')
            temporary.write_bytes(gzip.compress(raw, mtime=0))
            temporary.replace(path)
        return dict(game_pk=pk, source=API+f'/api/v1.1/game/{pk}/feed/live', sha256=digest(raw), bytes=len(raw))

    files, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, g): g for g in games}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                files.append(future.result())
            except Exception as error:
                errors.append(dict(game_pk=futures[future]['gamePk'], reason=str(error)))
            if i % 50 == 0 or i == len(games):
                print(f'{year}: downloaded {i}/{len(games)}; errors={len(errors)}', flush=True)
    manifest = dict(year=year, league='LMB', league_id=125, sport_id=23, game_type='R',
                    retrieved_at=datetime.now(timezone.utc).isoformat(), source=API+url,
                    schedule_sha256=digest(raw_schedule), scheduled_games=len(scheduled), final_games=len(games),
                    statuses=dict(Counter(g['status']['detailedState'] for g in scheduled.values())),
                    files=sorted(files, key=lambda f:f['game_pk']), errors=errors)
    write_json(root/'download_manifest.json', manifest)
    return manifest


def event_class(pitch):
    details = pitch.get('details', {})
    code = details.get('call', {}).get('code', details.get('code'))
    if details.get('isInPlay'):
        return 'in_play'
    return {'B': 'ball', '*B': 'ball', 'P': 'ball', 'V': 'ball', 'I': 'ball',
            'C': 'called_strike', 'S': 'whiff', 'W': 'whiff', 'T': 'whiff',
            'F': 'foul', 'R': 'foul', 'H': 'hit_by_pitch'}.get(code)


def base_mask(matchup):
    return sum(1 << i for i, name in enumerate(('postOnFirst', 'postOnSecond', 'postOnThird'))
               if matchup.get(name))


def clean_counts(play):
    """One observation per reached count per PA; no double-counted two-strike fouls."""
    pitches = [e for e in play.get('playEvents', []) if e.get('isPitch')]
    if not pitches:
        raise ValueError('no_pitches')
    last_index = pitches[-1]['index']
    # Do not attribute steals, pickoffs, wild pitches etc. to the terminal event.
    for runner in play.get('runners', []):
        m, d = runner.get('movement', {}), runner.get('details', {})
        changed = m.get('start') != m.get('end') or m.get('isOut') or d.get('isScoringEvent')
        if changed and d.get('playIndex') != last_index:
            raise ValueError('runner_action_before_terminal_pitch')
    b, s, counts = 0, 0, set()
    for e in play.get('playEvents', []):
        ec = e.get('count', {})
        if not e.get('isPitch'):
            # Automatic balls/strikes are not observations of this physical pitch model.
            if (ec.get('balls', b), ec.get('strikes', s)) != (b, s):
                raise ValueError('nonpitch_count_change')
            continue
        if not 0 <= b <= 3 or not 0 <= s <= 2:
            raise ValueError('invalid_pre_count')
        counts.add(f'{b}-{s}')
        category = event_class(e)
        if category is None:
            raise ValueError('unmapped_pitch_call')
        nb, ns = ec.get('balls'), ec.get('strikes')
        if category == 'ball':
            expected = (b+1, s)
        elif category in ('called_strike', 'whiff'):
            expected = (b, s+1)
        elif category == 'foul':
            expected = (b, min(s+1, 2))
        else:
            expected = (b, s)
        # Official feeds often increment the ball counter on HBP. This is
        # administrative; retain the true pre-count and the separate HBP class.
        hbp_counter = category == 'hit_by_pitch' and e['index'] == last_index and (nb,ns) in ((b,s),(b+1,s))
        if (nb, ns) != expected and not hbp_counter:
            raise ValueError('inconsistent_count_transition')
        before = f'{b}-{s}'
        b, s = nb, ns
    terminal = play.get('result', {}).get('eventType')
    category = event_class(pitches[-1])
    if terminal == 'walk' and not (category == 'ball' and b == 4):
        raise ValueError('inconsistent_terminal_walk')
    if terminal == 'strikeout' and not (category in ('whiff', 'called_strike') and s == 3):
        raise ValueError('inconsistent_terminal_strikeout')
    if terminal == 'hit_by_pitch' and category != 'hit_by_pitch':
        raise ValueError('inconsistent_terminal_hbp')
    if not (terminal in ('walk', 'strikeout', 'hit_by_pitch') or
            (category == 'in_play' and terminal in CONTACT_RESULTS)):
        raise ValueError('unsupported_terminal_event')
    return sorted(counts), before, category, len(pitches)


def extract_game(feed, year):
    """Reconstruct PA states; only complete, score-reconciled regulation half innings."""
    gd, live = feed['gameData'], feed['liveData']
    if gd['game']['type'] != 'R' or int(gd['game']['season']) != year:
        raise ValueError('wrong_season_or_game_type')
    if any(gd['teams'][side]['league']['id'] != 125 for side in ('home', 'away')):
        raise ValueError('wrong_league')
    plays = live.get('plays', {}).get('allPlays', [])
    if not plays:
        raise ValueError('empty_feed')
    halves = defaultdict(list)
    previous_index = -1
    score = {'home': 0, 'away': 0}
    key, outs, bases = None, 0, 0
    reasons = Counter()
    for p in plays:
        about, result = p['about'], p['result']
        index = about['atBatIndex']
        if index != previous_index+1 or not about.get('isComplete'):
            raise ValueError('incomplete_or_nonsequential_plays')
        previous_index = index
        current = (about['inning'], bool(about['isTopInning']))
        if current != key:
            key, outs, bases = current, 0, 0
        side = 'away' if current[1] else 'home'
        before_score = score[side]
        after_score = {'home': result['homeScore'], 'away': result['awayScore']}
        if any(after_score[k] < score[k] for k in score) or after_score['home' if side == 'away' else 'away'] != score['home' if side == 'away' else 'away']:
            raise ValueError('inconsistent_score_progression')
        after_outs = p['count']['outs']
        if not 0 <= outs <= after_outs <= 3:
            raise ValueError('inconsistent_out_progression')
        after_bases = base_mask(p.get('matchup', {})) if after_outs < 3 else 0
        row = dict(game_pk=feed['gamePk'], year=year, inning=current[0], top=current[1],
                   state=f'{outs}-{bases}', after_state=f'{after_outs}-{after_bases}',
                   outs=outs, after_outs=after_outs, runs=after_score[side]-before_score,
                   score_before=before_score, score_after=after_score[side],
                   terminal=result['eventType'], clean=False)
        try:
            counts, last, category, n = clean_counts(p)
            row.update(clean=True, counts=counts, terminal_count=last,
                       category=category, pitches=n)
        except ValueError as e:
            reasons[str(e)] += 1
        halves[key].append(row)
        score, outs, bases = after_score, after_outs, after_bases
    if any(score[side] != live['linescore']['teams'][side]['runs'] for side in score):
        raise ValueError('final_score_mismatch')
    inning_runs = {(i['num'], top): i['away' if top else 'home'].get('runs')
                   for i in live['linescore']['innings'] for top in (True, False)}
    rows = []
    for key, half in halves.items():
        if key[0] > 9:
            reasons['extra_inning_excluded'] += len(half)
            continue
        if half[-1]['after_outs'] != 3:
            reasons['incomplete_half_inning_excluded'] += len(half)
            continue
        if half[-1]['score_after']-half[0]['score_before'] != inning_runs.get(key):
            reasons['inning_score_mismatch'] += len(half)
            continue
        for row in half:
            row['remaining_runs'] = half[-1]['score_after']-row['score_before']
            rows.append(row)
    return rows, reasons


def load_season(root, year):
    folder = Path(root)/str(year)
    manifest_raw = (folder/'download_manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest.get('year') != year or manifest.get('league_id') != 125 or manifest.get('game_type') != 'R':
        raise ValueError('Download manifest season/league mismatch')
    if manifest['errors']:
        raise ValueError('Download incomplete; rerun download before fitting')
    rows, failures, exclusions = [], [], Counter()
    observed_pa, observed_pitches = 0, 0
    for item in manifest['files']:
        raw = gzip.decompress((folder/f"{item['game_pk']}.json.gz").read_bytes())
        if digest(raw) != item['sha256']:
            raise ValueError('Cached source hash mismatch')
        feed = json.loads(raw)
        source_plays = feed.get('liveData', {}).get('plays', {}).get('allPlays', [])
        observed_pa += len(source_plays)
        observed_pitches += sum(bool(e.get('isPitch')) for p in source_plays for e in p.get('playEvents', []))
        try:
            extracted, reasons = extract_game(feed, year)
            rows.extend(extracted)
            exclusions.update(reasons)
        except (ValueError, KeyError, TypeError) as e:
            failures.append(dict(game_pk=item['game_pk'], reason=str(e)))
    audit = dict(year=year, downloaded_games=len(manifest['files']),
                 source=manifest['source'], observed_pa=observed_pa, observed_pitches=observed_pitches,
                 accepted_games=len({r['game_pk'] for r in rows}), pa_rows=len(rows),
                 clean_pa_rows=sum(r['clean'] for r in rows),
                 pitch_rows=sum(r.get('pitches', 0) for r in rows if r['clean']),
                 excluded_games=failures, exclusions=dict(exclusions),
                 download_manifest_sha256=digest(manifest_raw), schedule_sha256=manifest['schedule_sha256'])
    return rows, audit


def fit_weights(rows, year=2024):
    if year != 2024:
        raise ValueError('Weights must be fitted exclusively on 2024')
    if any(r.get('year') != 2024 for r in rows):
        raise ValueError('Every fitting row must belong to 2024')
    states = defaultdict(list)
    for r in rows:
        states[r['state']].append(r['remaining_runs'])
    if set(states) != {f'{o}-{b}' for o in range(3) for b in range(8)}:
        raise ValueError('All 24 base-out states are required')
    if min(map(len, states.values())) < 30:
        raise ValueError('Insufficient support for run expectancy')
    re24 = {k: sum(v)/len(v) for k,v in sorted(states.items())}

    def value(r):
        after = 0 if r['after_outs'] == 3 else re24[r['after_state']]
        return r['runs']+after-re24[r['state']]

    clean = [r for r in rows if r['clean']]
    by_terminal = defaultdict(list)
    for r in clean:
        by_terminal[r['terminal']].append(value(r))
    # Global terminal-event values marginalize base/out context before count modeling.
    terminal_values = {k:sum(v)/len(v) for k,v in sorted(by_terminal.items())}
    reached, terminal_counts = defaultdict(list), defaultdict(list)
    for r in clean:
        rv = terminal_values[r['terminal']]
        for c in r['counts']:
            reached[c].append(rv)
        terminal_counts[(r['terminal_count'], r['category'])].append(rv)
    all_counts = {f'{b}-{s}' for b in range(4) for s in range(3)}
    if set(reached) != all_counts or min(map(len, reached.values())) < 100:
        raise ValueError('Insufficient support for count expectations')
    expectation = {k:sum(v)/len(v) for k,v in sorted(reached.items())}
    # Pool sparse HBP/contact terminal counts toward their own 2024 class mean.
    class_values = defaultdict(list)
    for r in clean:
        if r['terminal'] in ('walk','strikeout','hit_by_pitch') or r['category'] == 'in_play':
            cls = 'strikeout' if r['terminal'] == 'strikeout' else r['category']
            class_values[cls].append(terminal_values[r['terminal']])
    means = {k:sum(v)/len(v) for k,v in class_values.items()}
    terminal, supports = {}, {}
    for count in sorted(all_counts):
        terminal[count], supports[count] = {}, {}
        for cls in ('ball','strikeout','hit_by_pitch','in_play'):
            if cls == 'strikeout':
                values = terminal_counts.get((count,'called_strike'), []) + terminal_counts.get((count,'whiff'), [])
            else:
                values = terminal_counts.get((count,cls), [])
            supports[count][cls] = len(values)
            terminal[count][cls] = (sum(values)+30*means[cls])/(len(values)+30)
    weights = {}
    for b in range(4):
        for s in range(3):
            c = f'{b}-{s}'
            start = expectation[c]
            strike = expectation[f'{b}-{s+1}'] if s < 2 else terminal[c]['strikeout']
            ball = expectation[f'{b+1}-{s}'] if b < 3 else terminal[c]['ball']
            weights[c] = dict(ball=ball-start, called_strike=strike-start, whiff=strike-start,
                              foul=0.0 if s == 2 else strike-start,
                              in_play=terminal[c]['in_play']-start,
                              hit_by_pitch=terminal[c]['hit_by_pitch']-start)
    return dict(schema_version=2, version='xrv_external_lmb2024_v1', league='LMB', season=2024,
                method='count_transitions_of_LMB_RE24_terminal_event_values',
                label='LMB 2024', units='runs_per_pitch',
                perspective='offense_lower_is_better_for_pitcher',
                in_play_policy='LMB_2024_terminal_contact_mix_by_count_shrunk_30_PA',
                sources={'schedule':API+'/api/v1/schedule?sportId=23&leagueId=125&season=2024&gameType=R',
                         'feeds':API+'/api/v1.1/game/{gamePk}/feed/live',
                         'method_reference':'https://library.fangraphs.com/misc/re24/'},
                re24=re24, re24_support={k:len(v) for k,v in sorted(states.items())},
                terminal_event_run_values=terminal_values,
                terminal_event_support={k:len(v) for k,v in sorted(by_terminal.items())},
                count_run_expectation=expectation,
                count_support={k:len(v) for k,v in sorted(reached.items())},
                terminal_count_support=supports, event_weights_by_count=weights,
                limitations=['Approximate context-marginalized event valuation; not an individualized RE24 prediction.',
                             'Only complete regulation half innings; extras and walk-off half innings excluded.',
                             'Runner actions before terminal pitch and nonpitch count changes excluded from weight fitting.',
                             'Contact mix varies by count but not by EV/launch angle or individual pitch shape.',
                             'No park or altitude-specific weights; no anonymous-to-public player mapping.',
                             '2025 is reserved for transfer diagnostics; no 2026 used.'])


def build(root, output, validation_year=None):
    rows, audit = load_season(root, 2024)
    config = fit_weights(rows)
    if audit['accepted_games']/audit['downloaded_games'] < .9:
        raise ValueError('Less than 90% of downloaded games passed reconstruction')
    config['provenance'] = audit
    config['sources']['schedule'] = audit['source']
    config['frozen_on'] = '2026-10-21'
    config['builder_sha256'] = digest(Path(__file__).read_bytes())
    diagnostics = dict(fit=audit, validation=None, represents_pitch_model_validation=False)
    if validation_year is not None:
        import math
        other, other_audit = load_season(root, validation_year)
        # Frozen 2024 RE, evaluated on future remaining runs. Not xRV model RMSE.
        errors = [(config['re24'][r['state']]-r['remaining_runs'])**2 for r in other]
        counts = Counter(c for r in other if r['clean'] for c in r['counts'])
        clean_other = [r for r in other if r['clean'] and r['terminal'] in config['terminal_event_run_values']]
        count_squared_error, global_squared_error, count_n = 0., 0., 0
        for r in clean_other:
            target = config['terminal_event_run_values'][r['terminal']]
            for count in r['counts']:
                count_squared_error += (config['count_run_expectation'][count]-target)**2
                global_squared_error += (config['count_run_expectation']['0-0']-target)**2
                count_n += 1
        diagnostics['validation'] = dict(other_audit, re24_remaining_runs_rmse=math.sqrt(sum(errors)/len(errors)),
                                         reached_count_support=dict(sorted(counts.items())),
                                         terminal_value_projection=dict(n_reached_counts=count_n,
                                             count_rmse=math.sqrt(count_squared_error/count_n),
                                             constant_zero_zero_reference_rmse=math.sqrt(global_squared_error/count_n),
                                             target='2025 terminal event mapped through frozen 2024 terminal-event run weights'),
                                         scope='2025 source/reconstruction and frozen RE24 transfer only; not F8/F11 xRV accuracy')
    write_json(output, config)
    write_json(Path(output).with_name('xrv_lmb2024_validation.json'), diagnostics)
    print(json.dumps({'config':str(output), 'fit':audit, 'validation':diagnostics['validation']}, ensure_ascii=False), flush=True)
    return config, diagnostics


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('command', choices=['download','build'])
    parser.add_argument('--year', type=int, default=2024, choices=[2024, 2025])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4, choices=range(1, 9))
    parser.add_argument('--output', type=Path, default=Path('config/xrv_lmb2024.json'))
    parser.add_argument('--validation-year', type=int, choices=[2025])
    args = parser.parse_args()
    if args.command == 'download':
        download(args.year, args.root, args.workers)
    else:
        build(args.root, args.output, args.validation_year)


if __name__ == '__main__':
    main()
