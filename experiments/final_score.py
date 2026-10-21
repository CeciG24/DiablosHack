"""Train a location-aware arsenal candidate, without accessing the 2026 test."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase10_features import REGULARIZED, Repertoire
from experiments.phase9 import RELEASE, write
from experiments.phase9_predict import verify_experiment
from modeling.arsenal import ArsenalEventModel
from modeling.baselines import CLASSES
from modeling.calibration import TemperatureScaler
from modeling.datasets import ROOT, META, PITCHING, ids_hash, require_unique, sha256_file
from modeling.final_score import CombinedEventModel, FinalScorePredictor, VERSION, WEIGHTS
from modeling.metrics import calibration_bins, multiclass_metrics, paired_bootstrap, per_pitch_losses
from modeling.release import verify_release


def split_rows(rows):
    require_unique(rows)
    if not rows.year.isin([2024, 2025]).all():
        raise PermissionError('Final-score development cannot read 2026')
    parts = {}
    for role in ('development', 'calibration', 'phase_review'):
        part = rows.loc[rows.year.eq(2025) & rows.partition.eq(role)].copy()
        if part.empty or part.game_anon_id.isna().any():
            raise ValueError('Missing partition or game: '+role)
        parts[role] = part
    roles = list(parts)
    for i, role in enumerate(roles):
        for other in roles[i+1:]:
            if set(parts[role].game_anon_id) & set(parts[other].game_anon_id):
                raise ValueError('Game leakage between '+role+' and '+other)
    return parts


def run(destination, source):
    if destination.exists():
        raise FileExistsError(destination)
    cfg = json.loads((ROOT/'config/final_score.json').read_text(encoding='utf-8'))
    source_manifest = verify_experiment(source)
    release_id = verify_release(RELEASE)['release_id']
    exposure = ROOT/'artifacts/modeling/test_exposure.json'
    before = sha256_file(exposure)
    # Read only the verified 2024/2025 cohort, never the raw/test tables.
    rows = pd.read_parquet(source/'cohort.parquet', columns=META+PITCHING+['y_event'])
    parts = split_rows(rows)
    repertoire = Repertoire.load(source/'repertoire')
    prepared = {role: repertoire.transform(frame) for role, frame in parts.items()}
    destination.mkdir(parents=True, exist_ok=False)
    write(destination/'config.json', cfg)
    repertoire.save(destination/'repertoire')
    contract = json.loads((ROOT/'config/data_contract.json').read_text(encoding='utf-8'))
    write(destination/'input_bounds.json', contract['physical_review_bounds'])
    summary = dict(version=VERSION, experimental=True, production_promotion=False,
                   post_test_exposure=True, new_test_access=False, models={}, checks={},
                   partitions={k: dict(n=len(v), games=int(v.game_anon_id.nunique()),
                                       ids_sha256=ids_hash(v.pitch_uid.tolist()))
                               for k, v in parts.items()})
    losses, predictions = {}, {}
    for name, model in (
            ('base', ArsenalEventModel(False, cfg['seed'], cfg['threads'])),
            ('combined', CombinedEventModel(cfg['seed'], cfg['threads']))):
        print(f'Final score {name}: fit={len(parts["development"])}, rounds={cfg["rounds"]}', flush=True)
        model.fit(prepared['development'], cfg['parameters'], cfg['rounds'])
        folder = destination/name
        folder.mkdir()
        model.save(folder/'model')
        calibrator = TemperatureScaler(CLASSES).fit(
            prepared['calibration'], model.predict(prepared['calibration']), 'y_event')
        calibrator.save(folder/'temperature.json')
        p = calibrator.transform(model.predict(prepared['phase_review']))
        predictions[name] = p
        detail = parts['phase_review'][['pitch_uid', 'game_anon_id', 'y_event']].copy()
        detail['loss'] = per_pitch_losses(detail.y_event, p, CLASSES)[0]
        losses[name] = detail
        summary['models'][name] = multiclass_metrics(detail.y_event, p, CLASSES)
        summary['models'][name]['subgroups'] = {
            status: multiclass_metrics(detail.loc[mask, 'y_event'], p[mask], CLASSES)
            for status in ('regularized_2024_history', 'group_prior_only')
            if (mask := prepared['phase_review'].history_status.eq(status).to_numpy()).any()}
        write(folder/'calibration_bins.json', calibration_bins(detail.y_event, p, CLASSES))
        if name == 'combined':
            gain = model.booster.feature_importance('gain')
            write(folder/'feature_gain.json', dict(zip(model.features, gain.tolist())))
            summary['checks']['arsenal_used_by_trees'] = bool(sum(gain[model.features.index(c)] for c in REGULARIZED) > 0)
            summary['checks']['reload_identical'] = bool(np.array_equal(
                model.predict(prepared['phase_review']), CombinedEventModel.load(folder/'model').predict(prepared['phase_review'])))
            reference_p = calibrator.transform(model.predict(prepared['calibration']))
    comparison = paired_bootstrap(losses['base'], losses['combined'],
        cfg['bootstrap_repetitions'], cfg['seed'],
        minimum_relative_improvement=cfg['minimum_relative_improvement'])
    comparison.update(scientific_evidence=False, scope='exploratory_reused_2025_review_after_test_exposure')
    summary['comparison'] = comparison
    utilities = reference_p @ WEIGHTS
    mu, sigma = float(utilities.mean()), float(utilities.std())
    if not np.isfinite([mu, sigma]).all() or sigma <= 1e-12:
        raise ValueError('Degenerate reference scale')
    write(destination/'scale.json', dict(version=VERSION, mu=mu, sigma=sigma,
        reference_n=len(utilities), reference_ids_sha256=ids_hash(parts['calibration'].pitch_uid.tolist()),
        weights=WEIGHTS.tolist(), context_mode=cfg['score_context'],
        represents_runs=False, experimental=True))
    scores = 100+10*(utilities-mu)/sigma
    summary['checks'].update(reference_mean_100=bool(np.isclose(scores.mean(), 100)),
        reference_std_10=bool(np.isclose(scores.std(), 10)),
        F8_unchanged=verify_release(RELEASE)['release_id'] == release_id,
        test_exposure_unchanged=sha256_file(exposure) == before)
    if not all(summary['checks'].values()):
        raise AssertionError(summary['checks'])
    write(destination/'summary.json', summary)
    write(destination/'manifest.json', dict(
        version=VERSION, source_manifest_sha256=sha256_file(source/'manifest.json'),
        source_data_run=source_manifest.get('data_run'), F8_release_id=release_id,
        test_exposure_sha256=before,
        sources={str(p.relative_to(ROOT)): sha256_file(p) for p in (
            Path(__file__), ROOT/'modeling/final_score.py', ROOT/'config/final_score.json')},
        artifacts={str(p.relative_to(destination)): sha256_file(p)
                   for p in sorted(destination.rglob('*')) if p.is_file()}))
    predictor = FinalScorePredictor(destination)
    check = parts['phase_review'].iloc[:8].to_dict('records')
    actual = predictor.records(check)
    if not np.allclose([r['score'] for r in actual],
                       100+10*(predictions['combined'][:8]@WEIGHTS-mu)/sigma):
        raise AssertionError('Saved predictor differs from training inference')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT/'artifacts/modeling/f10-full/F10')
    args = parser.parse_args()
    run(args.output, args.source)
