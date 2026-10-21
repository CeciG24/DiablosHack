"""Versioned combined event score; the frozen F8 families remain unchanged."""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from experiments.phase10_features import REGULARIZED, Repertoire
from experiments.phase9_predict import verify_experiment
from modeling.arsenal import ArsenalEventModel
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler
from modeling.datasets import PITCHING, sha256_file
from modeling.models import BACKEND_VERSION

VERSION = 'F11_physics_location_arsenal_context_event_utility_v1'
WEIGHTS = np.array([-.5, 1., 1., 0., 0., -1.])


class CombinedEventModel(ArsenalEventModel):
    """Protocol C, fixed budget: location and observed context are NOT removed."""
    def __init__(self, seed=20260929, threads=4):
        super().__init__(True, seed, threads)
        self.features = PITCHING.copy() + REGULARIZED
        self.numeric = [c for c in self.features if c not in self.categorical]

    @classmethod
    def load(cls, directory):
        folder = Path(directory)
        metadata = json.loads((folder/'preprocessing.json').read_text(encoding='utf-8'))
        model = cls(metadata['seed'], metadata['threads'])
        if (metadata['features'] != model.features or metadata['classes'] != list(CLASSES)
                or metadata['protocol_id'] != 'C' or metadata['fit_year'] != 2025
                or metadata['fit_partition'] != 'development' or not metadata['with_arsenal']
                or metadata['backend_version'] != BACKEND_VERSION
                or metadata['model_sha256'] != sha256_file(folder/'model.txt')):
            raise ValueError('Invalid combined model artifact')
        model.metadata, model.vocabularies = metadata, metadata['vocabularies']
        model.booster = lgb.Booster(model_file=str(folder/'model.txt'))
        if model.booster.feature_name() != model.features or model.booster.num_model_per_iteration() != 6:
            raise ValueError('Combined model schema mismatch')
        return model


class FinalScorePredictor:
    """Outcome-free inference with fixed 2024 history and a separate 2025 scale."""
    def __init__(self, directory):
        folder = Path(directory)
        self.manifest = verify_experiment(folder)
        self.model = CombinedEventModel.load(folder/'combined/model')
        self.scaler = TemperatureScaler.load(folder/'combined/temperature.json')
        self.repertoire = Repertoire.load(folder/'repertoire')
        self.scale = json.loads((folder/'scale.json').read_text(encoding='utf-8'))
        self.bounds = json.loads((folder/'input_bounds.json').read_text(encoding='utf-8'))
        if (self.scale['version'] != VERSION or self.scale['weights'] != WEIGHTS.tolist()
                or not np.isfinite([self.scale['mu'], self.scale['sigma']]).all()
                or self.scale['sigma'] <= 1e-12 or self.scale['reference_n'] < 1):
            raise ValueError('Invalid final-score reference')
        self.model_id = sha256_file(folder/'manifest.json')

    def records(self, records):
        output, valid, indices = [], [], []
        for record in records:
            result = dict(pitch_uid=record.get('pitch_uid'), status='invalid_input',
                          score=None, probabilities=None, score_version=VERSION,
                          model_id=self.model_id, experimental=True, represents_runs=False,
                          history_status=None, history_n=0, warnings='',
                          context_mode='observed_location_count_batter_side',
                          auxiliary_targets_in_score=False)
            output.append(result)
            try:
                # Only allowlisted features reach inference; supplied arsenal/outcomes are ignored.
                row = {c: record[c] for c in PITCHING}
                for column in self.model.categorical:
                    if not isinstance(row[column], str) or not row[column].strip():
                        raise ValueError('Invalid '+column)
                if row['pitcher_throws'] not in ('Left', 'Right') or row['batter_side'] not in ('Left', 'Right'):
                    raise ValueError('Unknown hand')
                for column in (c for c in PITCHING if c not in self.model.categorical):
                    value = row[column]
                    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)) or not np.isfinite(value):
                        raise ValueError('Missing or invalid '+column)
                    if column in self.bounds and not self.bounds[column][0] <= value <= self.bounds[column][1]:
                        raise ValueError('Out of range '+column)
                if not (0 <= row['balls'] <= 3 and row['balls'] % 1 == 0
                        and 0 <= row['strikes'] <= 2 and row['strikes'] % 1 == 0):
                    raise ValueError('Invalid count')
                if (abs(row['spin_axis_sin']) > 1 or abs(row['spin_axis_cos']) > 1
                        or not np.isclose(row['spin_axis_sin']**2 + row['spin_axis_cos']**2, 1, atol=.02)):
                    raise ValueError('Invalid spin axis')
                row['pitcher_anon_id'] = record.get('pitcher_anon_id')
                valid.append(row)
                indices.append(len(output)-1)
            except (KeyError, ValueError, TypeError) as error:
                result['warnings'] = str(error)
        if valid:
            prepared = self.repertoire.transform(pd.DataFrame(valid))
            probabilities = self.scaler.transform(self.model.predict(prepared))
            scores = 100 + 10 * (probabilities @ WEIGHTS - self.scale['mu']) / self.scale['sigma']
            for j, (index, warning) in enumerate(zip(indices, self.model.warnings(prepared))):
                history = prepared.history_status.iloc[j]
                output[index].update(status='experimental', score=float(scores[j]),
                    probabilities=dict(zip(CLASSES, probabilities[j].tolist())),
                    history_status=history, history_n=int(prepared.history_n.iloc[j]),
                    warnings=';'.join(filter(None, [warning, 'group_prior_only' if history == 'group_prior_only' else ''])))
        return output
