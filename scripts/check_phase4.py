"""Independently reproduce F4 saved probabilities, temperatures, metrics and decisions."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler, calibration_decision
from modeling.contact import HEADS, AuxiliaryModel, head_metrics, load_targets, smoothed_prevalence
from modeling.datasets import FEATURES, META, ModelingDataset, ids_hash, pd, sha256_file
from modeling.metrics import multiclass_metrics
from modeling.models import TabularEventModel
from modeling.phase4 import compare_head, support, verify_f3
from modeling.phase3 import PROBABILITIES


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def assert_same(actual, expected):
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError('Different result keys')
        for key in expected:
            assert_same(actual[key], expected[key])
    elif isinstance(expected, float):
        if not np.isclose(actual, expected, atol=1e-12, rtol=0):
            raise ValueError('Numeric result changed')
    elif actual != expected:
        raise ValueError('Result changed')


def check_calibration(folder, rows, raw, target, classes, cfg, smoke, auxiliary):
    policy = read(folder / 'calibration_policy.json')
    cal = rows.partition.eq('calibration').to_numpy() & rows[target].notna().to_numpy()
    review = rows.partition.eq('phase_review').to_numpy() & rows[target].notna().to_numpy()
    sufficient_cal = support(rows.loc[cal], target, classes, cfg)['sufficient']
    sufficient_review = support(rows.loc[review], target, classes, cfg)['sufficient']
    candidate = raw.copy()
    if sufficient_cal:
        fitted = TemperatureScaler.load(folder / 'temperature.json')
        if fitted.state['fit_ids_sha256'] != ids_hash(rows.loc[cal, 'pitch_uid'].tolist()):
            raise ValueError('Calibrator fit population changed')
        reproduced = TemperatureScaler(classes).fit(rows.loc[cal], raw[cal], target)
        if not np.isclose(fitted.temperature, reproduced.temperature, atol=1e-8, rtol=0):
            raise ValueError('Calibration-only refit did not reproduce temperature')
        candidate = fitted.transform(raw)
    elif (folder / 'temperature.json').exists():
        raise ValueError('Calibrator fitted without enough data')
    route = 'identity'
    if sufficient_review:
        old = multiclass_metrics(rows.loc[review, target], raw[review], classes)['multiclass_log_loss']
        new = multiclass_metrics(rows.loc[review, target], candidate[review], classes)['multiclass_log_loss']
        if sufficient_cal:
            route = calibration_decision(old, new, cfg['F4']['calibration_acceptance_max_relative_increase'])
        assert_same(compare_head(rows.loc[review], target, classes, raw[review], candidate[review], cfg, smoke), policy['paired_comparison'])
    if route != policy['route']:
        raise ValueError('Calibration decision changed')
    selected = candidate if route == 'temperature' else raw
    metrics = read(folder / 'calibration_metrics.json')
    if len(metrics) != 9:
        raise ValueError('Expected all variant/partition metrics')
    for result in metrics:
        mask = rows.partition.eq(result['partition']).to_numpy() & rows[target].notna().to_numpy()
        if result['status'] == 'insufficient_data':
            if mask.any() and (not auxiliary or support(rows.loc[mask], target, classes, cfg)['sufficient']):
                raise ValueError('Incorrect insufficient-data state')
            continue
        p = {'raw': raw, 'temperature': candidate, 'selected': selected}[result['variant']]
        f = head_metrics if auxiliary else multiclass_metrics
        expected = f(rows.loc[mask, target], p[mask], classes)
        assert_same({k: result[k] for k in expected}, expected)
        if result['ids_sha256'] != ids_hash(rows.loc[mask, 'pitch_uid'].tolist()):
            raise ValueError('Metric population changed')
    return selected, candidate, len(metrics)


def check(experiment_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = ROOT / 'artifacts/modeling' / experiment_id / 'F4'
    manifest = read(folder / 'manifest.json')
    if manifest['status'] != 'verified' or manifest['phase_id'] != 'F4' or manifest['test_accessed']:
        raise ValueError('F4 not verified')
    for name, digest in manifest['artifact_hashes'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != digest:
            raise ValueError('Artifact integrity failure: '+name)
    checks = read(folder / 'checks.json')
    if not checks or not all(v is True for v in checks.values()):
        raise ValueError('Recorded checks failed')
    cfg = read(folder / 'config.json')
    dataset = ModelingDataset()
    dependency, _ = verify_f3(dataset)
    if sha256_file(dependency / 'manifest.json') != manifest['dependency_F3']['manifest_sha256']:
        raise ValueError('F3 changed')
    if dataset.run_id != manifest['data_run'] or dataset.manifest_hash != manifest['data_manifest_sha256']:
        raise ValueError('Pinned data changed')
    cohort = dataset.load(maximum=cfg['training']['smoke_target_max_pitches'] if manifest['smoke'] else None, phase='F4')
    rows = load_targets(dataset, cohort['aligned']['pitching'])
    saved_cohort = pd.read_parquet(folder / 'cohort.parquet')
    if not rows[saved_cohort.columns].equals(saved_cohort):
        raise ValueError('Cohort or conditional labels changed')
    evaluation = rows.loc[rows.partition.ne('train')].reset_index(drop=True)
    public = pd.read_parquet(folder / 'predictions.parquet')
    if set(public.family) != set(FEATURES) or public.duplicated(['pitch_uid','family']).any():
        raise ValueError('Invalid output population')
    report, metric_groups, bootstrap_comparisons = {}, 0, 0
    for family in FEATURES:
        print('Verifying F4 '+family, flush=True)
        destination = folder / family
        result = public.loc[public.family.eq(family)].reset_index(drop=True)
        if not result[META].equals(evaluation[META]):
            raise ValueError('Output metadata displaced')
        model = TabularEventModel.load(destination / 'event/model')
        raw = model.predict(evaluation)
        selected, candidate, count = check_calibration(destination/'event', evaluation, raw, 'y_event', CLASSES, cfg, manifest['smoke'], False)
        metric_groups += count
        event_saved = pd.read_parquet(destination/'event/predictions.parquet')
        delta = 0.0
        for name, p in (('raw',raw),('temperature',candidate),('selected',selected)):
            delta = max(delta, float(np.max(np.abs(event_saved[[name+'_'+c for c in CLASSES]].to_numpy()-p))))
        if not np.allclose(result[PROBABILITIES].to_numpy(),selected,atol=1e-8,rtol=0) or delta>1e-8:
            raise ValueError('Event predictions changed')
        bootstrap_comparisons += int(read(destination/'event/calibration_policy.json')['paired_comparison'] is not None)
        decisions = {}
        for head, classes in HEADS.items():
            d = destination/head
            decision = read(d/'decision.json')
            coverage = read(d/'coverage.json')
            for part, group in rows.groupby('partition'):
                expected = support(group,head,classes,cfg)
                assert_same({k:coverage[part][k] for k in expected},expected)
            enough = all(coverage[p]['sufficient'] for p in ('train','development','phase_review'))
            if not enough:
                if decision['status']!='insufficient_data' or decision['comparison'] is not None:
                    raise ValueError('Insufficient head presented as evaluated')
                deployed = None
            else:
                fitted = AuxiliaryModel.load(d/'model')
                training = rows.loc[rows.partition.eq('train') & rows[head].notna()]
                if fitted.metadata['fit_ids_sha256'] != ids_hash(training.pitch_uid.tolist()):
                    raise ValueError('Auxiliary fit IDs changed')
                probabilities = fitted.predict(evaluation)
                chosen, calibrated, count = check_calibration(d,evaluation,probabilities,head,classes,cfg,manifest['smoke'],True)
                metric_groups += count
                bootstrap_comparisons += int(read(d/'calibration_policy.json')['paired_comparison'] is not None)
                prevalence = smoothed_prevalence(training,head,classes)
                baseline = np.tile(prevalence,(len(evaluation),1))
                if not np.array_equal(prevalence, np.array(read(d/'baseline.json')['probabilities'])):
                    raise ValueError('Training prevalence changed')
                saved = pd.read_parquet(d/'predictions.parquet')
                if not saved[META+['y_event',head]].equals(evaluation[META+['y_event',head]]):
                    raise ValueError('Conditional target alignment changed')
                for name,p in (('raw',probabilities),('temperature',calibrated),('selected',chosen),('baseline',baseline)):
                    delta=max(delta,float(np.max(np.abs(p-saved[[name+'_'+c for c in classes]].to_numpy()))))
                review=evaluation.partition.eq('phase_review').to_numpy() & evaluation[head].notna().to_numpy()
                comparison=compare_head(evaluation.loc[review],head,classes,baseline[review],chosen[review],cfg,manifest['smoke'])
                assert_same(comparison,decision['comparison'])
                bootstrap_comparisons+=1
                promoted=comparison['decision']=='promote'
                expected_route='model' if promoted else 'smoothed_training_prevalence'
                if decision['route']!=expected_route:
                    raise ValueError('Auxiliary promotion/fallback changed')
                deployed=chosen if promoted else baseline
                for metric in read(d/'baseline_metrics.json'):
                    if metric['status']=='evaluated':
                        mask=evaluation.partition.eq(metric['partition']).to_numpy() & evaluation[head].notna().to_numpy()
                        expected=head_metrics(evaluation.loc[mask,head],baseline[mask],classes)
                        assert_same({k:metric[k] for k in expected},expected)
                        metric_groups+=1
            if not result[head+'_status'].eq(decision['status']).all() or not result[head+'_route'].eq(decision['route']).all():
                raise ValueError('Public head status/route changed')
            columns = {'contact':['p_'+c+'_given_in_play' for c in classes], 'groundball':['p_groundball_given_in_play'],
                       'chase':['p_chase_given_outside']}[head]
            if deployed is None:
                if not result[columns].isna().all().all():
                    raise ValueError('Unavailable head must output null')
            else:
                wanted=deployed if head=='contact' else deployed[:,1,None]
                if not np.allclose(result[columns].to_numpy(),wanted,atol=1e-8,rtol=0):
                    raise ValueError('Conditional public probability changed')
                if head!='chase':
                    joint_columns=[c.replace('_given_in_play','_per_pitch') for c in columns]
                    if not np.allclose(result[joint_columns].to_numpy(),selected[:,4,None]*wanted,atol=1e-8,rtol=0):
                        raise ValueError('Joint probability changed')
            decisions[head]=decision['status']
        if delta>1e-8:
            raise ValueError('Reload prediction mismatch')
        report[family]={'max_abs_prediction_difference':delta,'pitches':len(evaluation),'heads':decisions}
    dataset.assert_unchanged()
    return {'status':'verified','experiment_id':experiment_id,'families':report,'metric_groups_reproduced':metric_groups,
            'bootstrap_comparisons_reproduced':bootstrap_comparisons,'output_rows':len(public),
            'artifact_files_verified':len(manifest['artifact_hashes']),'recorded_checks_passed':len(checks),
            'calibration_refit_only_2025_calibration':True,'test_accessed':False,'virtual_environment':sys.prefix!=sys.base_prefix}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-id',default='f4-full-check')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=check(args.experiment_id)
    if args.output: args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
