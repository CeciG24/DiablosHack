"""External run-weight adapter. Does not alter or refit frozen event models."""
import hashlib
import json
import math
from pathlib import Path

EVENTS = ('ball', 'called_strike', 'whiff', 'foul', 'in_play', 'hit_by_pitch')
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / 'config/xrv_mlb2014.json'


class ExternalRunValue:
    def __init__(self, path=DEFAULT_CONFIG, baseline=None):
        raw = Path(path).read_bytes()
        self.config = json.loads(raw)
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.baseline = baseline
        c = self.config
        if set(c['count_woba']) != {f'{b}-{s}' for b in range(4) for s in range(3)}:
            raise ValueError('All twelve count expectations are required')
        values = [c['woba_scale'], *c['count_woba'].values(),
                  *c['terminal_woba'].values(), *c['hit_woba'].values()]
        if not all(math.isfinite(v) and v >= 0 for v in values) or c['woba_scale'] <= 0:
            raise ValueError('Invalid external weights')
        t, h = c['mlb_totals'], c['hit_woba']
        singles = t['hits'] - t['doubles'] - t['triples'] - t['homeRuns']
        # Include HR and sacrifice bunts in this model's broad in_play event.
        denominator = t['atBats'] - t['strikeOuts'] + t['sacFlies'] + t['sacBunts']
        if singles < 0 or denominator <= 0:
            raise ValueError('Invalid external contact totals')
        self.contact_woba = (singles*h['single'] + t['doubles']*h['double']
                             + t['triples']*h['triple'] + t['homeRuns']*h['home_run']) / denominator

    def weights(self, balls, strikes):
        if type(balls) is not int or type(strikes) is not int or not 0 <= balls <= 3 or not 0 <= strikes <= 2:
            raise ValueError('A valid explicit balls/strikes count is required')
        c = self.config
        start = c['count_woba'][f'{balls}-{strikes}']
        strike = c['count_woba'][f'{balls}-{strikes+1}'] if strikes < 2 else c['terminal_woba']['strikeout']
        ball = c['count_woba'][f'{balls+1}-{strikes}'] if balls < 3 else c['terminal_woba']['walk']
        after = dict(ball=ball, called_strike=strike, whiff=strike,
                     foul=start if strikes == 2 else strike, in_play=self.contact_woba,
                     hit_by_pitch=c['terminal_woba']['hit_by_pitch'])
        return {e: (v-start)/c['woba_scale'] for e, v in after.items()}

    def metadata(self):
        return dict(self.config, weights_sha256=self.sha256,
                    contact_mean_woba=self.contact_woba, experimental=True,
                    formula='sum(P(event | inputs) * (terminal_or_next_count_wOBA - count_wOBA) / wOBA_scale)',
                    baseline='B1 frozen 2024 count-only event probabilities' if self.baseline else None)

    def evaluate(self, probabilities, record, prediction_status='ok'):
        result = dict(version=self.config['version'], weights_sha256=self.sha256,
                      status='unavailable', runs_per_pitch=None, runs_per_100=None,
                      baseline_runs_per_pitch=None, delta_vs_count_baseline=None,
                      lower_is_better_for_pitcher=True, experimental=True,
                      in_play_policy=self.config['in_play_policy'])
        try:
            weights = self.weights(record.get('balls'), record.get('strikes'))
        except ValueError:
            return result | {'status': 'missing_or_invalid_count'}
        if prediction_status != 'ok':
            return result | {'status': 'event_prediction_unavailable'}
        p = [probabilities.get(e) for e in EVENTS]
        if (any(isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) or not 0 <= v <= 1 for v in p)
                or abs(sum(p)-1) > 1e-6):
            return result | {'status': 'invalid_event_probabilities'}
        contributions = {e: p[i]*weights[e] for i, e in enumerate(EVENTS)}
        value = sum(contributions.values())
        result.update(status='ok', runs_per_pitch=value, runs_per_100=100*value,
                      event_weights=weights, contributions=contributions)
        if self.baseline is not None:
            import pandas as pd
            bp, routes = self.baseline.predict(pd.DataFrame([record]))
            baseline = sum(float(bp[0, i])*weights[e] for i, e in enumerate(EVENTS))
            result.update(baseline_runs_per_pitch=baseline, delta_vs_count_baseline=value-baseline,
                          baseline_route=str(routes[0]))
        return result
