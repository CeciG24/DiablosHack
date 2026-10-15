"""F9 candidate: physical Stuff with deterministic derived features and train-fit z-scores."""
import numpy as np

from modeling.baselines import CLASSES
from modeling.datasets import STUFF, ids_hash, pd
from modeling.metrics import multiclass_metrics, validate_probabilities
from modeling.models import CATEGORICAL, TabularEventModel, validate_partition
from modeling.protocols import validate_fit_partition

DERIVATION_ID = 'stuff_v2_derived_physical_v1'
# Same-row deterministic transforms of the allowlisted physical columns.
DERIVED = ['bauer_units', 'break_magnitude', 'break_angle', 'axis_angle',
           'release_slope_v', 'release_slope_h']
# Train-only z-scores within auto_pitch_type (global fallback for unseen types).
Z_SOURCES = ['rel_speed', 'spin_rate', 'induced_vert_break', 'horz_break']
Z_FEATURES = ['z_' + column for column in Z_SOURCES]
STUFF_V2 = STUFF + DERIVED + Z_FEATURES
EPSILON = 1e-12


def derive_local(frame):
    missing = [c for c in STUFF if c not in frame.columns]
    if missing:
        raise ValueError('Missing physical source columns: ' + ','.join(missing))
    out = frame.copy()
    for column in ('rel_speed', 'spin_rate', 'spin_axis_sin', 'spin_axis_cos',
                   'rel_height', 'rel_side', 'extension', 'induced_vert_break', 'horz_break'):
        out[column] = pd.to_numeric(out[column], errors='coerce')
    out['bauer_units'] = out.spin_rate / out.rel_speed
    out['break_magnitude'] = np.hypot(out.induced_vert_break, out.horz_break)
    out['break_angle'] = np.arctan2(out.induced_vert_break, out.horz_break)
    out['axis_angle'] = np.arctan2(out.spin_axis_sin, out.spin_axis_cos)
    out['release_slope_v'] = out.rel_height / out.extension
    out['release_slope_h'] = out.rel_side / out.extension
    return out


def fit_group_stats(training):
    stats = {}
    for column in Z_SOURCES:
        values = training[column].to_numpy(dtype=float)
        stats[column] = {
            'global': [float(values.mean()), float(values.std())],
            'by_type': {str(t): [float(g[column].mean()), float(g[column].to_numpy(dtype=float).std())]
                        for t, g in training.groupby('auto_pitch_type')},
        }
    return stats


def augment(frame, group_stats):
    out = derive_local(frame)
    for source, target in zip(Z_SOURCES, Z_FEATURES):
        stats = group_stats[source]
        lookup = pd.DataFrame(
            [(t, v[0], v[1]) for t, v in stats['by_type'].items()],
            columns=['auto_pitch_type', '_m', '_s'])
        joined = out[['auto_pitch_type']].merge(
            lookup, on='auto_pitch_type', how='left', validate='many_to_one')
        mean = joined['_m'].fillna(stats['global'][0]).to_numpy()
        std = np.maximum(joined['_s'].fillna(stats['global'][1]).to_numpy(), EPSILON)
        out[target] = (out[source].to_numpy(dtype=float) - mean) / std
    return out


class StuffV2Model(TabularEventModel):
    """Physical-only family with derived features; same fit/selection partitions as F2."""

    def __init__(self, seed=20260929, threads=4, family='stuff', protocol='A'):
        if family != 'stuff':
            raise ValueError('StuffV2 cannot accept contextual features')
        super().__init__(seed, threads, family, protocol)
        self.features = list(STUFF_V2)
        self.categorical = [c for c in self.features if c in CATEGORICAL]
        self.numeric = [c for c in self.features if c not in self.categorical]
        self.group_stats = None

    def transform(self, frame):
        if self.group_stats is None:
            raise RuntimeError('Group statistics are not fitted')
        return super().transform(augment(frame, self.group_stats))

    def fit(self, training, development, parameters, rounds=800, patience=40):
        validate_fit_partition(training, 'train', self.protocol)
        self.group_stats = fit_group_stats(training)
        super().fit(training, development, parameters, rounds, patience)
        self.metadata['group_stats'] = self.group_stats
        self.metadata['feature_derivation'] = DERIVATION_ID
        self.metadata['post_release_development'] = True
        return self

    @classmethod
    def load(cls, directory):
        model = super().load(directory)
        if model.metadata.get('feature_derivation') != DERIVATION_ID:
            raise ValueError('Not a StuffV2 artifact')
        model.group_stats = model.metadata['group_stats']
        return model


def permutation_importance_v2(model, development, repeats, seed):
    """Permute the already-derived feature matrix: measures reliance on every feature."""
    validate_partition(development, 2025, 'development')
    if repeats < 1:
        raise ValueError('At least one permutation required')
    frame = development.sort_values('pitch_uid').reset_index(drop=True)
    original = multiclass_metrics(frame.y_event, model.predict(frame), CLASSES)['multiclass_log_loss']
    encoded = model.transform(frame)
    rng = np.random.default_rng(seed)
    output = []
    for column in model.features:
        deltas = []
        for _ in range(repeats):
            changed = encoded.copy()
            changed[column] = rng.permutation(changed[column].to_numpy())
            p = model.booster.predict(changed, num_iteration=model.metadata['best_iteration'],
                                      num_threads=model.threads)
            loss = multiclass_metrics(frame.y_event, validate_probabilities(p), CLASSES)['multiclass_log_loss']
            deltas.append(loss - original)
        output.append({'feature': column, 'mean_log_loss_increase': float(np.mean(deltas)),
                       'std_log_loss_increase': float(np.std(deltas)), 'deltas': deltas,
                       'repeats': repeats, 'seed': seed, 'partition': 'development',
                       'space': 'derived_feature_matrix', 'n_pitches': len(frame),
                       'ids_sha256': ids_hash(frame.pitch_uid.tolist())})
    return sorted(output, key=lambda row: (-row['mean_log_loss_increase'], row['feature']))
