"""Independently reload a completed F2 run and verify probabilities and metrics."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modeling.datasets import ModelingDataset, ids_hash, join_pitches, pd, sha256_file
from modeling.baselines import CLASSES
from modeling.metrics import multiclass_metrics, paired_bootstrap, per_pitch_losses
from modeling.models import StuffModel
import numpy as np


def check(experiment_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = ROOT / 'artifacts/modeling' / experiment_id / 'F2'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['status'] != 'verified' or manifest['phase_id'] != 'F2' or manifest['test_accessed']:
        raise ValueError('Not a verified sealed-test F2 experiment')
    for name, digest in manifest['artifact_hashes'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise ValueError(f'Artifact integrity failure: {name}')
    checks = json.loads((folder / 'checks.json').read_text(encoding='utf-8'))
    if not checks or not all(value is True for value in checks.values()):
        raise ValueError('Failed recorded checks')
    cfg = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    if sha256_file(folder / 'config.json') != manifest['artifact_hashes']['config.json']:
        raise ValueError('Invalid configuration snapshot')
    dataset = ModelingDataset()
    if dataset.run_id != manifest['data_run'] or dataset.manifest_hash != manifest['data_manifest_sha256']:
        raise ValueError('Data run changed')
    cohort = dataset.load(maximum=cfg['training']['smoke_target_max_pitches'] if manifest['smoke'] else None, phase='F2')
    rows = cohort['aligned']['stuff']
    if ids_hash(rows.pitch_uid.tolist()) != manifest['cohort']['common_ids_sha256']:
        raise ValueError('Cohort changed')
    evaluation = rows.loc[rows.partition.ne('train')]
    saved = pd.read_parquet(folder / 'predictions.parquet')
    if not saved.year.eq(2025).all() or saved.duplicated(['pitch_uid', 'model']).any():
        raise ValueError('Invalid prediction population')
    if set(saved.model) != {'B0', 'B1', 'Stuff'}:
        raise ValueError('Invalid prediction model list')
    columns = ['p_' + c for c in CLASSES]
    fitted = StuffModel.load(folder / 'stuff')
    probabilities = fitted.predict(evaluation)
    aligned = join_pitches(evaluation[['pitch_uid']], saved.loc[saved.model.eq('Stuff'), ['pitch_uid']+columns])
    if len(aligned) != len(evaluation):
        raise ValueError('Prediction IDs changed')
    delta = float(np.max(np.abs(probabilities - aligned[columns].to_numpy())))
    if delta > cfg['numerical_checks']['reload_prediction_atol_cpu']:
        raise ValueError('Independent reload exceeds tolerance')
    metrics = json.loads((folder / 'metrics.json').read_text(encoding='utf-8'))
    for result in metrics['metrics']:
        subset = saved.loc[saved.model.eq(result['model']) & saved.partition.eq(result['partition'])]
        recomputed = multiclass_metrics(subset.y_event, subset[columns].to_numpy(), CLASSES,
                                       cfg['numerical_checks']['log_loss_clipping_epsilon'])
        if len(subset) != result['n_pitches'] or ids_hash(subset.pitch_uid.tolist()) != result['ids_sha256']:
            raise ValueError('Metric population mismatch')
        for key in ('multiclass_log_loss', 'multiclass_brier_sum_over_classes'):
            if not np.isclose(result[key], recomputed[key], atol=1e-12, rtol=0):
                raise ValueError('Metrics did not reproduce')
    losses = {}
    for name in ('B0', 'B1', 'Stuff'):
        subset = saved.loc[saved.model.eq(name) & saved.partition.eq('phase_review')]
        loss, _ = per_pitch_losses(subset.y_event, subset[columns].to_numpy(), CLASSES)
        losses[name] = subset[['pitch_uid', 'game_anon_id', 'y_event']].assign(loss=loss)
    for baseline in ('B0', 'B1'):
        result = paired_bootstrap(losses[baseline], losses['Stuff'], cfg['evaluation']['bootstrap_smoke' if manifest['smoke'] else 'bootstrap_full'],
                                  cfg['seed'], cfg['evaluation']['bootstrap_confidence'],
                                  cfg['evaluation']['promotion_min_relative_log_loss_reduction'], manifest['smoke'])
        if result != metrics['comparisons']['Stuff_vs_' + baseline]:
            raise ValueError('Bootstrap did not reproduce')
    dataset.assert_unchanged()
    return {'status': 'verified', 'experiment_id': experiment_id, 'independent_process_reload': True,
            'max_abs_prediction_difference': delta, 'predictions_compared': len(evaluation),
            'metric_groups_reproduced': len(metrics['metrics']), 'bootstrap_comparisons_reproduced': 2,
            'artifact_files_verified': len(manifest['artifact_hashes']), 'recorded_checks_passed': len(checks),
            'test_accessed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-id', default='f2-full-check')
    print(json.dumps(check(parser.parse_args().experiment_id), indent=2))
