"""Physical Stuff model: train-only vocabularies and native CPU LightGBM files."""
import json
from pathlib import Path

from modeling.baselines import CLASSES
from modeling.datasets import STUFF, ids_hash, pd, require_unique, sha256_file
from modeling.metrics import multiclass_metrics, validate_probabilities
import lightgbm as lgb
import numpy as np

BACKEND_VERSION = '4.6.0'
CATEGORICAL = ['auto_pitch_type', 'pitcher_throws']
NUMERIC = [column for column in STUFF if column not in CATEGORICAL]


def validate_partition(frame, year, partition):
    require_unique(frame)
    if frame.empty or not frame.year.eq(year).all() or not frame.partition.eq(partition).all():
        raise PermissionError(f'Requires {year}/{partition} only')
    if frame.game_anon_id.isna().any() or not frame.y_event.isin(CLASSES).all():
        raise ValueError('Missing game or unknown/null target')


class StuffModel:
    def __init__(self, seed=20260929, threads=4):
        if lgb.__version__ != BACKEND_VERSION:
            raise RuntimeError(f'Install lightgbm=={BACKEND_VERSION} from requirements-modeling.txt')
        self.seed, self.threads = int(seed), int(threads)
        self.vocabularies = None
        self.booster = None
        self.metadata = None

    def transform(self, frame):
        if self.vocabularies is None:
            raise RuntimeError('Encoder is not fitted')
        if not frame.columns.is_unique or not set(STUFF).issubset(frame.columns):
            raise ValueError('All 11 unique Stuff columns are required')
        X = frame[STUFF].copy()
        if X.isna().any().any():
            raise ValueError('Missing Stuff features: F2 requires complete inputs; no imputation')
        for column in NUMERIC:
            if not pd.api.types.is_numeric_dtype(X[column]) or not np.isfinite(X[column].to_numpy(dtype=float)).all():
                raise ValueError(f'Non-numeric or non-finite physical feature: {column}')
            X[column] = X[column].astype(float)
        for column in CATEGORICAL:
            if not X[column].map(lambda value: isinstance(value, str)).all():
                raise ValueError(f'Categorical values must be strings: {column}')
            mapping = {value: i for i, value in enumerate(self.vocabularies[column])}
            # Unknown categories use LightGBM's missing-category branch, never an invented ordinal.
            X[column] = X[column].map(mapping).fillna(-1).astype('int32')
        return X

    def warnings(self, frame):
        self.transform(frame)
        unknown = {column: ~frame[column].isin(self.vocabularies[column]) for column in CATEGORICAL}
        return [';'.join('unknown_category:' + column for column in CATEGORICAL if unknown[column].iloc[i])
                for i in range(len(frame))]

    def fit(self, training, development, parameters, rounds=400, patience=30):
        validate_partition(training, 2024, 'train')
        validate_partition(development, 2025, 'development')
        if set(training.pitch_uid) & set(development.pitch_uid) or set(training.game_anon_id) & set(development.game_anon_id):
            raise ValueError('Training and development must be disjoint by pitch and game')
        if set(training.y_event) != set(CLASSES):
            raise ValueError('Training needs all six event classes')
        if set(parameters) != {'num_leaves', 'min_data_in_leaf', 'learning_rate', 'lambda_l2'}:
            raise ValueError('Only the declared hyperparameters may vary')
        if rounds < 1 or patience < 1 or self.threads < 1:
            raise ValueError('Rounds, patience and threads must be positive')
        training = training.sort_values('pitch_uid').reset_index(drop=True)
        development = development.sort_values('pitch_uid').reset_index(drop=True)
        self.vocabularies = {c: sorted(training[c].dropna().unique().tolist()) for c in CATEGORICAL}
        train_X, dev_X = self.transform(training), self.transform(development)
        params = dict(parameters, objective='multiclass', num_class=6, metric='multi_logloss',
                      seed=self.seed, data_random_seed=self.seed, feature_fraction_seed=self.seed,
                      bagging_seed=self.seed, deterministic=True, force_col_wise=True,
                      num_threads=self.threads, device_type='cpu', verbosity=-1,
                      feature_fraction=1.0, bagging_fraction=1.0, bagging_freq=0)
        train_data = lgb.Dataset(train_X, label=pd.Index(CLASSES).get_indexer(training.y_event),
                                 categorical_feature=CATEGORICAL, free_raw_data=False)
        dev_data = lgb.Dataset(dev_X, label=pd.Index(CLASSES).get_indexer(development.y_event),
                               reference=train_data, categorical_feature=CATEGORICAL)
        history = {}
        self.booster = lgb.train(params, train_data, num_boost_round=rounds,
                                 valid_sets=[dev_data], valid_names=['development'],
                                 callbacks=[lgb.early_stopping(patience, first_metric_only=True, verbose=False),
                                            lgb.record_evaluation(history)])
        self.metadata = {
            'schema_version': 1, 'family': 'stuff', 'backend': 'lightgbm',
            'backend_version': BACKEND_VERSION, 'features': STUFF, 'classes': list(CLASSES),
            'vocabularies': self.vocabularies, 'unknown_category_policy': 'native_missing_branch_with_warning',
            'missing_input_policy': 'reject_batch', 'seed': self.seed, 'threads': self.threads,
            'parameters': params, 'maximum_rounds': rounds, 'patience': patience,
            'best_iteration': self.booster.best_iteration, 'iterations_evaluated': len(history['development']['multi_logloss']),
            'early_stopping_partition': 'development', 'fit_year': 2024, 'fit_partition': 'train',
            'fit_rows': len(training), 'fit_ids_sha256': ids_hash(training.pitch_uid.tolist()),
            'development_rows': len(development), 'development_ids_sha256': ids_hash(development.pitch_uid.tolist()),
            'development_log_loss_history': history['development']['multi_logloss'],
        }
        return self

    def predict(self, frame):
        if self.booster is None:
            raise RuntimeError('Stuff model is not fitted')
        X = self.transform(frame)
        if frame.empty:
            return np.empty((0, 6))
        return validate_probabilities(self.booster.predict(X, num_iteration=self.metadata['best_iteration'],
                                                           num_threads=self.threads))

    def save(self, directory):
        if self.booster is None:
            raise RuntimeError('Stuff model is not fitted')
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=False)
        self.booster.save_model(str(folder / 'model.txt'), num_iteration=self.metadata['best_iteration'])
        metadata = dict(self.metadata, model_sha256=sha256_file(folder / 'model.txt'))
        (folder / 'preprocessing.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')

    @classmethod
    def load(cls, directory):
        folder = Path(directory)
        metadata = json.loads((folder / 'preprocessing.json').read_text(encoding='utf-8'))
        if (metadata['schema_version'] != 1 or metadata['features'] != STUFF or metadata['classes'] != list(CLASSES)
                or metadata['backend_version'] != BACKEND_VERSION or metadata['fit_year'] != 2024
                or metadata['fit_partition'] != 'train' or metadata['early_stopping_partition'] != 'development'
                or metadata['model_sha256'] != sha256_file(folder / 'model.txt')):
            raise ValueError('Incompatible or corrupted Stuff artifact')
        if set(metadata['vocabularies']) != set(CATEGORICAL) or any(
                not values or not all(isinstance(v, str) for v in values) or len(values) != len(set(values))
                for values in metadata['vocabularies'].values()):
            raise ValueError('Invalid saved vocabularies')
        model = cls(metadata['seed'], metadata['threads'])
        model.metadata, model.vocabularies = metadata, metadata['vocabularies']
        model.booster = lgb.Booster(model_file=str(folder / 'model.txt'))
        if model.booster.feature_name() != STUFF or model.booster.num_model_per_iteration() != 6:
            raise ValueError('Model feature/class schema mismatch')
        return model


def permutation_importance(model, development, repeats, seed):
    validate_partition(development, 2025, 'development')
    if repeats < 1:
        raise ValueError('At least one permutation required')
    frame = development.sort_values('pitch_uid').reset_index(drop=True)
    original = multiclass_metrics(frame.y_event, model.predict(frame), CLASSES)['multiclass_log_loss']
    rng = np.random.default_rng(seed)
    output = []
    for column in STUFF:
        deltas = []
        for _ in range(repeats):
            changed = frame.copy()
            changed[column] = rng.permutation(frame[column].to_numpy())
            loss = multiclass_metrics(frame.y_event, model.predict(changed), CLASSES)['multiclass_log_loss']
            deltas.append(loss - original)
        output.append({'feature': column, 'mean_log_loss_increase': float(np.mean(deltas)),
                       'std_log_loss_increase': float(np.std(deltas)), 'deltas': deltas,
                       'repeats': repeats, 'seed': seed, 'partition': 'development',
                       'n_pitches': len(frame), 'ids_sha256': ids_hash(frame.pitch_uid.tolist())})
    return sorted(output, key=lambda row: (-row['mean_log_loss_increase'], row['feature']))
