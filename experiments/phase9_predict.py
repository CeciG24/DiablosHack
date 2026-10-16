"""Outcome-free batch inference for the explicitly experimental F9 index."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from experiments.phase9 import (ExperimentModel, engineer, standardized_probabilities, UTILITY,
                                PROBS, write)
from modeling.calibration import TemperatureScaler
from modeling.datasets import ROOT, sha256_file


def verify_experiment(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['artifacts'].items():
        path = (folder/name).resolve()
        if not path.is_relative_to(folder) or sha256_file(path) != expected:
            raise ValueError('Experiment artifact changed: '+name)
    return manifest


class ExperimentalPredictor:
    """Does not change the production F8 server or accept outcome-derived inputs."""
    def __init__(self, folder):
        folder = Path(folder)
        self.manifest = verify_experiment(folder)
        self.model = ExperimentModel.load(folder/'A/context_physics/model')
        self.scaler = TemperatureScaler.load(folder/'A/context_physics/temperature.json')
        self.distribution = json.loads((folder/'context_distribution.json').read_text(encoding='utf-8'))
        self.scale = json.loads((folder/'scale.json').read_text(encoding='utf-8'))
        if (self.scale['distribution_sha256'] != sha256_file(folder/'context_distribution.json')
                or not np.isfinite([self.scale['mu'], self.scale['sigma']]).all()
                or self.scale['sigma'] <= 1e-12 or self.scale['weights'] != UTILITY.tolist()):
            raise ValueError('Invalid score reference')
        self.bounds = json.loads((ROOT/'config/data_contract.json').read_text(encoding='utf-8'))['physical_review_bounds']

    def predict(self, records):
        output = []
        valid_rows, valid_indices = [], []
        for record in records:
            result = dict(pitch_uid=record.get('pitch_uid'), status='experimental',
                          score_version=self.scale['version'], score=None, probabilities=None,
                          reference_n=self.scale['reference_n'], represents_runs=False)
            try:
                row = pd.DataFrame([record])
                # Context is integrated out; callers need only original physical inputs.
                row = row.assign(balls=0, strikes=0, batter_side='Right')
                for field, limits in self.bounds.items():
                    if field in row and (not np.isfinite(float(row[field].iloc[0])) or not limits[0] <= float(row[field].iloc[0]) <= limits[1]):
                        raise ValueError('Out-of-range '+field)
                for field in ('spin_axis_sin', 'spin_axis_cos'):
                    if not -1 <= float(row[field].iloc[0]) <= 1:
                        raise ValueError('Invalid '+field)
                row = engineer(row)
                self.model.transform(row)
                valid_rows.append(row)
                valid_indices.append(len(output))
            except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as error:
                result.update(status='invalid_input', warnings=str(error))
            output.append(result)
        if valid_rows:
            batch = pd.concat(valid_rows, ignore_index=True)
            probabilities = standardized_probabilities(self.model, self.scaler, batch, self.distribution)
            warnings = self.model.warnings(batch)
            for index, p, warning in zip(valid_indices, probabilities, warnings):
                output[index]['score'] = float(100+10*(p@UTILITY-self.scale['mu'])/self.scale['sigma'])
                output[index]['probabilities'] = dict(zip(PROBS, p.tolist()))
                output[index]['warnings'] = warning
        return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(destination)
    records = json.loads(Path(args.input).read_text(encoding='utf-8'))
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError('Expected a JSON array of pitch objects')
    result = ExperimentalPredictor(args.experiment).predict(records)
    write(destination, result)
