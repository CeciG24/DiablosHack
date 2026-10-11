"""Scalar temperature on log probabilities; fitting is restricted to 2025 calibration."""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from modeling.datasets import ids_hash, pd, require_unique
from modeling.metrics import multiclass_metrics, validate_probabilities


class TemperatureScaler:
    def __init__(self, classes):
        self.classes = list(classes)
        if len(self.classes) < 2 or len(set(self.classes)) != len(self.classes):
            raise ValueError('At least two distinct classes required')
        self.temperature = 1.0
        self.state = None

    def transform(self, probabilities):
        p = validate_probabilities(probabilities, len(self.classes))
        if self.temperature == 1.0:
            return p.copy()
        return validate_probabilities(softmax(np.log(np.clip(p, 1e-12, 1)) / self.temperature, axis=1), len(self.classes))

    def fit(self, rows, probabilities, target):
        require_unique(rows)
        if rows.empty or not rows.year.eq(2025).all() or not rows.partition.eq('calibration').all():
            raise PermissionError('Temperature fitting requires only 2025/calibration')
        p = validate_probabilities(probabilities, len(self.classes))
        labels = pd.Index(self.classes).get_indexer(rows[target])
        if len(p) != len(rows) or (labels < 0).any():
            raise ValueError('Invalid or missing calibration labels')
        logs = np.log(np.clip(p, 1e-12, 1))
        def objective(log_temperature):
            predicted = softmax(logs / np.exp(log_temperature), axis=1)
            return float(-np.log(np.clip(predicted[np.arange(len(p)), labels], 1e-12, 1)).mean())
        optimum = minimize_scalar(objective, bounds=(np.log(.05), np.log(20.)), method='bounded', options={'xatol': 1e-8})
        if not optimum.success or not np.isfinite(optimum.fun):
            raise RuntimeError('Temperature optimization failed')
        raw_loss = multiclass_metrics(rows[target], p, self.classes)['multiclass_log_loss']
        self.temperature = float(np.exp(optimum.x)) if optimum.fun < raw_loss else 1.0
        self.state = {'schema_version': 1, 'classes': self.classes, 'temperature': self.temperature,
                      'method': 'scalar_temperature_log_probabilities', 'bounds': [.05, 20.],
                      'fit_year': 2025, 'fit_partition': 'calibration', 'target': target,
                      'fit_rows': len(rows), 'fit_ids_sha256': ids_hash(rows.pitch_uid.tolist()),
                      'raw_fit_log_loss': raw_loss, 'fitted_log_loss': min(float(optimum.fun), raw_loss)}
        return self

    def save(self, path):
        if self.state is None:
            raise RuntimeError('Unfitted scaler')
        Path(path).write_text(json.dumps(self.state, indent=2, allow_nan=False)+'\n', encoding='utf-8')

    @classmethod
    def load(cls, path):
        state = json.loads(Path(path).read_text(encoding='utf-8'))
        if (state['schema_version'] != 1 or state['fit_year'] != 2025 or state['fit_partition'] != 'calibration'
                or not np.isfinite(state['temperature']) or not .05 <= state['temperature'] <= 20.):
            raise ValueError('Invalid calibration artifact')
        model = cls(state['classes'])
        model.temperature, model.state = state['temperature'], state
        return model


def calibration_decision(raw_loss, calibrated_loss, tolerance=0.0):
    # Conservative interpretation of the contract: a harmful calibrator keeps identity.
    if not np.isfinite([raw_loss, calibrated_loss, tolerance]).all() or raw_loss <= 0 or not 0 <= tolerance <= .005:
        raise ValueError('Invalid calibration comparison')
    return 'temperature' if calibrated_loss <= raw_loss * (1 + tolerance) else 'identity'
