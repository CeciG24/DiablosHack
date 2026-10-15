"""F10 post-release: Stuff heads with pitcher-relative features, judged on Stuff's own targets (2024/2025 only).

Lives outside modeling/ so release_lock.json keeps verifying the frozen F8 release.
2026 stays out of reach: dataset.load rejects 'test' for any phase other than F8, and this
phase declares the prior exposure instead of seeking a second evaluation.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
import re
import shutil
import sys
import time
import uuid

import numpy as np

from modeling.baselines import CLASSES, EventBaseline
from modeling.cli import verify, write_json
from modeling.datasets import ROOT, META, ModelingDataset, ids_hash, join_pitches, pd, sha256_file
from modeling.metrics import multiclass_metrics, paired_bootstrap, per_pitch_losses
from modeling.models import BACKEND_VERSION
from modeling.release import read
from postrelease.phase9 import verify_f2, verify_f8
from modeling.phase2 import verify_f1
from postrelease.stuff_v3 import (BINARY, CONTEXT, DERIVATION_ID, HEAD_TARGETS, REFERENCE_INPUTS, REL,
                                  REFERENCE_MODES, VARIANTS, StuffV3Model, attach_relative, auc,
                                  build_relative_reference, event_utility_s0, index_scale,
                                  load_head_targets, reference_years, smoothed_binary_prevalence,
                                  to_index, to_index_within_type, type_variance_share,
                                  within_type_correlation, within_type_scale)

PARTS = ('development', 'calibration', 'phase_review')
EVENT_MODELS = {'event_stuff_count': 'base', 'event_stuff_count_refA': 'refA', 'event_stuff_count_refB': 'refB'}


def verify_f9(dataset):
    cfg = dataset.config
    experiment = cfg['F10']['f9_reference_experiment']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment):
        raise ValueError('Invalid F9 reference ID')
    folder = dataset.root / 'artifacts/modeling' / experiment / 'F9'
    manifest = read(folder / 'manifest.json')
    if (manifest['status'] != 'verified' or manifest['phase_id'] != 'F9' or manifest['smoke']
            or manifest['data_run'] != dataset.run_id):
        raise RuntimeError('F9 must be a verified full run on pinned data')
    for name in ('predictions.parquet', 'metrics.json'):
        if sha256_file(folder / name) != manifest['artifact_hashes'][name]:
            raise RuntimeError(f'F9 artifact integrity failure: {name}')
    return folder, manifest


def binary_loss(labels, probabilities):
    return per_pitch_losses(np.asarray(labels, dtype=int), probabilities, list(BINARY))[0]


def loss_frame(group, loss, label_column):
    return group[['pitch_uid', 'game_anon_id']].assign(y_event=group[label_column].astype(int).to_numpy(), loss=loss)


def head_metrics(labels, probabilities):
    y = np.asarray(labels, dtype=int)
    loss, brier = per_pitch_losses(y, probabilities, list(BINARY))
    return {'n': len(y), 'positives': int(y.sum()), 'log_loss': float(loss.mean()),
            'brier': float(brier.mean() / 2), 'auc': auc(y, probabilities[:, 1])}


def select_model(features, classes, training, development, label, candidates, seed, threads, rounds, patience,
                 directory, variant, task, smoke):
    trials = candidates[:1] if smoke else candidates
    if not 1 <= len(candidates) <= 12:
        raise ValueError('F10 permits at most 12 predeclared configurations per model')
    known = development.loc[development[label].notna()].sort_values('pitch_uid')
    results = []
    for i, parameters in enumerate(trials):
        model = StuffV3Model(features, classes, seed, threads, variant, task).fit(
            training, development, label, parameters, rounds, patience)
        candidate_id = f'candidate_{i + 1:02}'
        model.save(directory / candidate_id)
        probabilities = model.predict(known)
        loss = (per_pitch_losses(known[label].astype(int), probabilities, list(BINARY))[0] if len(classes) == 2
                else per_pitch_losses(known[label], probabilities, classes)[0])
        results.append({'candidate_id': candidate_id, 'parameters': parameters, 'development_log_loss': float(loss.mean()),
                        'best_iteration': model.metadata['best_iteration'],
                        'iterations_evaluated': model.metadata['iterations_evaluated']})
    selected = min(results, key=lambda row: (row['development_log_loss'], row['candidate_id']))
    return StuffV3Model.load(directory / selected['candidate_id']), {
        'selection_partition': 'development', 'selection_metric': 'log_loss', 'selected': selected,
        'trials': results, 'smoke': smoke, 'review_used_for_selection': False,
        'development_ids_sha256': ids_hash(known.pitch_uid.tolist())}


def train_stuff_v3(experiment_id=None, smoke=False, root=ROOT):
    started, tick = datetime.now(timezone.utc), time.perf_counter()
    dataset = ModelingDataset(root)
    cfg, settings = dataset.config, dataset.config['F10']
    f1_folder, f1_reference = verify_f1(dataset)
    f2_folder, f2_reference = verify_f2(dataset)
    f9_folder, f9_reference = verify_f9(dataset)
    release_folder, release_lock, exposure = verify_f8(dataset)
    if settings['cohort_policy'] != 'f0_common_v1' or cfg['training']['backend'] != 'lightgbm==' + BACKEND_VERSION:
        raise ValueError('Unsupported cohort or backend policy')
    if len(settings['candidates']) > cfg['training']['maximum_initial_hyperparameter_configurations']:
        raise ValueError('Hyperparameter budget exceeded')
    experiment_id = experiment_id or started.strftime('f10-%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', experiment_id):
        raise ValueError('Invalid experiment ID')
    folder = dataset.root / 'artifacts/modeling' / experiment_id / 'F10'
    folder.mkdir(parents=True, exist_ok=False)
    source_paths = sorted((dataset.root / 'postrelease').glob('*.py')) + sorted(
        (dataset.root / 'modeling').glob('*.py')) + [dataset.root / 'diablos_data.py']
    manifest = {
        'experiment_id': experiment_id, 'phase_id': 'F10', 'status': 'in_progress',
        'scientific_decision': 'not_applicable', 'protocol_id': 'A', 'family': 'stuff',
        'feature_set': DERIVATION_ID, 'variants': {k: {'features': v, 'reference_mode': REFERENCE_MODES[k]}
                                                   for k, v in VARIANTS.items()},
        'head_targets': HEAD_TARGETS, 'seed': cfg['seed'], 'smoke': smoke, 'data_run': dataset.run_id,
        'data_manifest_sha256': dataset.manifest_hash, 'data_output_hashes': dataset.manifest['outputs'],
        'config_sha256': dataset.config_hash,
        'code_hashes': {str(p.relative_to(dataset.root)): sha256_file(p) for p in source_paths},
        'requirements_sha256': sha256_file(dataset.root / 'requirements-modeling.txt'),
        'document_sha256': sha256_file(dataset.root / cfg['document']),
        'dependency_F1': {'experiment_id': f1_reference['experiment_id'], 'manifest_sha256': sha256_file(f1_folder / 'manifest.json')},
        'dependency_F2': {'experiment_id': f2_reference['experiment_id'], 'manifest_sha256': sha256_file(f2_folder / 'manifest.json')},
        'dependency_F9': {'experiment_id': f9_reference['experiment_id'], 'manifest_sha256': sha256_file(f9_folder / 'manifest.json')},
        'dependency_F8': {'release': release_folder.name, 'release_id': release_lock['release_id'],
                          'release_lock_sha256': sha256_file(release_folder / 'release_lock.json')},
        'post_release_development': True, 'test_previously_exposed': exposure, 'test_accessed': False,
        'transductive_variant': 'refA uses same-season physical fastball profiles of the evaluated pitcher; '
                                'no outcomes are read. refB is the deployable variant: prior-season reference at inference.',
        'ablation_rule': settings['ablation_rule'],
        'versions': {'python': platform.python_version(), **{name: importlib.metadata.version(name)
                     for name in ('pandas', 'numpy', 'pyarrow', 'duckdb', 'lightgbm', 'scipy')}},
        'python_executable': sys.executable, 'virtual_environment': sys.prefix != sys.base_prefix,
        'hardware': {'processor': platform.processor(), 'machine': platform.machine(), 'threads_used': settings['threads']},
        'started_utc': started.isoformat(),
        'scope_note': 'Development after the final test was opened; phase_review 2025 informed earlier decisions '
                      'and is not an independent test. 2026 was not queried.'}
    write_json(folder / 'manifest.json', manifest)
    write_json(folder / 'config.json', cfg)
    checks, decision = {}, 'not_applicable'
    try:
        cohort = dataset.load(maximum=cfg['training']['smoke_target_max_pitches'] if smoke else None, phase='F10')
        checks.update(verify(cohort, dataset))
        try:
            dataset.load(partitions=['test'], phase='F10')
        except PermissionError:
            checks['test_partition_rejected_for_f10'] = True
        else:
            checks['test_partition_rejected_for_f10'] = False
        rows = join_pitches(cohort['aligned']['stuff'], cohort['context']).sort_values('pitch_uid').reset_index(drop=True)
        rows = load_head_targets(dataset, rows)
        training = rows.loc[rows.partition.eq('train')]
        checks['train_game_folds_intact'] = bool(training.groupby('game_anon_id').game_cv_fold.nunique().eq(1).all())
        if not smoke:
            checks['same_F2_cohort'] = ids_hash(rows.pitch_uid.tolist()) == f2_reference['cohort']['common_ids_sha256']
        if not all(checks.values()):
            raise RuntimeError('F10 cohort checks failed before training')
        manifest['cohort'] = {'common_rows': len(rows), 'common_ids_sha256': ids_hash(rows.pitch_uid.tolist()),
                              'by_partition': {p: {'n_pitches': len(g), 'n_games': int(g.game_anon_id.nunique()),
                                                   'ids_sha256': ids_hash(g.pitch_uid.tolist())} for p, g in rows.groupby('partition')},
                              'head_support': {name: {p: int(g[col].notna().sum()) for p, g in rows.groupby('partition')}
                                               for name, col in HEAD_TARGETS.items()},
                              'exclusions': cohort['exclusions']}
        write_json(folder / 'cohort_manifest.json', manifest['cohort'])
        rows[META].to_parquet(folder / 'cohort.parquet', index=False)

        minimum = settings['reference_min_fastballs']
        refs = build_relative_reference(rows[REFERENCE_INPUTS], minimum)
        refs_prior = refs.loc[refs.reference_year.eq(2024)].reset_index(drop=True)
        shuffled = build_relative_reference(rows[REFERENCE_INPUTS].sample(frac=1, random_state=3), minimum)
        shuffled = shuffled.sort_values(['pitcher_anon_id', 'reference_year']).reset_index(drop=True)
        keys = ['pitcher_anon_id', 'reference_year', 'reference_type', 'fb_n']
        numeric = [c for c in refs.columns if c not in keys]
        checks['reference_deterministic_order_invariant'] = bool(
            refs[keys].equals(shuffled[keys]) and np.allclose(refs[numeric], shuffled[numeric], rtol=0, atol=1e-9))
        try:
            build_relative_reference(rows[REFERENCE_INPUTS + ['y_event']], minimum)
        except ValueError:
            checks['reference_builder_rejects_outcomes'] = True
        else:
            checks['reference_builder_rejects_outcomes'] = False
        checks['refA_same_season_reference'] = bool(
            (reference_years(rows, 'same_season') == rows.year.to_numpy()).all())
        evaluation_mask = ~rows.partition.eq('train')
        prior_years = reference_years(rows, 'prior_season_at_inference')
        checks['refB_evaluation_uses_only_2024_reference'] = bool(
            (prior_years[evaluation_mask.to_numpy()] == 2024).all() and set(refs_prior.reference_year) == {2024})
        refs.to_parquet(folder / 'reference_profiles.parquet', index=False)
        frames = {'base': rows.assign(has_reference=False),
                  'refA': attach_relative(rows, refs, 'same_season'),
                  'refB': attach_relative(rows, refs_prior, 'prior_season_at_inference')}
        coverage = [{'variant': variant, 'partition': part, 'n': len(g), 'with_reference': int(g.has_reference.sum()),
                     'coverage': float(g.has_reference.mean())}
                    for variant in ('refA', 'refB') for part, g in frames[variant].groupby('partition')]
        write_json(folder / 'reference_coverage.json', coverage)

        rounds = settings['smoke_rounds'] if smoke else settings['maximum_rounds']
        threads, seed = settings['threads'], cfg['seed']
        models, selections, sources = {}, {}, {}
        for head, target in HEAD_TARGETS.items():
            for variant, features in VARIANTS.items():
                print(f'F10: head {head} / {variant}: fitting on 2024, selecting on development 2025', flush=True)
                frame = frames[variant]
                train_v, dev_v = frame.loc[frame.partition.eq('train')], frame.loc[frame.partition.eq('development')]
                directory = folder / 'candidates' / head / variant
                model, selection = select_model(features, list(BINARY), train_v, dev_v, target, settings['candidates'], seed,
                                                threads, rounds, settings['early_stopping_rounds'], directory, variant, 'head', smoke)
                selection.update(head=head, variant=variant, target=target)
                model.save(folder / 'models' / head / variant)
                models[(head, variant)] = StuffV3Model.load(folder / 'models' / head / variant)
                selections[f'{head}/{variant}'] = selection
                sources[(head, variant)] = (train_v, dev_v, target, selection['selected']['parameters'])
        for name, variant in EVENT_MODELS.items():
            print(f'F10: event model {name}: fitting on 2024, selecting on development 2025', flush=True)
            frame = frames[variant]
            features = VARIANTS[variant] + CONTEXT
            train_v, dev_v = frame.loc[frame.partition.eq('train')], frame.loc[frame.partition.eq('development')]
            model, selection = select_model(features, CLASSES, train_v, dev_v, 'y_event', [settings['event_parameters']], seed,
                                            threads, rounds, settings['early_stopping_rounds'],
                                            folder / 'candidates' / name, variant, 'event', smoke)
            selection.update(head=name, variant=variant, target='y_event')
            model.save(folder / 'models' / name)
            models[(name, variant)] = StuffV3Model.load(folder / 'models' / name)
            selections[name] = selection
            sources[(name, variant)] = (train_v, dev_v, 'y_event', settings['event_parameters'])
        write_json(folder / 'selection.json', selections)
        checks['selection_argmin_development'] = all(
            s['selected'] == min(s['trials'], key=lambda r: (r['development_log_loss'], r['candidate_id']))
            and not s['review_used_for_selection'] for s in selections.values())
        checks['encoders_fitted_only_on_training'] = all(
            m.vocabularies[c] == sorted(training[c].unique().tolist()) for m in models.values() for c in m.vocabularies)
        checks['exact_feature_lists'] = all(m.booster.feature_name() == m.features for m in models.values())
        checks['relative_features_only_in_ref_variants'] = all(
            (set(REL) & set(m.features) != set()) == (key[1] != 'base') for key, m in models.items())

        evaluation = {v: f.loc[~f.partition.eq('train')].reset_index(drop=True) for v, f in frames.items()}
        predictions = {key: m.predict(evaluation[key[1]]) for key, m in models.items()}
        print('F10: verifying reload and deterministic refit of selected configurations', flush=True)
        reload_diff = refit_diff = 0.0
        for key, model in models.items():
            train_v, dev_v, target, parameters = sources[key]
            replay = StuffV3Model(model.features, model.classes, seed, threads, model.variant, model.task).fit(
                train_v, dev_v, target, parameters, rounds, settings['early_stopping_rounds'])
            refit_diff = max(refit_diff, float(np.max(np.abs(predictions[key] - replay.predict(evaluation[key[1]])))))
            reload_diff = max(reload_diff, float(np.max(np.abs(predictions[key] - model.predict(evaluation[key[1]])))))
        atol = cfg['numerical_checks']['reload_prediction_atol_cpu']
        checks['reload_prediction_tolerance'] = reload_diff <= atol
        checks['deterministic_refit'] = refit_diff <= atol
        write_json(folder / 'reproducibility.json', {
            'reload_max_abs_difference': reload_diff, 'refit_max_abs_difference': refit_diff, 'tolerance': atol,
            'n_models': len(models), 'selection_not_repeated': True})

        for (name, variant), model in models.items():
            probe = evaluation[variant].iloc[:512].copy()
            expected = model.predict(probe)
            ignored = ['plate_loc_height', 'plate_loc_side', 'batter_side', 'altitude_category', 'pitch_uid',
                       'game_anon_id', 'pitcher_anon_id', 'year', 'y_event', 'y_whiff_given_swing', 'y_groundball_bip']
            if model.task == 'head':
                ignored += CONTEXT
            for column in ignored:
                changed = probe.copy()
                changed[column] = 'ignored_context'
                checks[f'invariant_{name}_{variant}_{column}'] = bool(np.array_equal(expected, model.predict(changed)))
            missing = probe.copy()
            missing.loc[missing.index[0], 'rel_speed'] = np.nan
            try:
                model.predict(missing)
            except ValueError:
                checks[f'missing_physics_rejected_{name}_{variant}'] = True
            else:
                checks[f'missing_physics_rejected_{name}_{variant}'] = False
        refB_model = models[('whiff_given_swing', 'refB')]
        probe = evaluation['refB'].iloc[:512].copy()
        probe[REL] = np.nan
        checks['missing_reference_finite_with_warning'] = bool(
            np.isfinite(refB_model.predict(probe)).all()
            and all('insufficient_arsenal_reference' in w for w in refB_model.warnings(probe)))
        probe = evaluation['refB'].iloc[:512].copy()
        probe['auto_pitch_type'] = '__unknown__'
        checks['unseen_category_finite_with_warning'] = bool(
            np.isfinite(refB_model.predict(probe)).all()
            and all('unknown_category' in w for w in refB_model.warnings(probe)))

        metrics, head_rows, event_rows = [], [], []
        for head, target in HEAD_TARGETS.items():
            prevalence = smoothed_binary_prevalence(training, target)
            for variant in list(VARIANTS) + ['prevalence']:
                frame = evaluation['base' if variant == 'prevalence' else variant]
                p = (np.tile([1 - prevalence, prevalence], (len(frame), 1)) if variant == 'prevalence'
                     else predictions[(head, variant)])
                for part in PARTS:
                    mask = (frame.partition.eq(part) & frame[target].notna()).to_numpy()
                    if mask.sum() == 0:
                        continue
                    metrics.append(dict(head_metrics(frame.loc[mask, target], p[mask]), task='head', head=head,
                                        model=variant, partition=part, n_games=int(frame.loc[mask].game_anon_id.nunique()),
                                        ids_sha256=ids_hash(frame.loc[mask].pitch_uid.tolist())))
                out = frame[['pitch_uid', 'game_anon_id', 'partition', 'has_reference']].copy()
                out['head'], out['model'], out['label'], out['p_positive'] = head, variant, frame[target], p[:, 1]
                head_rows.append(out)
        columns = ['p_' + label for label in CLASSES]
        f1_predictions = None if smoke else pd.read_parquet(f1_folder / 'predictions.parquet')
        for name in ['B1'] + list(EVENT_MODELS):
            if name == 'B1':
                frame = evaluation['base']
                if smoke:
                    baseline = EventBaseline(name, cfg['event_class_order'],
                                             cfg['training']['baseline_global_pseudocount_per_class'],
                                             cfg['training']['baseline_group_prior_strength']).fit(training)
                    baseline.save(folder / 'B1.json')
                else:
                    shutil.copyfile(f1_folder / 'models/B1.json', folder / 'B1.json')
                baseline = EventBaseline.load(folder / 'B1.json')
                checks['B1_same_training_ids'] = baseline.state['fit_ids_sha256'] == ids_hash(training.pitch_uid.tolist())
                probabilities, _ = baseline.predict(frame[['balls', 'strikes', 'auto_pitch_type']])
                if not smoke:
                    past = f1_predictions.loc[f1_predictions.model.eq('B1'), ['pitch_uid'] + columns]
                    aligned = join_pitches(frame[['pitch_uid']], past)
                    checks['B1_matches_F1_probabilities'] = len(aligned) == len(frame) and bool(
                        np.array_equal(probabilities, aligned[columns].to_numpy()))
            else:
                frame, probabilities = evaluation[EVENT_MODELS[name]], predictions[(name, EVENT_MODELS[name])]
            out = frame[['pitch_uid', 'game_anon_id', 'partition', 'y_event']].copy()
            out[columns], out['model'] = probabilities, name
            event_rows.append(out)
            for part in PARTS:
                mask = frame.partition.eq(part).to_numpy()
                metrics.append(dict(multiclass_metrics(frame.loc[mask, 'y_event'], probabilities[mask], CLASSES),
                                    task='event', head='y_event', model=name, partition=part,
                                    n_games=int(frame.loc[mask].game_anon_id.nunique()),
                                    ids_sha256=ids_hash(frame.loc[mask].pitch_uid.tolist())))
        head_predictions, event_predictions = pd.concat(head_rows, ignore_index=True), pd.concat(event_rows, ignore_index=True)
        checks['unique_head_pitch_model_pairs'] = not head_predictions.duplicated(['pitch_uid', 'head', 'model']).any()
        checks['unique_event_pitch_model_pairs'] = not event_predictions.duplicated(['pitch_uid', 'model']).any()
        checks['only_2025_predictions'] = bool(evaluation['base'].year.eq(2025).all())
        checks['finite_metrics'] = bool(np.isfinite([m[k] for m in metrics for k in
                                                     (('log_loss', 'brier') if m['task'] == 'head' else
                                                      ('multiclass_log_loss', 'multiclass_brier_sum_over_classes'))]).all())
        head_predictions.to_parquet(folder / 'head_predictions.parquet', index=False)
        event_predictions.to_parquet(folder / 'event_predictions.parquet', index=False)
        checks['predictions_roundtrip'] = (head_predictions.equals(pd.read_parquet(folder / 'head_predictions.parquet'))
                                           and event_predictions.equals(pd.read_parquet(folder / 'event_predictions.parquet')))

        bootstrap = cfg['evaluation']['bootstrap_smoke' if smoke else 'bootstrap_full']
        args = (bootstrap, seed, cfg['evaluation']['bootstrap_confidence'],
                cfg['evaluation']['promotion_min_relative_log_loss_reduction'], smoke)

        review_heads = head_predictions.loc[head_predictions.partition.eq('phase_review') & head_predictions.label.notna()]
        review_events = event_predictions.loc[event_predictions.partition.eq('phase_review')]

        def head_losses(head, model, subset=None):
            group = review_heads.loc[review_heads['head'].eq(head) & review_heads.model.eq(model)].sort_values('pitch_uid')
            if subset is not None:
                group = group.loc[group.pitch_uid.isin(subset)]
            loss = binary_loss(group.label, np.column_stack([1 - group.p_positive, group.p_positive]))
            return group[['pitch_uid', 'game_anon_id']].assign(y_event=group.label.astype(int).to_numpy(), loss=loss)

        def event_losses(model):
            group = review_events.loc[review_events.model.eq(model)].sort_values('pitch_uid')
            return group[['pitch_uid', 'game_anon_id', 'y_event']].assign(
                loss=per_pitch_losses(group.y_event, group[columns].to_numpy(), CLASSES)[0])

        def compare(reference, candidate):
            result = paired_bootstrap(reference, candidate, *args)
            result['evidence_of_improvement'] = bool(result['ci_high'] is not None and result['ci_high'] < 0 and not smoke)
            return result

        comparisons = {}
        review_refs = head_predictions.loc[head_predictions.partition.eq('phase_review') & head_predictions.has_reference & head_predictions.model.eq('refB')]
        covered = set(review_refs.pitch_uid)
        for head in HEAD_TARGETS:
            for variant in VARIANTS:
                comparisons[f'{head}:{variant}_vs_prevalence'] = compare(
                    head_losses(head, 'prevalence'), head_losses(head, variant))
            for variant in ('refA', 'refB'):
                comparisons[f'{head}:{variant}_vs_base'] = compare(
                    head_losses(head, 'base'), head_losses(head, variant))
            comparisons[f'{head}:refB_vs_base_with_reference_only'] = compare(
                head_losses(head, 'base', covered), head_losses(head, 'refB', covered))
        comparisons['event:stuff_count_vs_B1'] = compare(event_losses('B1'),
                                                         event_losses('event_stuff_count'))
        for variant in ('refA', 'refB'):
            comparisons[f'event:{variant}_vs_stuff_count'] = compare(
                event_losses('event_stuff_count'),
                event_losses(f'event_stuff_count_{variant}'))
        whiff = {v: comparisons[f'whiff_given_swing:{v}_vs_base'] for v in ('refA', 'refB')}
        if smoke:
            decision = 'inconclusive'
        elif whiff['refB']['evidence_of_improvement']:
            decision = 'adopt_refB_deployable'
        elif whiff['refA']['evidence_of_improvement']:
            decision = 'refA_diagnostic_only'
        else:
            decision = 'retain_base'
        selected_variant = 'refB' if decision == 'adopt_refB_deployable' else 'base'

        print(f'F10: building type-neutral index from P(whiff|swing), variant {selected_variant}', flush=True)
        weights = cfg['score']['default_weights']
        frame = evaluation[selected_variant].copy()
        frame['score'] = predictions[('whiff_given_swing', selected_variant)][:, 1]
        reference = frame.loc[frame.partition.eq('calibration')]
        global_scale, type_scale = index_scale(reference.score), within_type_scale(reference, 'score')
        frame['index_global'] = to_index(frame.score, global_scale)
        frame['index_within_type'] = to_index_within_type(frame, 'score', type_scale)
        review = frame.loc[frame.partition.eq('phase_review')].reset_index(drop=True)
        known = review.y_whiff_given_swing.notna().to_numpy()
        diagnostics = {'partition': 'phase_review', 'selected_variant': selected_variant, 'n_pitches': len(review),
                       'n_with_whiff_label': int(known.sum())}
        review_scores = {'v3_raw': review.score.to_numpy(), 'v3_index_global': review.index_global.to_numpy(),
                         'v3_index_within_type': review.index_within_type.to_numpy()}
        if not smoke:
            f9_predictions = pd.read_parquet(f9_folder / 'predictions.parquet')
            for old in ('Stuff', 'StuffV2'):
                part = f9_predictions.loc[f9_predictions.model.eq(old) & f9_predictions.partition.eq('phase_review')]
                aligned = join_pitches(review[['pitch_uid']], part[['pitch_uid'] + columns])
                review_scores[old + '_S0'] = event_utility_s0(aligned[columns].to_numpy(), weights) \
                    if aligned.pitch_uid.tolist() == review.pitch_uid.tolist() else None
        diagnostics['scores'] = {}
        for name, values in review_scores.items():
            if values is None:
                continue
            diagnostics['scores'][name] = {
                'type_variance_share': type_variance_share(values, review.auto_pitch_type),
                'within_type_corr_with_whiff_given_swing': within_type_correlation(
                    values[known], review.auto_pitch_type[known], review.y_whiff_given_swing[known]),
                'global_corr_with_whiff_given_swing': float(np.corrcoef(values[known], review.y_whiff_given_swing[known])[0, 1])}
        write_json(folder / 'index_diagnostics.json', diagnostics)
        write_json(folder / 'index_scales.json', {'derivation': DERIVATION_ID, 'score': 'p_whiff_given_swing',
                   'variant': selected_variant, 'reference_partition': 'calibration', 'global': global_scale,
                   'within_type': type_scale, 'provisional': True, 'represents_expected_runs': False})
        frame[['pitch_uid', 'partition', 'auto_pitch_type', 'score', 'index_global', 'index_within_type', 'has_reference']].rename(
            columns={'score': 'p_whiff_given_swing'}).to_parquet(folder / 'stuff_v3_index.parquet', index=False)
        checks['index_reference_calibration_only'] = bool(global_scale['n'] == int(frame.partition.eq('calibration').sum()))
        checks['index_global_mean_100_std_10'] = bool(
            abs(frame.loc[frame.partition.eq('calibration'), 'index_global'].mean() - 100) < 1e-6
            and abs(frame.loc[frame.partition.eq('calibration'), 'index_global'].std(ddof=0) - 10) < 1e-6)
        checks['index_finite'] = bool(np.isfinite(frame[['index_global', 'index_within_type']].to_numpy()).all())
        write_json(folder / 'metrics.json', {
            'status': 'smoke_only' if smoke else 'evaluated', 'protocol_id': 'A', 'data_run': dataset.run_id, 'seed': seed,
            'metrics': metrics, 'comparisons': comparisons, 'scientific_decision': decision,
            'selected_variant': selected_variant, 'ablation_rule': settings['ablation_rule'],
            'index_diagnostics': diagnostics, 'review_is_independent_final_test': False,
            'post_release_development': True, 'release_unchangeable_test_exposed': True})
        write_json(folder / 'checks.json', {key: bool(value) for key, value in checks.items()})
        if not all(checks.values()):
            raise RuntimeError('F10 checks failed: ' + ', '.join(k for k, v in checks.items() if not v))
        dataset.assert_unchanged()
        manifest.update(status='verified', scientific_decision=decision, selected_variant=selected_variant)
        (folder / 'decision.md').write_text(
            '# Decisión F10\n\nImplementación: `verified`. Decisión científica: `' + decision + '`.\n\n'
            'Desarrollo posterior a la apertura del test 2026 (release `' + release_lock['release_id']
            + '`); la exposición quedó declarada y 2026 no se consultó.\n\n'
            'Ajuste solo en 2024; selección y parada temprana solo en development 2025; escalas del índice '
            'solo en calibration 2025. Regla de ablación: ' + settings['ablation_rule'] + '.\n\n'
            + {'adopt_refB_deployable': 'Las features relativas con referencia del año previo mejoran whiff|swing con IC bajo cero: '
                                        'evidencia para una futura versión del índice, sin reabrir el release.\n\n',
               'refA_diagnostic_only': 'Solo la referencia de la misma temporada (transductiva) mejora; no es desplegable. '
                                       'Se conserva Stuff base.\n\n',
               'retain_base': 'Las features relativas no mejoran con evidencia; se conserva Stuff base.\n\n',
               'inconclusive': ''}[decision]
            + 'phase_review 2025 ya informó decisiones anteriores: no es un test independiente.\n\n'
            + ('Smoke no produce conclusión científica.\n\n' if smoke else '')
            + 'El release F8 permanece intacto y verificable.\n', encoding='utf-8')
    except Exception as exc:
        manifest.update(status='blocked', error=f'{type(exc).__name__}: {exc}')
        write_json(folder / 'checks.json', {**{k: bool(v) for k, v in checks.items()}, 'technical_failure': False, 'error': manifest['error']})
        (folder / 'decision.md').write_text('# F10 blocked\n\nNo avanzar.\n\n' + manifest['error'], encoding='utf-8')
        raise
    finally:
        manifest['finished_utc'], manifest['elapsed_seconds'] = datetime.now(timezone.utc).isoformat(), time.perf_counter() - tick
        manifest['artifact_hashes'] = {p.relative_to(folder).as_posix(): sha256_file(p)
                                       for p in sorted(folder.rglob('*')) if p.is_file() and p != folder / 'manifest.json'}
        write_json(folder / 'manifest.json', manifest)
    print(json.dumps({'path': str(folder), 'status': manifest['status'], 'decision': decision,
                      'selected_variant': manifest.get('selected_variant')}, indent=2))
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-id')
    parser.add_argument('--smoke', action='store_true', help='Small flow check: 1 candidate, reduced rounds and bootstrap')
    args = parser.parse_args()
    try:
        train_stuff_v3(args.experiment_id, args.smoke)
    except (ValueError, RuntimeError, PermissionError, FileExistsError) as exc:
        parser.exit(1, f'F10 blocked: {exc}\n')


if __name__ == '__main__':
    main()
