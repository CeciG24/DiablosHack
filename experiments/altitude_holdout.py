"""Leave-one-altitude-category-out transfer test for physical movement (IVB/HB).

Fit on 2024 rows of two categories, evaluate on 2025 rows of the held-out one.
Categories are dataset buckets, not stadiums: this is not a park holdout.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import duckdb
import lightgbm as lgb
from modeling.datasets import ROOT, META, ids_hash, sha256_file, require_unique, game_bucket, sample_games
from modeling.models import TabularEventModel
from experiments.phase9 import write
from experiments.phase10 import paired
from experiments.phase10_models import MOVEMENT_FEATURES

ORDINAL = 'altitude_ord'
FEATURES = {'control': MOVEMENT_FEATURES, 'ordinal': MOVEMENT_FEATURES+[ORDINAL], 'ordinal_linear': MOVEMENT_FEATURES+[ORDINAL]}
COLUMNS = ['pitch_uid', 'year', 'game_anon_id', 'pitcher_anon_id', 'altitude_category']+MOVEMENT_FEATURES+['induced_vert_break', 'horz_break']


def load_rows(run, cfg, smoke=False):
    run = Path(run)
    contract = json.loads((ROOT/'config/modeling_contract.json').read_text(encoding='utf-8'))['protocol_A']
    years = [cfg['train_year'], cfg['evaluation_year']]
    with duckdb.connect(str(run/'diablos.duckdb'), read_only=True) as db:
        rows = db.execute('SELECT '+','.join(COLUMNS)+' FROM model_base WHERE year IN (?, ?) AND eligible_pitching_default', years).df()
    rows = prepare(rows, cfg)
    if smoke:
        rows = sample_games(rows, cfg['smoke_max_rows'], cfg['seed'])
    lo, hi = contract['phase_review_bucket']
    buckets = rows.game_anon_id.map({g: game_bucket(g, contract['validation_hash_seed']) for g in rows.game_anon_id.unique()})
    rows['phase_review'] = rows.year.eq(cfg['evaluation_year']) & buckets.between(lo, hi)
    return rows


def prepare(rows, cfg):
    require_unique(rows)
    if not rows.year.isin([cfg['train_year'], cfg['evaluation_year']]).all():
        raise PermissionError('Only 2024/2025 development data are authorized')
    rows = rows.loc[rows.altitude_category.isin(cfg['categories'])].dropna(subset=MOVEMENT_FEATURES+cfg['targets']).copy()
    if rows.groupby('game_anon_id').altitude_category.nunique().gt(1).any():
        raise ValueError('A game spans several altitude categories')
    rows[ORDINAL] = rows.altitude_category.map(cfg['ordinal']).astype(float)
    return rows.sort_values('pitch_uid').reset_index(drop=True)


def make_fold(rows, heldout, cfg):
    if heldout not in cfg['categories']:
        raise ValueError('Unknown category')
    train = rows.loc[rows.year.eq(cfg['train_year']) & rows.altitude_category.ne(heldout)]
    shifted = rows.loc[rows.year.eq(cfg['evaluation_year']) & rows.altitude_category.eq(heldout)]
    indomain = rows.loc[rows.year.eq(cfg['evaluation_year']) & rows.altitude_category.ne(heldout)]
    if min(map(len, (train, shifted, indomain))) == 0:
        raise ValueError('Insufficient fold support for '+heldout)
    if heldout in set(train.altitude_category) or set(train.game_anon_id) & (set(shifted.game_anon_id) | set(indomain.game_anon_id)):
        raise ValueError('Held-out leakage')
    return train, shifted, indomain


class HoldoutMovementModel(TabularEventModel):
    def __init__(self, target, variant, cfg):
        if target not in cfg['targets'] or variant not in FEATURES:
            raise ValueError('Unknown holdout model')
        super().__init__(cfg['seed'], cfg['threads'], 'stuff', 'A')
        self.target, self.variant, self.cfg = target, variant, cfg
        self.features = FEATURES[variant].copy()
        self.categorical = [c for c in self.features if c in ('auto_pitch_type', 'pitcher_throws')]
        self.numeric = [c for c in self.features if c not in self.categorical]

    def fit_fold(self, rows, smoke=False):
        require_unique(rows)
        if rows.empty or not rows.year.eq(self.cfg['train_year']).all():
            raise PermissionError('Fit restricted to the training year')
        rows = rows.sort_values('pitch_uid')
        self.vocabularies = {c: sorted(rows[c].unique().tolist()) for c in self.categorical}
        params = dict(self.cfg['parameters'], objective='regression', metric='l2', seed=self.seed, deterministic=True,
                      force_col_wise=True, num_threads=self.threads, verbosity=-1)
        if self.variant == 'ordinal_linear':
            params.update(linear_tree=True, linear_lambda=self.cfg['linear_lambda'])
        rounds = 20 if smoke else self.cfg['rounds']
        self.booster = lgb.train(params, lgb.Dataset(self.transform(rows), label=rows[self.target], categorical_feature=self.categorical), num_boost_round=rounds)
        self.metadata = dict(target=self.target, variant=self.variant, rounds=rounds, fit_n=len(rows), fit_ids_sha256=ids_hash(rows.pitch_uid.tolist()),
                             train_categories=sorted(rows.altitude_category.unique().tolist()))
        return self

    def predict(self, rows):
        result = np.asarray(self.booster.predict(self.transform(rows), num_threads=self.threads), dtype=float)
        if not np.isfinite(result).all():
            raise ValueError('Non-finite predictions')
        return result


def orientation(rows):
    return rows.pitcher_throws.map({'Left': -1., 'Right': 1.}).to_numpy()


def metrics(rows, pred, target):
    error = pred-rows[target].to_numpy(float)
    sign = orientation(rows) if target == 'horz_break' else 1.
    return dict(n=len(rows), rmse_inches=float(np.sqrt(np.mean(error**2))), mae_inches=float(np.mean(np.abs(error))), bias_oriented_inches=float(np.mean(sign*error)))


def by_type(rows, predictions, target, minimum):
    records = []
    sign = orientation(rows) if target == 'horz_break' else np.ones(len(rows))
    for pitch_type, index in rows.groupby('auto_pitch_type').indices.items():
        record = dict(auto_pitch_type=pitch_type, n=len(index), observed_oriented_mean=float(np.mean(sign[index]*rows[target].to_numpy(float)[index])), provisional=len(index) < minimum)
        for variant, pred in predictions.items():
            error = pred[index]-rows[target].to_numpy(float)[index]
            record[variant] = dict(rmse_inches=float(np.sqrt(np.mean(error**2))), bias_oriented_inches=float(np.mean(sign[index]*error)))
        records.append(record)
    return records


def run(name, data_run=None, smoke=False):
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
        raise ValueError('Invalid experiment name')
    cfg = json.loads((ROOT/'config/altitude_holdout.json').read_text(encoding='utf-8'))
    run_path = Path(data_run) if data_run else ROOT/'data/runs'/(ROOT/'data/CURRENT').read_text(encoding='utf-8').strip()
    folder = ROOT/'artifacts/modeling'/name/'AH'
    folder.mkdir(parents=True, exist_ok=False)
    write(folder/'config.json', cfg)
    rows = load_rows(run_path, cfg, smoke)
    rows[['pitch_uid', 'year', 'game_anon_id', 'altitude_category', 'phase_review']].to_parquet(folder/'cohort_ids.parquet', index=False)
    summary = dict(version=cfg['version'], smoke=smoke, scope=cfg['scope'], data_run=run_path.name, new_2026_access=False, folds={}, checks={})
    tail_confidence = 1-cfg['familywise_alpha']/cfg['comparison_count']
    pcfg = dict(seed=cfg['seed'], bootstrap_repetitions=cfg['bootstrap_repetitions'], confidence=tail_confidence, minimum_relative_improvement=cfg['minimum_relative_improvement'])
    for heldout in cfg['categories']:
        train, shifted, indomain = make_fold(rows, heldout, cfg)
        fold = dict(train_categories=sorted(train.altitude_category.unique().tolist()), train_n=len(train), train_ids_sha256=ids_hash(train.pitch_uid.tolist()),
                    shifted_n=len(shifted), shifted_games=int(shifted.game_anon_id.nunique()), shifted_phase_review_n=int(shifted.phase_review.sum()),
                    indomain_n=len(indomain), targets={})
        for target in cfg['targets']:
            models, predictions, losses = {}, {}, {}
            entry = dict(models={}, comparisons={})
            for variant in cfg['variants']:
                print(f'AH heldout={heldout} {target}/{variant}: train={len(train)} shifted={len(shifted)}', flush=True)
                model = HoldoutMovementModel(target, variant, cfg).fit_fold(train, smoke)
                p, q = model.predict(shifted), model.predict(indomain)
                predictions[variant], losses[variant] = p, (p-shifted[target].to_numpy(float))**2
                review = shifted.phase_review.to_numpy()
                entry['models'][variant] = dict(shifted=metrics(shifted, p, target), shifted_phase_review=metrics(shifted.loc[review], p[review], target) if review.any() else None,
                                                indomain_2025=metrics(indomain, q, target), fit=model.metadata)
                model.booster.save_model(str(folder/f'{heldout.replace(" ", "_")}_{target}_{variant}.txt'))
            for variant in cfg['variants'][1:]:
                entry['comparisons'][variant+'_vs_control'] = paired(shifted, losses['control'], losses[variant], pcfg, smoke)
            entry['by_pitch_type'] = by_type(shifted, predictions, target, cfg['minimum_group_rows'])
            frame = shifted[['pitch_uid', 'game_anon_id', 'auto_pitch_type', 'pitcher_throws', target]].copy()
            for variant, p in predictions.items():
                frame['pred_'+variant] = p
            frame.to_parquet(folder/f'{heldout.replace(" ", "_")}_{target}_predictions.parquet', index=False)
            fold['targets'][target] = entry
        summary['folds'][heldout] = fold
    summary['checks']['heldout_never_in_train'] = all(heldout not in f['train_categories'] for heldout, f in summary['folds'].items())
    summary['checks']['only_2024_2025'] = bool(rows.year.isin([cfg['train_year'], cfg['evaluation_year']]).all())
    if not all(summary['checks'].values()):
        raise AssertionError('Altitude holdout checks failed')
    write(folder/'summary.json', summary)
    write(folder/'manifest.json', dict(created_utc=datetime.now(timezone.utc).isoformat(), data_manifest_sha256=sha256_file(run_path/'manifest.json'),
          config_sha256=sha256_file(ROOT/'config/altitude_holdout.json'), source_sha256=sha256_file(Path(__file__)),
          artifacts={str(p.relative_to(folder)).replace('\\', '/'): sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file()}))
    print(str(folder), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--data-run', help='Path to data/runs/<id>; defaults to data/CURRENT under the repository')
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    run(args.name, args.data_run, args.smoke)
