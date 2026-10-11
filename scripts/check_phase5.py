"""Independent F5 reference, model, policy, calibration and metric reproduction."""
import argparse
import json
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from modeling.arsenal import ArsenalEventModel, build_reference, route_probabilities, predict_policy
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler, calibration_decision
from modeling.datasets import ModelingDataset, ids_hash, pd, sha256_file
from modeling.metrics import multiclass_metrics
from modeling.phase4 import compare_head
from modeling.phase5 import load_history, load_c_rows, verify_f4
from scripts.check_phase4 import assert_same


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def check(experiment):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment):
        raise ValueError('Invalid experiment')
    dataset = ModelingDataset()
    verify_f4(dataset)
    folder = ROOT/'artifacts/modeling'/experiment/'F5'
    manifest, cfg = read(folder/'manifest.json'), read(folder/'config.json')
    assert manifest['status'] == 'verified' and not manifest['test_accessed']
    assert manifest['data_manifest_sha256'] == dataset.manifest_hash
    for name, digest in manifest['artifact_hashes'].items():
        path = (folder/name).resolve()
        assert path.is_relative_to(folder.resolve()) and sha256_file(path) == digest, name
    for name, digest in manifest['code_hashes'].items():
        assert sha256_file(ROOT/name) == digest, name
    checks = read(folder/'checks.json')
    assert checks and all(v is True for v in checks.values())
    history = load_history(dataset)
    reference_manifest = read(folder/'reference_2024/manifest.json')
    assert ids_hash(history.pitch_uid.tolist()) == reference_manifest['source_ids_sha256']
    reference = build_reference(history, reference_manifest['minimum_fastball_reference'], reference_manifest['fastball_types'])
    for name, table in zip(('fastballs', 'type_counts', 'pitcher_counts'), reference):
        pd.testing.assert_frame_equal(table, pd.read_parquet(folder/'reference_2024'/(name+'.parquet')))
    rows, _ = load_c_rows(dataset, manifest['smoke'], reference)
    pd.testing.assert_frame_equal(rows, pd.read_parquet(folder/'cohort.parquet'))
    evaluation = rows.loc[rows.partition.ne('development')].reset_index(drop=True)
    covered = evaluation.loc[evaluation.has_reference].reset_index(drop=True)
    policy = read(folder/'policy.json')
    selected = {}
    for name in (('fallback', 'control', 'arsenal') if policy['available'] else ('fallback',)):
        frame = evaluation if name == 'fallback' else covered
        training = rows.loc[rows.partition.eq('development') & (True if name == 'fallback' else rows.has_reference)]
        model = ArsenalEventModel.load(folder/name/'model')
        assert model.metadata['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
        raw = model.predict(frame)
        predictions = pd.read_parquet(folder/name/'predictions.parquet')
        np.testing.assert_array_equal(raw, predictions[['raw_'+c for c in CLASSES]].to_numpy())
        calibration = read(folder/name/'calibration_policy.json')
        candidate = raw.copy()
        cal = frame.partition.eq('calibration').to_numpy()
        review = frame.partition.eq('phase_review').to_numpy()
        if calibration['fit_status'] == 'fitted':
            scaler = TemperatureScaler(CLASSES).fit(frame.loc[cal], raw[cal], 'y_event')
            saved = TemperatureScaler.load(folder/name/'temperature.json')
            assert_same(scaler.state, saved.state)
            candidate = saved.transform(raw)
        np.testing.assert_array_equal(candidate, predictions[['temperature_'+c for c in CLASSES]].to_numpy())
        if calibration['fit_status'] == 'fitted' and calibration['review_support']['sufficient']:
            route = calibration_decision(multiclass_metrics(frame.loc[review, 'y_event'], raw[review], CLASSES)['multiclass_log_loss'],
                multiclass_metrics(frame.loc[review, 'y_event'], candidate[review], CLASSES)['multiclass_log_loss'])
            assert route == calibration['route']
        selected[name] = candidate if calibration['route'] == 'temperature' else raw
        np.testing.assert_array_equal(selected[name], predictions[['selected_'+c for c in CLASSES]].to_numpy())
    base = selected['fallback']
    control = selected.get('control', base[evaluation.has_reference])
    arsenal = selected.get('arsenal', control)
    reference_policy, _ = route_probabilities(base, control, arsenal, evaluation.has_reference, False)
    candidate_policy, _ = route_probabilities(base, control, arsenal, evaluation.has_reference, True)
    public, routes = route_probabilities(base, control, arsenal, evaluation.has_reference, policy['promote_arsenal'])
    if not policy['available']:
        routes[:] = 'fallback'
    output = pd.read_parquet(folder/'predictions.parquet')
    assert output.pitch_uid.tolist() == evaluation.pitch_uid.tolist()
    assert output.route.tolist() == routes.tolist()
    from modeling.datasets import PITCHING
    inputs = evaluation[['pitch_uid', 'year', 'pitcher_anon_id']+PITCHING]
    replay = predict_policy(folder, inputs)
    np.testing.assert_array_equal(replay[['p_'+c for c in CLASSES]].to_numpy(), public)
    assert replay.route.tolist() == routes.tolist()
    cold = predict_policy(folder, inputs.head(100), cold_start=True)
    np.testing.assert_array_equal(cold[['p_'+c for c in CLASSES]].to_numpy(), base[:len(cold)])
    assert cold.route.eq('fallback').all()
    for name, matrix in (('full_base', base), ('control_policy', reference_policy), ('candidate_policy', candidate_policy), ('selected', public)):
        np.testing.assert_array_equal(matrix, output[[name+'_'+c for c in CLASSES]].to_numpy())
    result = read(folder/'metrics.json')
    for metric in result['metrics']:
        matrix = dict(full_base=base, control_policy=reference_policy, candidate_policy=candidate_policy, selected_policy=public)[metric['model']]
        mask = evaluation.partition.eq(metric['partition']).to_numpy()
        reproduced = multiclass_metrics(evaluation.loc[mask, 'y_event'], matrix[mask], CLASSES)
        assert_same(reproduced, {k: metric[k] for k in reproduced})
    if policy['available']:
        mask = covered.partition.eq('phase_review').to_numpy()
        paired = compare_head(covered.loc[mask], 'y_event', CLASSES, control[mask], arsenal[mask], cfg, manifest['smoke'])
        assert_same(paired, result['paired_arsenal'])
        assert policy['promote_arsenal'] == (paired['decision'] == 'promote')
        mask = evaluation.partition.eq('phase_review').to_numpy()
        assert_same(compare_head(evaluation.loc[mask], 'y_event', CLASSES, reference_policy[mask], candidate_policy[mask], cfg, manifest['smoke']), result['full_policy_comparison'])
    dataset.assert_unchanged()
    return dict(experiment=experiment, status='verified', checks_passed=len(checks), artifact_hashes_verified=len(manifest['artifact_hashes']),
                prediction_rows=len(output), max_prediction_difference=0.0, metrics_reproduced=len(result['metrics']),
                reference_rebuilt_from_2024=True, test_accessed=False, scientific_decision=result['scientific_decision'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check(args.experiment)
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text)
