"""Conditional targets and fixed-budget auxiliary heads on the existing family allowlists."""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb
from modeling.datasets import duckdb, ids_hash, join_pitches, pd, sha256_file
from modeling.models import BACKEND_VERSION, TabularEventModel
from modeling.protocols import validate_fit_partition
from modeling.metrics import multiclass_metrics, validate_probabilities

HEADS = {'contact': ('weak', 'medium', 'hard'), 'groundball': ('not_groundball', 'groundball'),
         'chase': ('take', 'swing')}
TARGET_COLUMNS = ['y_hard_contact_bip', 'y_weak_contact_proxy_bip', 'y_groundball_bip', 'y_chase_given_outside']


def derive_targets(frame):
    rows = frame.copy()
    for name in TARGET_COLUMNS:
        if not rows[name].dropna().isin([0, 1]).all():
            raise ValueError('Invalid binary target: '+name)
    weak, hard = rows.y_weak_contact_proxy_bip, rows.y_hard_contact_bip
    if not weak.isna().equals(hard.isna()) or ((weak.eq(1) & hard.eq(1)).fillna(False)).any():
        raise ValueError('Inconsistent joint contact labels')
    rows['contact'] = pd.Series(pd.NA, index=rows.index, dtype='string')
    known = weak.notna() & hard.notna()
    if (known & rows.y_event.ne('in_play')).any() or (rows.y_groundball_bip.notna() & rows.y_event.ne('in_play')).any():
        raise ValueError('Contact label outside in_play')
    rows.loc[known, 'contact'] = 'medium'
    rows.loc[weak.eq(1).fillna(False), 'contact'] = 'weak'
    rows.loc[hard.eq(1).fillna(False), 'contact'] = 'hard'
    rows['groundball'] = rows.y_groundball_bip.map({0: 'not_groundball', 1: 'groundball'}).astype('string')
    rows['chase'] = rows.y_chase_given_outside.map({0: 'take', 1: 'swing'}).astype('string')
    return rows


def load_targets(dataset, rows):
    dataset.assert_unchanged()
    selected = ', '.join(['pitch_uid'] + TARGET_COLUMNS)
    with duckdb.connect(str(dataset.run / 'diablos.duckdb'), read_only=True) as db:
        labels = db.execute(f'SELECT {selected} FROM model_base WHERE year IN (2024, 2025)').df()
    result = join_pitches(rows, labels).sort_values('pitch_uid').reset_index(drop=True)
    if len(result) != len(rows):
        raise ValueError('Auxiliary target join lost pitches')
    dataset.assert_unchanged()
    return derive_targets(result)


def sample_support(rows, target, classes, minimum_rows=200, minimum_class=20):
    valid = rows.loc[rows[target].notna()]
    if not valid[target].isin(classes).all():
        raise ValueError('Unknown auxiliary class')
    counts = {c: int(valid[target].eq(c).sum()) for c in classes}
    return {'eligible_rows': len(valid), 'missing_rows': int(rows[target].isna().sum()),
            'population_rows': len(rows), 'class_counts': counts,
            'sufficient': len(valid) >= minimum_rows and min(counts.values()) >= minimum_class,
            'ids_sha256': ids_hash(valid.pitch_uid.tolist())}


class AuxiliaryModel(TabularEventModel):
    def __init__(self, family, head, seed=20260929, threads=4):
        super().__init__(seed, threads, family, 'A')
        if head not in HEADS:
            raise ValueError('Unknown head')
        self.head, self.classes = head, list(HEADS[head])

    def fit(self, training, development, parameters, rounds=400, patience=30):
        validate_fit_partition(training, 'train', 'A')
        validate_fit_partition(development, 'development', 'A')
        if (set(training.pitch_uid) & set(development.pitch_uid)
                or set(training.game_anon_id) & set(development.game_anon_id)):
            raise ValueError('Fit and development overlap')
        if set(training[self.head]) != set(self.classes) or not development[self.head].isin(self.classes).all():
            raise ValueError('Missing/invalid auxiliary targets')
        if set(parameters) != {'num_leaves', 'min_data_in_leaf', 'learning_rate', 'lambda_l2'}:
            raise ValueError('Only declared parameters allowed')
        training = training.sort_values('pitch_uid').reset_index(drop=True)
        development = development.sort_values('pitch_uid').reset_index(drop=True)
        self.vocabularies = {c: sorted(training[c].dropna().unique().tolist()) for c in self.categorical}
        params = dict(parameters, objective='multiclass', num_class=len(self.classes), metric='multi_logloss',
                      seed=self.seed, data_random_seed=self.seed, feature_fraction_seed=self.seed, bagging_seed=self.seed,
                      deterministic=True, force_col_wise=True, num_threads=self.threads, device_type='cpu', verbosity=-1)
        train_data = lgb.Dataset(self.transform(training), label=pd.Index(self.classes).get_indexer(training[self.head]), categorical_feature=self.categorical)
        dev_data = lgb.Dataset(self.transform(development), label=pd.Index(self.classes).get_indexer(development[self.head]),
                              reference=train_data, categorical_feature=self.categorical)
        history = {}
        self.booster = lgb.train(params, train_data, num_boost_round=rounds, valid_sets=[dev_data], valid_names=['development'],
            callbacks=[lgb.early_stopping(patience, verbose=False), lgb.record_evaluation(history)])
        self.metadata = {'schema_version': 1, 'family': self.family, 'head': self.head, 'classes': self.classes,
                         'backend_version': BACKEND_VERSION, 'protocol_id': 'A', 'features': self.features,
                         'vocabularies': self.vocabularies, 'seed': self.seed, 'threads': self.threads,
                         'fit_year': 2024, 'fit_partition': 'train', 'fit_rows': len(training),
                         'fit_ids_sha256': ids_hash(training.pitch_uid.tolist()), 'development_rows': len(development),
                         'development_ids_sha256': ids_hash(development.pitch_uid.tolist()),
                         'early_stopping_partition': 'development', 'parameters': parameters,
                         'maximum_rounds': rounds, 'patience': patience, 'best_iteration': self.booster.best_iteration,
                         'development_log_loss_history': history['development']['multi_logloss'],
                         'missing_input_policy': 'reject_batch', 'unknown_category_policy': 'native_missing_branch_with_warning'}
        return self

    def predict(self, frame):
        if self.booster is None:
            raise RuntimeError('Unfitted auxiliary model')
        X = self.transform(frame)
        if frame.empty:
            return np.empty((0, len(self.classes)))
        return validate_probabilities(self.booster.predict(X, num_iteration=self.metadata['best_iteration'], num_threads=self.threads), len(self.classes))

    @classmethod
    def load(cls, directory):
        folder = Path(directory)
        meta = json.loads((folder / 'preprocessing.json').read_text(encoding='utf-8'))
        model = cls(meta['family'], meta['head'], meta['seed'], meta['threads'])
        if (meta['schema_version'] != 1 or meta['classes'] != model.classes or meta['features'] != model.features
                or meta['backend_version'] != BACKEND_VERSION or meta['protocol_id'] != 'A'
                or meta['fit_year'] != 2024 or meta['fit_partition'] != 'train' or meta['early_stopping_partition'] != 'development'
                or meta['model_sha256'] != sha256_file(folder / 'model.txt') or set(meta['vocabularies']) != set(model.categorical)):
            raise ValueError('Invalid auxiliary artifact')
        model.metadata, model.vocabularies = meta, meta['vocabularies']
        model.booster = lgb.Booster(model_file=str(folder / 'model.txt'))
        if model.booster.feature_name() != model.features or model.booster.num_model_per_iteration() != len(model.classes):
            raise ValueError('Auxiliary schema mismatch')
        return model


def smoothed_prevalence(training, target, classes):
    validate_fit_partition(training, 'train', 'A')
    if not training[target].isin(classes).all():
        raise ValueError('Invalid prevalence labels')
    counts = training[target].value_counts().reindex(classes, fill_value=0).to_numpy(dtype=float)
    return (counts + 1) / (len(training) + len(classes))


def average_precision(labels, scores):
    """Step PR-AUC (average precision), thresholds grouped to handle ties fairly."""
    y, p = np.asarray(labels, dtype=int), np.asarray(scores, dtype=float)
    if len(y) == 0 or y.sum() == 0:
        return None
    order = np.argsort(-p, kind='stable')
    y, p = y[order], p[order]
    end = np.r_[np.flatnonzero(p[:-1] != p[1:]), len(p)-1]
    positives = np.cumsum(y)[end]
    return float(np.sum(np.diff(np.r_[0, positives]) / y.sum() * positives / (end + 1)))


def head_metrics(labels, probabilities, classes):
    result = multiclass_metrics(labels, probabilities, classes)
    for i, label in enumerate(classes):
        truth = (np.asarray(labels) == label).astype(float)
        result['binary_' + label] = {'brier': float(np.mean((probabilities[:, i] - truth)**2)),
            'log_loss': float(np.mean(-truth*np.log(np.clip(probabilities[:, i], 1e-12, 1))
                                      -(1-truth)*np.log(np.clip(1-probabilities[:, i], 1e-12, 1)))),
            'pr_auc_average_precision': average_precision(truth, probabilities[:, i])}
    return result


def joint_contact_probabilities(event_probabilities, conditional_probabilities):
    event = validate_probabilities(event_probabilities, 6)
    conditional = validate_probabilities(conditional_probabilities, 3)
    if len(event) != len(conditional):
        raise ValueError('Mismatched populations')
    return event[:, 4, None] * conditional
