"""Reload F3 in a separate process, reproduce all models, metrics and paired comparisons."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from modeling.baselines import CLASSES, EventBaseline
from modeling.datasets import ModelingDataset, ids_hash, pd, sha256_file
from modeling.metrics import multiclass_metrics, paired_bootstrap, per_pitch_losses
from modeling.models import TabularEventModel
from modeling.phase3 import PAIRS, PROBABILITIES, family_decisions, verify_f2
from modeling.protocols import assign_pitcher_partitions


def check(experiment_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = ROOT / 'artifacts/modeling' / experiment_id / 'F3'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['status'] != 'verified' or manifest['phase_id'] != 'F3' or manifest['test_accessed']:
        raise ValueError('Not a verified sealed-test F3 run')
    for name, digest in manifest['artifact_hashes'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise ValueError('Artifact changed: ' + name)
    checks = json.loads((folder / 'checks.json').read_text(encoding='utf-8'))
    if not checks or not all(v is True for v in checks.values()):
        raise ValueError('Recorded checks failed')
    cfg = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    dataset = ModelingDataset()
    if dataset.run_id != manifest['data_run'] or dataset.manifest_hash != manifest['data_manifest_sha256']:
        raise ValueError('Data identity changed')
    reference_folder, reference = verify_f2(dataset)
    if sha256_file(reference_folder / 'manifest.json') != manifest['dependency_F2']['manifest_sha256']:
        raise ValueError('F2 dependency changed')
    cohort = dataset.load(maximum=cfg['training']['smoke_target_max_pitches'] if manifest['smoke'] else None, phase='F3')
    report = {}
    for protocol in ('A', 'B'):
        rows = cohort['aligned']['pitching']
        if protocol == 'B':
            rows = assign_pitcher_partitions(rows, cfg['F3']['protocol_B_validation_hash_seed'])
        rows = rows.sort_values('pitch_uid').reset_index(drop=True)
        saved_cohort = pd.read_parquet(folder / protocol / 'cohort.parquet')
        if not rows[saved_cohort.columns].equals(saved_cohort):
            raise ValueError('Cohort/labels/partitions changed')
        evaluation = rows.loc[rows.partition.ne('train')].reset_index(drop=True)
        training = rows.loc[rows.partition.eq('train')]
        saved = pd.read_parquet(folder / protocol / 'predictions.parquet')
        if (set(saved.model) != {'B1', 'Stuff', 'Location', 'Pitching'} or saved.duplicated(['pitch_uid', 'model']).any()
                or not saved.protocol_id.eq(protocol).all() or not saved.year.isin([2024, 2025]).all()):
            raise ValueError('Invalid prediction schema/population')
        difference = 0.0
        losses = {}
        for name in ('B1', 'Stuff', 'Location', 'Pitching'):
            predictions = saved.loc[saved.model.eq(name)].sort_values('pitch_uid').reset_index(drop=True)
            if not predictions[evaluation.columns.intersection(predictions.columns)].equals(evaluation[evaluation.columns.intersection(predictions.columns)]):
                raise ValueError('Prediction metadata or targets displaced')
            if name == 'B1':
                model = EventBaseline.load(folder / protocol / 'B1.json')
                predicted = model.predict(evaluation)[0]
                fit_hash = model.state['fit_ids_sha256']
            else:
                model = TabularEventModel.load(folder / protocol / name.lower())
                predicted = model.predict(evaluation)
                fit_hash = model.metadata['fit_ids_sha256']
            if fit_hash != ids_hash(training.pitch_uid.tolist()):
                raise ValueError('Model fit population changed')
            difference = max(difference, float(np.max(np.abs(predicted - predictions[PROBABILITIES].to_numpy()))))
            if difference > cfg['numerical_checks']['reload_prediction_atol_cpu']:
                raise ValueError('Predictions did not reproduce')
            review = predictions.loc[predictions.partition.eq('phase_review')]
            loss, _ = per_pitch_losses(review.y_event, review[PROBABILITIES].to_numpy(), CLASSES)
            losses[name] = review[['pitch_uid', 'game_anon_id', 'y_event']].assign(loss=loss)
        metrics = json.loads((folder / protocol / 'metrics.json').read_text(encoding='utf-8'))
        if len(metrics['metrics']) != 12:
            raise ValueError('Expected all 12 model/partition metric groups')
        for result in metrics['metrics']:
            group = saved.loc[saved.model.eq(result['model']) & saved.partition.eq(result['partition'])]
            reproduced = multiclass_metrics(group.y_event, group[PROBABILITIES].to_numpy(), CLASSES)
            if ids_hash(group.pitch_uid.tolist()) != result['ids_sha256'] or result['n_pitches'] != len(group):
                raise ValueError('Metric denominator changed')
            for key in ('multiclass_log_loss', 'multiclass_brier_sum_over_classes'):
                if not np.isclose(reproduced[key], result[key], atol=1e-12, rtol=0):
                    raise ValueError('Metric did not reproduce')
        comparisons = {}
        for candidate, reference_name in PAIRS:
            key = candidate + '_vs_' + reference_name
            comparisons[key] = paired_bootstrap(losses[reference_name], losses[candidate],
                cfg['evaluation']['bootstrap_smoke' if manifest['smoke'] else 'bootstrap_full'], cfg['seed'],
                cfg['evaluation']['bootstrap_confidence'], cfg['evaluation']['promotion_min_relative_log_loss_reduction'], manifest['smoke'])
            if comparisons[key] != metrics['comparisons'][key]:
                raise ValueError('Paired bootstrap did not reproduce')
        if family_decisions(comparisons, manifest['smoke']) != metrics['decision']:
            raise ValueError('Decision did not reproduce')
        report[protocol] = {'predictions_compared': len(saved), 'pitches_per_model': len(evaluation),
                            'max_abs_prediction_difference': difference, 'metric_groups_reproduced': 12,
                            'bootstrap_comparisons_reproduced': 4, 'decision': metrics['decision']}
    dataset.assert_unchanged()
    return {'status': 'verified', 'experiment_id': experiment_id, 'protocols': report,
            'artifact_files_verified': len(manifest['artifact_hashes']), 'recorded_checks_passed': len(checks),
            'test_accessed': False, 'virtual_environment': sys.prefix != sys.base_prefix}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-id', default='f3-full-check')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check(args.experiment_id)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
