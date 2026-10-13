"""Categorical environment association, with train-only support and honest uncertainty."""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler
from modeling.datasets import PITCHING, ids_hash, pd, require_unique, sha256_file
from modeling.models import TabularEventModel, BACKEND_VERSION

MODE = 'fixed_shape_environment_association'
ENV = 'altitude_category'
COMBINATION = [ENV, 'auto_pitch_type', 'pitcher_throws', 'batter_side']
PROBS = ['p_'+c for c in CLASSES]


def training_support(training, numeric, minimum=200):
    """Marginal ranges within category + counts of type/hand combinations, not joint density."""
    if training.empty or not training.year.eq(2024).all() or not training.partition.eq('train').all():
        raise PermissionError('Support may use only 2024/train')
    categories = sorted(training[ENV].unique().tolist())
    bounds = {category: {c: [float(group[c].min()), float(group[c].max())] for c in numeric}
              for category, group in training.groupby(ENV)}
    counts = training.groupby(COMBINATION).size().rename('n').reset_index().to_dict('records')
    return dict(categories=categories, numeric_bounds_by_category=bounds, combination_counts=counts,
                minimum_combination_rows=minimum, fit_ids_sha256=ids_hash(training.pitch_uid.tolist()),
                method='marginal_min_max_by_environment_and_type_hand_counts',
                limitation='Passing these checks does not establish full multivariate support or causality')


def support_warnings(frame, support):
    warnings = pd.Series('', index=frame.index, dtype=object)
    for category, bounds in support['numeric_bounds_by_category'].items():
        within = frame[ENV].eq(category)
        for feature, (low, high) in bounds.items():
            bad = within & ~frame[feature].between(low, high)
            warnings.loc[bad] += 'outside_training_range:'+feature+';'
    counts = pd.DataFrame(support['combination_counts'])
    known = frame[COMBINATION].merge(counts, on=COMBINATION, how='left', validate='many_to_one', sort=False)['n']
    sparse = known.fillna(0).lt(support['minimum_combination_rows']).to_numpy()
    warnings.loc[sparse] += 'sparse_or_unseen_environment_type_hand_combination;'
    return warnings.str.rstrip(';').tolist()


class EnvironmentEventModel(TabularEventModel):
    """F6 A model; base fit validation, encoders, determinism and save format are reused."""
    def __init__(self, with_environment=True, seed=20260929, threads=4):
        super().__init__(seed, threads, 'pitching', 'A')
        self.with_environment = bool(with_environment)
        if self.with_environment:
            self.features = self.features + [ENV]
            self.categorical = self.categorical + [ENV]

    def fit(self, training, development, parameters, rounds=400, patience=30, minimum_support=200):
        # Unknown environment is never assigned the generic missing-category branch.
        if self.with_environment and not set(development[ENV]).issubset(set(training[ENV])):
            raise ValueError('unsupported_environment in development')
        super().fit(training, development, parameters, rounds, patience)
        self.metadata['with_environment'] = self.with_environment
        if self.with_environment:
            self.metadata['environment_support'] = training_support(training, self.numeric, minimum_support)
            self.metadata['environment_mode'] = MODE
        return self

    def transform(self, frame):
        if self.with_environment and self.vocabularies is not None:
            if ENV not in frame or not frame[ENV].isin(self.vocabularies[ENV]).all():
                raise ValueError('unsupported_environment')
        return super().transform(frame)

    @classmethod
    def load(cls, directory):
        folder = Path(directory)
        m = json.loads((folder/'preprocessing.json').read_text(encoding='utf-8'))
        model = cls(m['with_environment'], m['seed'], m['threads'])
        if (m['schema_version'] != 1 or m['protocol_id'] != 'A' or m['family'] != 'pitching'
                or m['fit_year'] != 2024 or m['fit_partition'] != 'train'
                or m['early_stopping_partition'] != 'development' or m['features'] != model.features
                or m['classes'] != list(CLASSES) or m['backend_version'] != BACKEND_VERSION
                or m['model_sha256'] != sha256_file(folder/'model.txt')):
            raise ValueError('Invalid F6 model artifact')
        if set(m['vocabularies']) != set(model.categorical) or any(not v or len(v) != len(set(v)) for v in m['vocabularies'].values()):
            raise ValueError('Invalid vocabularies')
        if model.with_environment and (m['environment_support']['fit_ids_sha256'] != m['fit_ids_sha256']
                or m['environment_support']['categories'] != m['vocabularies'][ENV]):
            raise ValueError('Invalid environment support')
        model.metadata, model.vocabularies = m, m['vocabularies']
        model.booster = lgb.Booster(model_file=str(folder/'model.txt'))
        if model.booster.feature_name() != model.features or model.booster.num_model_per_iteration() != len(CLASSES):
            raise ValueError('Invalid F6 model schema')
        return model


class EnvironmentSimulator:
    """Always exposes the environmental candidate as a diagnostic, even when not promoted."""
    def __init__(self, model, scaler=None, promoted=False):
        if not model.with_environment or model.metadata is None:
            raise ValueError('A fitted environment model is required')
        self.model, self.scaler, self.promoted = model, scaler, bool(promoted)

    @classmethod
    def load(cls, directory):
        folder = Path(directory)
        policy = json.loads((folder/'policy.json').read_text(encoding='utf-8'))
        calibration = json.loads((folder/'environment/calibration_policy.json').read_text(encoding='utf-8'))
        scaler = TemperatureScaler.load(folder/'environment/temperature.json') if calibration['route'] == 'temperature' else None
        return cls(EnvironmentEventModel.load(folder/'environment/model'), scaler, policy['promote_environment'])

    def predict(self, inputs):
        require_unique(inputs)
        if not inputs.columns.is_unique or not set(['pitch_uid']+PITCHING+[ENV]).issubset(inputs.columns):
            raise ValueError('Required unique input columns are missing')
        frame = inputs.reset_index(drop=True).copy()
        output = frame[['pitch_uid']].copy()
        output[PROBS] = np.nan
        output['status'] = 'ok'
        output['warnings'] = ''
        output['input_support_status'] = 'within_checked_support'
        invalid = pd.Series(False, index=frame.index)
        for column in self.model.numeric:
            converted = pd.to_numeric(frame[column], errors='coerce')
            invalid |= converted.isna() | ~np.isfinite(converted)
            frame[column] = converted
            if column in ('balls', 'strikes'):
                invalid |= ~converted.between(0, 3 if column == 'balls' else 2) | converted.mod(1).ne(0)
        for column in self.model.categorical:
            if column != ENV:
                invalid |= ~frame[column].map(lambda v: isinstance(v, str)).astype(bool)
        unknown = ~frame[ENV].isin(self.model.vocabularies[ENV])
        output.loc[invalid, ['status','warnings','input_support_status']] = ['invalid_input','missing_or_invalid_feature','not_evaluated']
        output.loc[unknown, ['status','warnings','input_support_status']] = ['unsupported_environment','category_not_seen_in_training','not_evaluated']
        valid = ~(invalid | unknown)
        if valid.any():
            values = self.model.predict(frame.loc[valid])
            if self.scaler is not None:
                values = self.scaler.transform(values)
            output.loc[valid, PROBS] = values
            warnings = support_warnings(frame.loc[valid], self.model.metadata['environment_support'])
            output.loc[valid, 'warnings'] = warnings
            output.loc[valid, 'input_support_status'] = np.where(np.array(warnings) == '', 'within_checked_support', 'outside_support')
        output['environment_mode'] = MODE
        output['candidate_status'] = 'validated' if self.promoted else 'experimental'
        output['recommendation_allowed'] = False
        return output

    def simulate(self, inputs, target_category):
        before = self.predict(inputs)
        changed = inputs.copy(deep=True)
        changed[ENV] = target_category
        after = self.predict(changed)
        output = inputs[['pitch_uid', ENV]].reset_index(drop=True).rename(columns={ENV:'source_environment'})
        output['target_environment'] = target_category
        valid = before.status.eq('ok') & after.status.eq('ok')
        for column in PROBS:
            output['source_'+column] = before[column].where(valid)
            output['target_'+column] = after[column].where(valid)
            output['delta_'+column] = (after[column]-before[column]).where(valid)
        output['status'] = np.where(before.status.ne('ok'), before.status, after.status)
        output['warnings'] = ('source:'+before.warnings+';target:'+after.warnings).where(
            before.warnings.ne('') | after.warnings.ne(''), '')
        output['input_support_status'] = np.where(~valid, 'not_evaluated',
            np.where(before.input_support_status.eq('within_checked_support') & after.input_support_status.eq('within_checked_support'),
                     'within_checked_support', 'outside_support'))
        output['environment_mode'] = MODE
        output['candidate_status'] = 'validated' if self.promoted else 'experimental'
        output['recommendation_allowed'] = False
        return output


def cohort_delta_interval(simulations, game_ids, repetitions, seed, confidence=.95, minimum=200, smoke=False):
    """Pitch-weighted cohort mean association: fixed-model, whole-game percentile bootstrap."""
    if repetitions < 2 or not 0 < confidence < 1:
        raise ValueError('Invalid bootstrap configuration')
    require_unique(simulations)
    require_unique(game_ids)
    joined = simulations.merge(game_ids[['pitch_uid','game_anon_id']], on='pitch_uid', validate='one_to_one', how='left')
    if joined.game_anon_id.isna().any():
        raise ValueError('Missing game IDs')
    eligible = joined.status.eq('ok') & joined.input_support_status.eq('within_checked_support')
    frame = joined.loc[eligible]
    columns = ['delta_'+p for p in PROBS]
    if len(frame) and not np.isfinite(frame[columns].to_numpy()).all():
        raise ValueError('Invalid scenario deltas')
    result = dict(n_total=len(joined), n_pitches=len(frame), n_excluded=int((~eligible).sum()),
                  ids_sha256=ids_hash(frame.pitch_uid.tolist()), n_games=int(frame.game_anon_id.nunique()),
                  resamples=repetitions, seed=seed, confidence=confidence, environment_mode=MODE,
                  scope='cohort_mean_fixed_model_association_not_individual_not_causal_not_refit_uncertainty',
                  status='insufficient_data', scientific_evidence=not smoke, classes={})
    if len(frame) < minimum or result['n_games'] < 2:
        result['scientific_evidence'] = False
        return result
    grouped = frame.groupby('game_anon_id', sort=True)
    sums, counts = grouped[columns].sum().to_numpy(), grouped.size().to_numpy()
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(repetitions):
        sample = rng.integers(0, len(counts), len(counts))
        values.append(sums[sample].sum(axis=0)/counts[sample].sum())
    low, high = np.quantile(values, [(1-confidence)/2, (1+confidence)/2], axis=0)
    means = frame[columns].mean().to_numpy()
    result['classes'] = {c: dict(mean_delta=float(means[i]), ci_low=float(low[i]), ci_high=float(high[i])) for i,c in enumerate(CLASSES)}
    result['status'] = 'smoke_only' if smoke else 'evaluated'
    return result
