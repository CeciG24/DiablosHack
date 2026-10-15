"""F10 candidate: physical Stuff heads with pitcher-relative (arsenal) features and a type-neutral index."""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
from scipy.stats import rankdata

from modeling.baselines import CLASSES
from modeling.datasets import STUFF, duckdb, ids_hash, join_pitches, pd, sha256_file
from modeling.metrics import validate_probabilities
from modeling.models import BACKEND_VERSION, CATEGORICAL
from modeling.protocols import validate_fit_partition

DERIVATION_ID = 'stuff_v3_relative_arsenal_v1'
HEAD_TARGETS = {'whiff_given_swing': 'y_whiff_given_swing', 'groundball_bip': 'y_groundball_bip',
                'hard_contact_bip': 'y_hard_contact_bip'}
BINARY = (0, 1)
PHYSICAL = ['rel_speed', 'induced_vert_break', 'horz_break', 'rel_height', 'rel_side']
FASTBALLS = ('Four-Seam', 'Sinker')
REL = ['rel_d_speed', 'rel_d_ivb', 'rel_d_hb', 'rel_d_release']
CONTEXT = ['balls', 'strikes']
VARIANTS = {'base': STUFF, 'refA': STUFF + REL, 'refB': STUFF + REL}
REFERENCE_MODES = {'base': None, 'refA': 'same_season', 'refB': 'prior_season_at_inference'}
PARAMETER_KEYS = {'num_leaves', 'min_data_in_leaf', 'learning_rate', 'lambda_l2'}
REFERENCE_INPUTS = ['pitcher_anon_id', 'year', 'auto_pitch_type'] + PHYSICAL


def build_relative_reference(frame, minimum=30):
    """Per pitcher-year fastball profile from physical covariates only; never reads outcomes."""
    if set(frame.columns) != set(REFERENCE_INPUTS):
        raise ValueError('Reference builder accepts exactly the physical covariate columns')
    valid = frame.loc[frame.pitcher_anon_id.notna() & frame.auto_pitch_type.isin(FASTBALLS)
                      & frame[PHYSICAL].notna().all(axis=1)]
    refs = valid.groupby(['pitcher_anon_id', 'year', 'auto_pitch_type']).agg(
        fb_n=('rel_speed', 'size'), fb_speed=('rel_speed', 'mean'), fb_ivb=('induced_vert_break', 'mean'),
        fb_hb=('horz_break', 'mean'), fb_height=('rel_height', 'mean'), fb_side=('rel_side', 'mean')).reset_index()
    refs = refs.loc[refs.fb_n.ge(minimum)].sort_values(
        ['pitcher_anon_id', 'year', 'fb_n', 'auto_pitch_type'], ascending=[True, True, False, True]
    ).drop_duplicates(['pitcher_anon_id', 'year'])
    return refs.rename(columns={'auto_pitch_type': 'reference_type', 'year': 'reference_year'}).reset_index(drop=True)


def reference_years(rows, mode):
    """Year of the reference used per row. refB: train uses its own season, evaluation uses the prior one."""
    year = rows.year.to_numpy()
    if mode == 'same_season':
        return year
    if mode == 'prior_season_at_inference':
        return np.where(rows.partition.eq('train').to_numpy(), year, year - 1)
    raise ValueError('Unknown reference mode')


def attach_relative(rows, refs, mode):
    out = rows.copy()
    out['reference_year'] = reference_years(out, mode)
    merged = out[['pitch_uid', 'pitcher_anon_id', 'reference_year']].merge(
        refs, on=['pitcher_anon_id', 'reference_year'], how='left', validate='many_to_one')
    if not merged.pitch_uid.equals(out.pitch_uid.reset_index(drop=True)):
        raise ValueError('Reference merge changed row order')
    merged.index = out.index
    out['rel_d_speed'] = out.rel_speed - merged.fb_speed
    out['rel_d_ivb'] = out.induced_vert_break - merged.fb_ivb
    out['rel_d_hb'] = out.horz_break - merged.fb_hb
    out['rel_d_release'] = np.hypot(out.rel_height - merged.fb_height, out.rel_side - merged.fb_side)
    out['has_reference'] = merged.fb_n.notna()
    return out.drop(columns='reference_year')


def load_head_targets(dataset, rows):
    """Conditional Stuff targets for 2024/2025 only; nulls stay null."""
    dataset.assert_unchanged()
    columns = ', '.join(['pitch_uid'] + list(HEAD_TARGETS.values()))
    with duckdb.connect(str(dataset.run / 'diablos.duckdb'), read_only=True) as db:
        labels = db.execute(f'SELECT {columns} FROM model_base WHERE year IN (2024, 2025)').df()
    result = join_pitches(rows, labels).sort_values('pitch_uid').reset_index(drop=True)
    if len(result) != len(rows):
        raise ValueError('Head target join lost pitches')
    for column in HEAD_TARGETS.values():
        result[column] = pd.to_numeric(result[column], errors='coerce')
        if not result[column].dropna().isin(BINARY).all():
            raise ValueError('Invalid binary target: ' + column)
    dataset.assert_unchanged()
    return result


def smoothed_binary_prevalence(training, target):
    validate_fit_partition(training, 'train', 'A')
    labels = training[target].dropna()
    return float((labels.sum() + 1) / (len(labels) + 2))


def auc(labels, scores):
    y, p = np.asarray(labels, dtype=int), np.asarray(scores, dtype=float)
    positives = int(y.sum())
    if positives == 0 or positives == len(y):
        return None
    ranks = rankdata(p)
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * (len(y) - positives)))


class StuffV3Model:
    """LightGBM over an explicit allowlist; relative features may be missing, physics may not."""

    def __init__(self, features, classes, seed=20260929, threads=4, variant='base', task='head'):
        if lgb.__version__ != BACKEND_VERSION:
            raise RuntimeError(f'Install lightgbm=={BACKEND_VERSION} from requirements-modeling.txt')
        if not set(STUFF).issubset(features) or set(features) - set(STUFF + REL + CONTEXT):
            raise ValueError('Feature list outside the Stuff/relative/count allowlist')
        self.features, self.classes = list(features), list(classes)
        self.categorical = [c for c in self.features if c in CATEGORICAL]
        self.optional = [c for c in self.features if c in REL]
        self.numeric = [c for c in self.features if c not in self.categorical]
        self.seed, self.threads, self.variant, self.task = int(seed), int(threads), variant, task
        self.vocabularies = self.booster = self.metadata = None

    def transform(self, frame):
        if self.vocabularies is None:
            raise RuntimeError('Encoder is not fitted')
        if not frame.columns.is_unique or not set(self.features).issubset(frame.columns):
            raise ValueError('All unique model columns are required')
        X = frame[self.features].copy()
        required = [c for c in self.features if c not in self.optional]
        if X[required].isna().any().any():
            raise ValueError('Missing model features: complete physical inputs required; no imputation')
        for column in self.numeric:
            values = pd.to_numeric(X[column], errors='coerce').to_numpy(dtype=float)
            if np.isinf(values).any() or (column not in self.optional and np.isnan(values).any()):
                raise ValueError(f'Non-numeric or non-finite feature: {column}')
            if column in CONTEXT and not (np.isin(values, np.arange(4 if column == 'balls' else 3))).all():
                raise ValueError(f'Invalid {column}')
            X[column] = values
        for column in self.categorical:
            if not X[column].map(lambda value: isinstance(value, str)).all():
                raise ValueError(f'Categorical values must be strings: {column}')
            X[column] = X[column].map({v: i for i, v in enumerate(self.vocabularies[column])}).fillna(-1).astype('int32')
        return X

    def fit(self, training, development, label, parameters, rounds=800, patience=40):
        validate_fit_partition(training, 'train', 'A')
        validate_fit_partition(development, 'development', 'A')
        if set(training.pitch_uid) & set(development.pitch_uid) or set(training.game_anon_id) & set(development.game_anon_id):
            raise ValueError('Training and development must be disjoint by pitch and game')
        if set(parameters) != PARAMETER_KEYS:
            raise ValueError('Only the declared hyperparameters may vary')
        if rounds < 1 or patience < 1 or self.threads < 1:
            raise ValueError('Rounds, patience and threads must be positive')
        training = training.loc[training[label].notna()].sort_values('pitch_uid').reset_index(drop=True)
        development = development.loc[development[label].notna()].sort_values('pitch_uid').reset_index(drop=True)
        if set(training[label]) != set(self.classes) or not development[label].isin(self.classes).all():
            raise ValueError('Training needs every class; development labels must be known')
        self.vocabularies = {c: sorted(training[c].dropna().unique().tolist()) for c in self.categorical}
        binary = len(self.classes) == 2
        params = dict(parameters, objective='binary' if binary else 'multiclass', metric='binary_logloss' if binary else 'multi_logloss',
                      seed=self.seed, data_random_seed=self.seed, feature_fraction_seed=self.seed, bagging_seed=self.seed,
                      deterministic=True, force_col_wise=True, num_threads=self.threads, device_type='cpu',
                      verbosity=-1, feature_fraction=1.0, bagging_fraction=1.0, bagging_freq=0)
        if not binary:
            params['num_class'] = len(self.classes)
        index = pd.Index(self.classes)
        if binary:
            training, development = training.assign(**{label: training[label].astype(int)}), development.assign(**{label: development[label].astype(int)})
        train_data = lgb.Dataset(self.transform(training), label=index.get_indexer(training[label]),
                                 categorical_feature=self.categorical, free_raw_data=False)
        dev_data = lgb.Dataset(self.transform(development), label=index.get_indexer(development[label]),
                               reference=train_data, categorical_feature=self.categorical)
        history = {}
        self.booster = lgb.train(params, train_data, num_boost_round=rounds, valid_sets=[dev_data],
                                 valid_names=['development'],
                                 callbacks=[lgb.early_stopping(patience, first_metric_only=True, verbose=False),
                                            lgb.record_evaluation(history)])
        metric = params['metric']
        self.metadata = {
            'schema_version': 1, 'derivation': DERIVATION_ID, 'task': self.task, 'variant': self.variant,
            'reference_mode': REFERENCE_MODES.get(self.variant), 'label': label, 'features': self.features,
            'classes': self.classes, 'vocabularies': self.vocabularies, 'backend': 'lightgbm',
            'backend_version': BACKEND_VERSION, 'seed': self.seed, 'threads': self.threads, 'parameters': params,
            'maximum_rounds': rounds, 'patience': patience, 'best_iteration': self.booster.best_iteration,
            'iterations_evaluated': len(history['development'][metric]),
            'fit_partition': 'train', 'fit_year': 2024, 'early_stopping_partition': 'development',
            'fit_rows': len(training), 'fit_ids_sha256': ids_hash(training.pitch_uid.tolist()),
            'development_rows': len(development), 'development_ids_sha256': ids_hash(development.pitch_uid.tolist()),
            'unknown_category_policy': 'native_missing_branch_with_warning',
            'missing_input_policy': 'physics_rejected_relative_native_missing', 'post_release_development': True}
        return self

    def predict(self, frame):
        if self.booster is None:
            raise RuntimeError('Model is not fitted')
        X = self.transform(frame)
        if frame.empty:
            return np.empty((0, len(self.classes)))
        p = self.booster.predict(X, num_iteration=self.metadata['best_iteration'], num_threads=self.threads)
        if len(self.classes) == 2:
            p = np.column_stack([1 - p, p])
        return validate_probabilities(p, len(self.classes))

    def save(self, directory):
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=False)
        self.booster.save_model(str(folder / 'model.txt'), num_iteration=self.metadata['best_iteration'])
        metadata = dict(self.metadata, model_sha256=sha256_file(folder / 'model.txt'))
        (folder / 'preprocessing.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')

    @classmethod
    def load(cls, directory):
        folder = Path(directory)
        meta = json.loads((folder / 'preprocessing.json').read_text(encoding='utf-8'))
        model = cls(meta['features'], meta['classes'], meta['seed'], meta['threads'], meta['variant'], meta['task'])
        if (meta['schema_version'] != 1 or meta['derivation'] != DERIVATION_ID or meta['backend_version'] != BACKEND_VERSION
                or meta['fit_partition'] != 'train' or meta['early_stopping_partition'] != 'development'
                or meta['model_sha256'] != sha256_file(folder / 'model.txt')
                or set(meta['vocabularies']) != set(model.categorical)):
            raise ValueError('Incompatible or corrupted StuffV3 artifact')
        model.metadata, model.vocabularies = meta, meta['vocabularies']
        model.booster = lgb.Booster(model_file=str(folder / 'model.txt'))
        if model.booster.feature_name() != model.features:
            raise ValueError('Model feature schema mismatch')
        return model

    def warnings(self, frame):
        self.transform(frame)
        flags = [frame[c].isin(self.vocabularies[c]).to_numpy() for c in self.categorical]
        missing = ~frame[self.optional].notna().all(axis=1).to_numpy() if self.optional else np.zeros(len(frame), bool)
        return [';'.join(
            [f'unknown_category:{c}' for c, ok in zip(self.categorical, flags) if not ok[i]]
            + (['insufficient_arsenal_reference'] if missing[i] else [])) for i in range(len(frame))]


def index_scale(reference_scores):
    values = np.asarray(reference_scores, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all() or values.std() == 0:
        raise ValueError('Invalid reference scores')
    return {'mean': float(values.mean()), 'std': float(values.std()), 'n': len(values)}


def to_index(scores, scale):
    return 100 + 10 * (np.asarray(scores, dtype=float) - scale['mean']) / scale['std']


def within_type_scale(reference, score_column):
    """Per pitch-type mean/std from a fixed reference; global fallback for rare or unseen types."""
    by_type = {}
    for pitch_type, group in reference.groupby('auto_pitch_type'):
        std = float(group[score_column].std(ddof=0))
        if len(group) >= 200 and std > 0:
            by_type[str(pitch_type)] = {'mean': float(group[score_column].mean()), 'std': std, 'n': len(group)}
    return {'global': index_scale(reference[score_column]), 'by_type': by_type}


def to_index_within_type(frame, score_column, scale):
    stats = scale['by_type']
    mean = frame.auto_pitch_type.map(lambda t: stats.get(t, scale['global'])['mean']).to_numpy(dtype=float)
    std = frame.auto_pitch_type.map(lambda t: stats.get(t, scale['global'])['std']).to_numpy(dtype=float)
    return 100 + 10 * (frame[score_column].to_numpy(dtype=float) - mean) / std


def type_variance_share(scores, types):
    scores = pd.Series(np.asarray(scores, dtype=float))
    total = scores.var(ddof=0)
    within = (scores - scores.groupby(pd.Series(np.asarray(types)).values).transform('mean')).var(ddof=0)
    return float(1 - within / total) if total > 0 else None


def within_type_correlation(scores, types, labels):
    frame = pd.DataFrame({'s': np.asarray(scores, dtype=float), 't': np.asarray(types), 'y': np.asarray(labels, dtype=float)})
    frame['s'] = frame.s - frame.groupby('t').s.transform('mean')
    frame['y'] = frame.y - frame.groupby('t').y.transform('mean')
    return float(np.corrcoef(frame.s, frame.y)[0, 1])


def event_utility_s0(probabilities, weights):
    p = pd.DataFrame(probabilities, columns=CLASSES)
    return sum(float(weights[c]) * p[c].to_numpy() for c in CLASSES)
