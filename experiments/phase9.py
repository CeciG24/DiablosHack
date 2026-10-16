"""F9: matched ablations, temporal/pitcher validation and fixed-context scoring.

All data access is explicitly restricted to 2024/2025. This is exploratory
development after F8 test exposure, never an independent final evaluation.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import lightgbm as lgb
from modeling.datasets import ROOT, STUFF, META, ModelingDataset, duckdb, pd, ids_hash, sha256_file, require_unique
from modeling.models import TabularEventModel, BACKEND_VERSION
from modeling.arsenal import ARSENAL, ArsenalEventModel, build_reference, attach_reference
from modeling.phase5 import load_history
from modeling.baselines import CLASSES, EventBaseline
from modeling.calibration import TemperatureScaler
from modeling.metrics import multiclass_metrics, per_pitch_losses, calibration_bins, paired_bootstrap
from modeling.protocols import assign_pitcher_partitions
from modeling.release import verify_release

DERIVED = ['hand_hb', 'hand_release_side', 'movement_magnitude', 'spin_per_mph',
           'speed_x_ivb', 'extension_x_speed']
CONTEXT = ['auto_pitch_type', 'pitcher_throws', 'batter_side', 'balls', 'strikes']
FEATURES = {'physical': STUFF, 'engineered': STUFF + DERIVED, 'context': CONTEXT,
            'context_physics': STUFF + DERIVED + CONTEXT[2:],
            'arsenal': STUFF + DERIVED + CONTEXT[2:] + ARSENAL,
            'environment': STUFF + DERIVED + CONTEXT[2:] + ARSENAL + ['altitude_category']}
PROBS = ['p_' + c for c in CLASSES]
UTILITY = np.array([-.5, 1., 1., 0., 0., -1.])
RELEASE = ROOT/'artifacts/modeling/releases/f8-release-20261013'


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def engineer(rows):
    """Deterministic transforms; no learned statistics, outcomes or identities."""
    result = rows.copy()
    if not result.pitcher_throws.isin(['Left', 'Right']).all():
        raise ValueError('Unknown throwing hand; expected Left or Right')
    if not (np.isfinite(result.rel_speed).all() and result.rel_speed.gt(0).all()):
        raise ValueError('Positive finite speed required')
    sign = result.pitcher_throws.map({'Left': -1., 'Right': 1.})
    result['hand_hb'] = sign * result.horz_break
    result['hand_release_side'] = sign * result.rel_side
    result['movement_magnitude'] = np.hypot(result.horz_break, result.induced_vert_break)
    result['spin_per_mph'] = result.spin_rate / result.rel_speed
    result['speed_x_ivb'] = result.rel_speed * result.induced_vert_break
    result['extension_x_speed'] = result.extension * result.rel_speed
    return result


class ExperimentModel(TabularEventModel):
    def __init__(self, variant, protocol='A', seed=20260929, threads=4):
        if variant not in FEATURES or protocol not in ('A', 'B', 'C'):
            raise ValueError('Unknown F9 model')
        super().__init__(seed, threads, 'stuff', 'A' if protocol == 'C' else protocol)
        self.variant, self.protocol = variant, protocol
        self.features = FEATURES[variant].copy()
        self.categorical = [c for c in self.features if c in CONTEXT[:3]+['altitude_category']]
        self.numeric = [c for c in self.features if c not in self.categorical]

    def fit_experiment(self, train, dev, cfg, smoke=False):
        if self.protocol == 'C':
            # Reuse guarded fixed-round fitting; features are this experiment's allowlist.
            self.with_arsenal = self.variant in ('arsenal', 'environment')
            ArsenalEventModel.fit(self, train, cfg['parameters'], 20 if smoke else cfg['fixed_rounds_C'])
        else:
            super().fit(train, dev, cfg['parameters'], 20 if smoke else cfg['maximum_rounds'], cfg['patience'])
        self.metadata.update(f9_variant=self.variant, f9_version=cfg['version'], protocol_id=self.protocol)
        return self

    @classmethod
    def load(cls, folder):
        folder = Path(folder)
        m = json.loads((folder/'preprocessing.json').read_text(encoding='utf-8'))
        model = cls(m['f9_variant'], m['protocol_id'], m['seed'], m['threads'])
        if (m['features'] != model.features or m['classes'] != list(CLASSES)
                or m['backend_version'] != BACKEND_VERSION or m['schema_version'] != 1
                or m['model_sha256'] != sha256_file(folder/'model.txt')
                or set(m['vocabularies']) != set(model.categorical)):
            raise ValueError('Invalid F9 artifact')
        model.metadata, model.vocabularies = m, m['vocabularies']
        model.booster = lgb.Booster(model_file=str(folder/'model.txt'))
        if model.booster.feature_name() != model.features or model.booster.num_model_per_iteration() != 6:
            raise ValueError('Invalid native schema')
        return model


def context_distribution(train):
    require_unique(train)
    if train.empty or not train.year.eq(2024).all() or not train.partition.eq('train').all():
        raise PermissionError('Standardization weights require A training only')
    counts = train.groupby(['balls', 'strikes', 'batter_side']).size()
    return [dict(balls=int(b), strikes=int(s), batter_side=h, weight=float(n/len(train)))
            for (b, s, h), n in counts.items()]


def standardized_probabilities(model, scaler, rows, distribution):
    """Marginal association under the same training context mix for every pitch."""
    if not distribution or not np.isclose(sum(d['weight'] for d in distribution), 1):
        raise ValueError('Invalid context weights')
    p = np.zeros((len(rows), 6))
    for context in distribution:
        if not np.isfinite(context['weight']) or context['weight'] < 0:
            raise ValueError('Invalid context weight')
        changed = rows.assign(**{k: context[k] for k in ('balls', 'strikes', 'batter_side')})
        p += context['weight'] * scaler.transform(model.predict(changed))
    return p


def diagnostics(rows, p, name, folder):
    loss, _ = per_pitch_losses(rows.y_event, p, CLASSES)
    detail = rows[['pitch_uid', 'game_anon_id', 'y_event', 'auto_pitch_type', 'pitcher_throws', 'altitude_category']].copy()
    detail['loss'] = loss
    records = []
    for group in ('auto_pitch_type', 'pitcher_throws', 'altitude_category'):
        for value, frame in detail.groupby(group, dropna=False):
            records.append(dict(group=group, value=value, n=len(frame), games=frame.game_anon_id.nunique(),
                                log_loss=float(frame.loss.mean()), provisional=len(frame)<200))
    write(folder/(name+'_subgroups.json'), records)
    write(folder/(name+'_calibration.json'), calibration_bins(rows.y_event, p, CLASSES))
    classes = []
    for i, label in enumerate(CLASSES):
        y = rows.y_event.eq(label).to_numpy(dtype=float)
        classes.append(dict(label=label, n=len(y), positives=int(y.sum()),
                            mean_probability=float(p[:, i].mean()), frequency=float(y.mean()),
                            binary_brier=float(np.mean((p[:, i]-y)**2))))
    write(folder/(name+'_classes.json'), classes)
    return detail[['pitch_uid', 'game_anon_id', 'y_event', 'loss']]


def run(name, smoke=False):
    import re
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
        raise ValueError('Invalid experiment name')
    cfg = json.loads((ROOT/'config/phase9.json').read_text(encoding='utf-8'))
    folder = ROOT/'artifacts/modeling'/name/'F9'
    folder.mkdir(parents=True, exist_ok=False)
    write(folder/'config.json', cfg)  # Persist before any fitting.
    release_id = verify_release(RELEASE)['release_id']
    exposure = ROOT/'artifacts/modeling/test_exposure.json'
    exposure_before = sha256_file(exposure)
    dataset = ModelingDataset()
    data = dataset.load(maximum=20000 if smoke else None)
    rows = data['aligned']['pitching']
    with duckdb.connect(str(dataset.run/'diablos.duckdb'), read_only=True) as db:
        categories = db.execute('SELECT pitch_uid, altitude_category FROM model_base WHERE year IN (2024, 2025)').df()
    rows = engineer(rows.merge(categories, on='pitch_uid', validate='one_to_one'))
    if not rows.year.isin([2024, 2025]).all():
        raise PermissionError('F9 cannot access final test')
    rows.to_parquet(folder/'cohort.parquet', index=False)
    reference = build_reference(load_history(dataset))
    refdir = folder/'history_2024'
    refdir.mkdir()
    for ref, filename in zip(reference, ('fastballs', 'type_counts', 'pitcher_counts')):
        ref.to_parquet(refdir/(filename+'.parquet'), index=False)
    c_all = attach_reference(rows.loc[rows.year.eq(2025)], *reference)
    c_rows = c_all.loc[c_all.has_reference].copy()
    coverage = c_all.groupby('partition').has_reference.agg(['size', 'sum']).reset_index().to_dict('records')
    summary = dict(version=cfg['version'], smoke=smoke, post_test_exposure=True, new_test_access=False,
                   release_id=release_id, history_coverage=coverage, protocols={}, comparisons={}, checks={})
    models_A = {}
    for protocol, frame in [('A', rows), ('B', assign_pitcher_partitions(rows, dataset.config['F3']['protocol_B_validation_hash_seed'])), ('C', c_rows)]:
        dest = folder/protocol
        dest.mkdir()
        train = frame.loc[frame.partition.eq('development' if protocol=='C' else 'train')].copy()
        dev = frame.loc[frame.partition.eq('development')].copy()
        # B calibration uses only 2025 pitchers assigned validation, separate games from early stopping.
        cal = frame.loc[frame.partition.eq('calibration') & frame.year.eq(2025)].copy()
        review = frame.loc[frame.partition.eq('phase_review')].copy()
        if min(map(len, (train, dev, cal, review))) == 0:
            raise ValueError('Insufficient partition support')
        if protocol == 'B':
            if set(train.pitcher_anon_id) & (set(dev.pitcher_anon_id)|set(cal.pitcher_anon_id)|set(review.pitcher_anon_id)) or set(review.pitcher_anon_id)&(set(dev.pitcher_anon_id)|set(cal.pitcher_anon_id)):
                raise ValueError('Pitcher leakage')
        roles = {'train': train, 'development': dev, 'calibration': cal, 'review': review}
        summary['protocols'][protocol] = {'partitions': {k: dict(n=len(v), pitchers=v.pitcher_anon_id.nunique(), games=v.game_anon_id.nunique(), ids_sha256=ids_hash(v.pitch_uid.tolist())) for k,v in roles.items()}, 'metrics': {}}
        for role, part in roles.items():
            part[META].to_parquet(dest/(role+'_ids.parquet'), index=False)
        losses = {}
        predictions = review[META+['y_event']].copy()
        variants = cfg['variants_C' if protocol=='C' else 'variants_AB']
        for variant in variants:
            print(f'F9 {protocol}/{variant}: fit={len(train)}, cal={len(cal)}, review={len(review)}', flush=True)
            model = ExperimentModel(variant, protocol, cfg['seed'], cfg['threads']).fit_experiment(train, dev, cfg, smoke)
            md = dest/variant
            md.mkdir()
            model.save(md/'model')
            raw_cal, raw_review = model.predict(cal), model.predict(review)
            scaler = TemperatureScaler(CLASSES).fit(cal, raw_cal, 'y_event')
            scaler.save(md/'temperature.json')
            p = scaler.transform(raw_review)
            loaded = ExperimentModel.load(md/'model')
            summary['checks'][protocol+'_'+variant+'_reload'] = bool(np.array_equal(raw_review, loaded.predict(review)))
            summary['protocols'][protocol]['metrics'][variant] = dict(raw=multiclass_metrics(review.y_event, raw_review, CLASSES), calibrated=multiclass_metrics(review.y_event, p, CLASSES), temperature=scaler.temperature, rounds=model.metadata['best_iteration'])
            losses[variant] = diagnostics(review, p, variant, dest)
            for i, label in enumerate(CLASSES):
                predictions[variant+'_'+label] = p[:, i]
            if protocol=='A':
                models_A[variant] = (model, scaler)
        if protocol in ('A', 'B'):
            for name_b in ('B0', 'B1', 'B2'):
                baseline = EventBaseline(name_b).fit(train, protocol)
                baseline.save(dest/(name_b+'.json'))
                p, _ = baseline.predict(review)
                summary['protocols'][protocol]['metrics'][name_b] = dict(calibrated=multiclass_metrics(review.y_event, p, CLASSES))
                for i, label in enumerate(CLASSES):
                    predictions[name_b+'_'+label] = p[:, i]
        predictions.to_parquet(dest/'review_predictions.parquet', index=False)
        for reference_name, candidate in cfg['comparisons_C' if protocol=='C' else 'comparisons_AB']:
            comparison = paired_bootstrap(losses[reference_name], losses[candidate], 20 if smoke else cfg['bootstrap_repetitions'], cfg['seed'], confidence=1-cfg['familywise_alpha']/cfg['comparison_count'], minimum_relative_improvement=cfg['minimum_relative_improvement'], smoke=smoke)
            comparison.update(status='exploratory_post_test_exposure', production_promotion=False,
                              interval_note='Bonferroni nominal familywise 95%; not independent confirmation')
            summary['comparisons'][protocol+':'+candidate+'_vs_'+reference_name] = comparison
    print('F9: fixed-context score and scouting aggregates', flush=True)
    distribution = context_distribution(rows.loc[rows.partition.eq('train')])
    write(folder/'context_distribution.json', distribution)
    model, scaler = models_A['context_physics']
    reference_rows = rows.loc[rows.partition.eq('calibration')]
    review = rows.loc[rows.partition.eq('phase_review')]
    ref_p = standardized_probabilities(model, scaler, reference_rows, distribution)
    ref_u = ref_p @ UTILITY
    mu, sigma = float(ref_u.mean()), float(ref_u.std())
    if not np.isfinite(sigma) or sigma <= 1e-12:
        raise ValueError('Degenerate score reference')
    scale = dict(version=cfg['score'], mu=mu, sigma=sigma, reference_n=len(ref_u), reference_ids_sha256=ids_hash(reference_rows.pitch_uid.tolist()), distribution_sha256=sha256_file(folder/'context_distribution.json'), weights=UTILITY.tolist(), represents_runs=False, experimental=True)
    write(folder/'scale.json', scale)
    p = standardized_probabilities(model, scaler, review, distribution)
    scores = review[META+['auto_pitch_type', 'altitude_category']].copy()
    scores['experimental_score'] = 100+10*(p@UTILITY-mu)/sigma
    scores[PROBS] = p
    scores.to_parquet(folder/'standardized_scores.parquet', index=False)
    aggregates = scores.groupby(['pitcher_anon_id', 'auto_pitch_type'], sort=True).agg(n=('pitch_uid', 'size'), games=('game_anon_id','nunique'), score=('experimental_score','mean')).reset_index()
    aggregates['provisional'] = (aggregates.n < 200) | (aggregates.games < 5)
    aggregates['scope'] = '2025_review_observed_pitch_mix_experimental_not_runs'
    aggregates.to_csv(folder/'scouting.csv', index=False)
    summary['checks']['F8_unchanged'] = verify_release(RELEASE)['release_id'] == release_id
    summary['checks']['test_exposure_unchanged'] = sha256_file(exposure) == exposure_before
    summary['checks']['reference_score_mean_100'] = bool(np.isclose((100+10*(ref_u-mu)/sigma).mean(), 100))
    summary['checks']['reference_score_std_10'] = bool(np.isclose((100+10*(ref_u-mu)/sigma).std(), 10))
    summary['coverage'] = data['exclusions']
    dataset.assert_unchanged()
    if not all(summary['checks'].values()):
        raise AssertionError('F9 checks failed')
    write(folder/'summary.json', summary)
    write(folder/'manifest.json', dict(created_utc=datetime.now(timezone.utc).isoformat(), data_run=dataset.run_id,
          data_manifest_sha256=dataset.manifest_hash, source_sha256=sha256_file(Path(__file__)),
          config_sha256=sha256_file(ROOT/'config/phase9.json'), test_exposure_sha256=exposure_before,
          artifacts={str(p.relative_to(folder)).replace('\\','/'):sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file()}))
    print(str(folder), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    run(args.name, args.smoke)
