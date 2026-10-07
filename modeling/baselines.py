"""F1 event-frequency baselines. No fitting outside the 2024 train partition."""
import json
from pathlib import Path

from modeling.datasets import ids_hash, pd, require_unique
import numpy as np

CLASSES = ('ball', 'called_strike', 'whiff', 'foul', 'in_play', 'hit_by_pitch')
GROUPS = {'B0': [], 'B1': ['balls', 'strikes'],
          'B2': ['balls', 'strikes', 'auto_pitch_type']}


class EventBaseline:
    def __init__(self, name, classes=CLASSES, pseudocount=1.0, strength=20.0):
        if name not in GROUPS or tuple(classes) != CLASSES:
            raise ValueError('Unknown baseline or event class order')
        if not np.isfinite([pseudocount, strength]).all() or min(pseudocount, strength) <= 0:
            raise ValueError('Smoothing parameters must be finite and positive')
        self.name, self.classes = name, list(classes)
        self.pseudocount, self.strength = float(pseudocount), float(strength)
        self.columns = GROUPS[name].copy()
        self.state = None

    def _context(self, frame, fitting=False):
        if not set(self.columns).issubset(frame.columns):
            raise ValueError(f'{self.name} requires {self.columns}')
        for column, upper in (('balls', 3), ('strikes', 2)):
            if column in self.columns:
                values = frame[column].dropna()
                if not pd.api.types.is_numeric_dtype(values) or not (values.between(0, upper) & values.mod(1).eq(0)).all():
                    raise ValueError(f'Invalid {column}')
        if fitting and frame[self.columns].isna().any().any():
            raise ValueError('Training context cannot be missing')

    @staticmethod
    def _key(values):
        # JSON is unambiguous even if pitch types contain punctuation.
        if any(pd.isna(value) for value in values):
            return None
        return json.dumps([str(value) if i == 2 else int(value)
                           for i, value in enumerate(values)], ensure_ascii=False,
                          separators=(',', ':'))

    def fit(self, frame):
        require_unique(frame)
        if frame.empty or not frame.year.eq(2024).all() or not frame.partition.eq('train').all():
            raise PermissionError('Baseline fit requires nonempty 2024/train rows only')
        if frame.y_event.isna().any() or not frame.y_event.isin(self.classes).all():
            raise ValueError('Missing or unknown training target')
        self._context(frame, fitting=True)
        counts = frame.y_event.value_counts().reindex(self.classes, fill_value=0).to_numpy(dtype=int)
        groups = {}
        if self.columns:
            for key, rows in frame.groupby(self.columns, sort=True, observed=True):
                groups[self._key(key)] = rows.y_event.value_counts().reindex(self.classes, fill_value=0).astype(int).tolist()
        self.state = {
            'schema_version': 1, 'name': self.name, 'classes': self.classes,
            'features': self.columns, 'pseudocount': self.pseudocount,
            'prior_strength': self.strength, 'fallback': 'global_B0',
            'fit_year': 2024, 'fit_partition': 'train', 'fit_rows': len(frame),
            'fit_ids_sha256': ids_hash(frame.pitch_uid.tolist()),
            'global_counts': counts.tolist(), 'group_counts': groups,
        }
        return self

    @property
    def global_probabilities(self):
        if self.state is None:
            raise RuntimeError('Model has not been fitted')
        counts = np.asarray(self.state['global_counts'], dtype=float)
        return (counts + self.pseudocount) / (counts.sum() + len(self.classes) * self.pseudocount)

    def predict(self, frame):
        self._context(frame)
        global_p = self.global_probabilities
        probabilities = np.tile(global_p, (len(frame), 1))
        routes = np.full(len(frame), 'global' if not self.columns else 'fallback_global', dtype=object)
        if self.columns:
            lookup = {}
            for key, values in self.state['group_counts'].items():
                counts = np.asarray(values, dtype=float)
                lookup[key] = (counts + self.strength * global_p) / (counts.sum() + self.strength)
            for i, values in enumerate(frame[self.columns].itertuples(index=False, name=None)):
                key = self._key(values)
                if key in lookup:
                    probabilities[i] = lookup[key]
                    routes[i] = 'group'
        return probabilities, routes

    def save(self, path):
        if self.state is None:
            raise RuntimeError('Model has not been fitted')
        Path(path).write_text(json.dumps(self.state, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')

    @classmethod
    def load(cls, path):
        state = json.loads(Path(path).read_text(encoding='utf-8'))
        model = cls(state['name'], state['classes'], state['pseudocount'], state['prior_strength'])
        if state['schema_version'] != 1 or state['features'] != model.columns or state['fallback'] != 'global_B0':
            raise ValueError('Invalid baseline schema')
        if state['fit_year'] != 2024 or state['fit_partition'] != 'train' or state['fit_rows'] <= 0:
            raise ValueError('Invalid training provenance')
        counts = np.asarray(state['global_counts'])
        if counts.shape != (6,) or not np.isfinite(counts).all() or (counts < 0).any() or (counts % 1 != 0).any() or counts.sum() != state['fit_rows']:
            raise ValueError('Invalid global counts')
        total = np.zeros(6, dtype=int)
        for key, values in state['group_counts'].items():
            if not model.columns or len(json.loads(key)) != len(model.columns):
                raise ValueError('Invalid group key')
            group = np.asarray(values)
            if group.shape != (6,) or not np.isfinite(group).all() or (group < 0).any() or (group % 1 != 0).any() or group.sum() <= 0:
                raise ValueError('Invalid group counts')
            total += group.astype(int)
        if model.columns and not np.array_equal(total, counts):
            raise ValueError('Group counts do not match training counts')
        model.state = state
        return model
