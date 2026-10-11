"""Protocol C: fixed 2024 references and explicitly allowlisted arsenal models."""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb
from modeling.baselines import CLASSES
from modeling.datasets import PITCHING, ids_hash, pd, require_unique, sha256_file
from modeling.models import TabularEventModel, BACKEND_VERSION

ARSENAL = ['historical_type_usage', 'velo_diff_vs_fb', 'ivb_diff_vs_fb',
           'hb_diff_vs_fb', 'release_distance_vs_fb']
PHYSICAL = ['rel_speed', 'induced_vert_break', 'horz_break', 'rel_height', 'rel_side']


def build_reference(history, minimum=30, fastball_types=('Four-Seam', 'Sinker')):
    require_unique(history)
    if history.empty or not history.year.eq(2024).all():
        raise PermissionError('Arsenal reference requires exclusively 2024 pitches')
    history = history.sort_values('pitch_uid').loc[history.pitcher_anon_id.notna()].copy()
    counts = history.groupby(['pitcher_anon_id', 'auto_pitch_type']).size().rename('historical_type_n').reset_index()
    totals = history.groupby('pitcher_anon_id').size().rename('historical_pitcher_n').reset_index()
    valid = history.auto_pitch_type.isin(fastball_types) & history[PHYSICAL].notna().all(axis=1)
    refs = history.loc[valid].groupby(['pitcher_anon_id', 'auto_pitch_type']).agg(
        fb_n=('pitch_uid', 'size'), fb_velocity=('rel_speed', 'mean'),
        fb_ivb=('induced_vert_break', 'mean'), fb_hb=('horz_break', 'mean'),
        fb_release_height=('rel_height', 'mean'), fb_release_side=('rel_side', 'mean'),
        source_max_year=('year', 'max')).reset_index()
    refs = refs.loc[refs.fb_n.ge(minimum)].sort_values(
        ['pitcher_anon_id', 'fb_n', 'auto_pitch_type'], ascending=[True, False, True]).drop_duplicates('pitcher_anon_id')
    refs = refs.rename(columns={'auto_pitch_type': 'reference_fastball_type'})
    return refs.reset_index(drop=True), counts, totals


def attach_reference(rows, refs, counts, totals, cold_start=False):
    require_unique(rows)
    if not rows.year.isin([2025, 2026]).all():
        raise PermissionError('Fixed reference is for 2025/2026 inputs only')
    if len(refs) and not refs.source_max_year.eq(2024).all():
        raise PermissionError('Future history is forbidden')
    result = rows.merge(refs, on='pitcher_anon_id', how='left', validate='many_to_one', sort=False)
    result = result.merge(counts, on=['pitcher_anon_id', 'auto_pitch_type'], how='left', validate='many_to_one', sort=False)
    result = result.merge(totals, on='pitcher_anon_id', how='left', validate='many_to_one', sort=False)
    result['historical_type_usage'] = result.historical_type_n.fillna(0) / result.historical_pitcher_n
    result['velo_diff_vs_fb'] = result.rel_speed-result.fb_velocity
    result['ivb_diff_vs_fb'] = result.induced_vert_break-result.fb_ivb
    result['hb_diff_vs_fb'] = result.horz_break-result.fb_hb
    result['release_distance_vs_fb'] = np.hypot(result.rel_height-result.fb_release_height, result.rel_side-result.fb_release_side)
    result['has_reference'] = result.fb_n.notna() & result[ARSENAL].notna().all(axis=1)
    if cold_start:
        result['has_reference'] = False
        result[ARSENAL] = np.nan
    result['history_status'] = np.where(result.has_reference, 'fixed_2024_history', 'insufficient_history')
    return result


class ArsenalEventModel(TabularEventModel):
    """Fixed budget, no early stopping: only 2025 development labels are fit."""
    def __init__(self, with_arsenal=False, seed=20260929, threads=4):
        super().__init__(seed, threads, 'pitching', 'A')
        self.protocol = 'C'
        self.with_arsenal = bool(with_arsenal)
        self.features = PITCHING.copy() + (ARSENAL if with_arsenal else [])
        self.numeric = [c for c in self.features if c not in self.categorical]

    def fit(self, training, parameters, rounds=200):
        require_unique(training)
        if training.empty or not training.year.eq(2025).all() or not training.partition.eq('development').all():
            raise PermissionError('Protocol C fit requires only 2025/development')
        if training.game_anon_id.isna().any() or set(training.y_event) != set(CLASSES):
            raise ValueError('Valid games and all six classes required')
        if set(parameters) != {'num_leaves', 'min_data_in_leaf', 'learning_rate', 'lambda_l2'} or rounds < 1:
            raise ValueError('Invalid fixed training configuration')
        training = training.sort_values('pitch_uid').reset_index(drop=True)
        self.vocabularies = {c: sorted(training[c].dropna().unique().tolist()) for c in self.categorical}
        params = dict(parameters, objective='multiclass', num_class=6, metric='multi_logloss',
                      seed=self.seed, deterministic=True, force_col_wise=True, num_threads=self.threads,
                      device_type='cpu', verbosity=-1, feature_fraction=1., bagging_fraction=1., bagging_freq=0)
        data = lgb.Dataset(self.transform(training), label=pd.Index(CLASSES).get_indexer(training.y_event),
                           categorical_feature=self.categorical)
        self.booster = lgb.train(params, data, num_boost_round=rounds)
        self.metadata = dict(schema_version=1, protocol_id='C', family='pitching', with_arsenal=self.with_arsenal,
                             backend_version=BACKEND_VERSION, features=self.features, classes=list(CLASSES),
                             seed=self.seed, threads=self.threads, vocabularies=self.vocabularies,
                             fit_year=2025, fit_partition='development', fit_rows=len(training),
                             fit_ids_sha256=ids_hash(training.pitch_uid.tolist()), parameters=params,
                             best_iteration=rounds, selection_policy='predeclared_fixed_rounds_no_review_selection')
        return self

    @classmethod
    def load(cls, directory):
        folder = Path(directory)
        m = json.loads((folder/'preprocessing.json').read_text(encoding='utf-8'))
        model = cls(m['with_arsenal'], m['seed'], m['threads'])
        if (m['schema_version'] != 1 or m['protocol_id'] != 'C' or m['fit_year'] != 2025
                or m['fit_partition'] != 'development' or m['features'] != model.features
                or m['classes'] != list(CLASSES) or m['backend_version'] != BACKEND_VERSION
                or m['model_sha256'] != sha256_file(folder/'model.txt')):
            raise ValueError('Invalid protocol C model')
        model.metadata, model.vocabularies = m, m['vocabularies']
        model.booster = lgb.Booster(model_file=str(folder/'model.txt'))
        if model.booster.feature_name() != model.features or model.booster.num_model_per_iteration() != 6:
            raise ValueError('Invalid protocol C feature/class schema')
        return model


def route_probabilities(base, control, arsenal, has_reference, promote):
    """Cold-start or missing history always uses the full-population C base."""
    mask = np.asarray(has_reference, dtype=bool)
    result = base.copy()
    result[mask] = (arsenal if promote else control)
    routes = np.where(mask, 'arsenal' if promote else 'base', 'fallback')
    return result, routes


def predict_policy(directory, rows, cold_start=False):
    """Reload a C policy on feature rows; outcomes are neither required nor read.

    This batch helper covers valid model inputs. The F8 invalid-row API is separate.
    Cold-start explicitly suppresses supplied historical references.
    """
    from modeling.calibration import TemperatureScaler
    folder = Path(directory)
    policy = json.loads((folder/'policy.json').read_text(encoding='utf-8'))
    reference = [pd.read_parquet(folder/'reference_2024'/(name+'.parquet'))
                 for name in ('fastballs','type_counts','pitcher_counts')]
    frame = attach_reference(rows, *reference, cold_start=cold_start)
    def predict(name, inputs):
        p = ArsenalEventModel.load(folder/name/'model').predict(inputs)
        calibration = json.loads((folder/name/'calibration_policy.json').read_text(encoding='utf-8'))
        if calibration['route'] == 'temperature':
            p = TemperatureScaler.load(folder/name/'temperature.json').transform(p)
        return p
    probabilities = predict('fallback', frame)
    covered = frame.has_reference.to_numpy() & policy['available']
    routes = np.full(len(frame), 'fallback', dtype=object)
    if covered.any():
        probabilities[covered] = predict(policy['history_branch'], frame.loc[covered])
        routes[covered] = 'arsenal' if policy['promote_arsenal'] else 'base'
    output = frame[['pitch_uid']].copy()
    output[['p_'+c for c in CLASSES]] = probabilities
    output['route'] = routes
    output['warnings'] = np.where(cold_start | ~frame.has_reference, 'insufficient_history', '')
    output['protocol_id'] = 'C'
    return output
