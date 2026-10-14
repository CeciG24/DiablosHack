"""Immutable local release bundles and auditable final-test authorization."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from modeling.datasets import ROOT, ModelingDataset, sha256_file, ids_hash, pd
from modeling.phase7 import verify_f6


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def verify_release(folder, release_id=None, check_code=True):
    folder=Path(folder)
    lock=read(folder/'release_lock.json')
    identity=lock.pop('release_id')
    if identity != digest(lock) or (release_id is not None and release_id != identity):
        raise ValueError('Release identity mismatch')
    lock['release_id']=identity
    for name,expected in lock['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path)!=expected:
            raise ValueError('Release artifact changed: '+name)
    if check_code:
        for name,expected in lock['code_hashes'].items():
            if sha256_file(ROOT/name)!=expected:
                raise ValueError('Frozen code changed: '+name)
        if sha256_file(ROOT/'requirements-modeling.txt')!=lock['requirements_sha256']:
            raise ValueError('Frozen requirements changed')
    return lock


def freeze(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}',name):
        raise ValueError('Invalid release name')
    if (ROOT/'artifacts/modeling/test_exposure.json').exists():
        raise PermissionError('Test already exposed: new development requires a separately labeled protocol')
    dataset=ModelingDataset()
    cfg=dataset.config
    if next(p for p in cfg['phases'] if p['id']=='F7')['status']!='verified':
        raise ValueError('F7 must be verified')
    f6,f4=verify_f6(dataset)
    f7=ROOT/'artifacts/modeling'/cfg['F8']['f7_reference_experiment']/'F7'
    m=read(f7/'manifest.json')
    if m['status']!='verified' or m['smoke'] or m['test_accessed'] or m['data_run']!=dataset.run_id:
        raise ValueError('Verified full F7 required')
    for filename,expected in m['artifact_hashes'].items():
        path=(f7/filename).resolve()
        if not path.is_relative_to(f7.resolve()) or sha256_file(path)!=expected:
            raise ValueError('F7 artifact changed')
    if not all(v is True for v in read(f7/'checks.json').values()):
        raise ValueError('F7 checks failed')
    for key in ('F7','score','protocol_A'):
        if cfg[key]!=read(f7/'config.json')[key]:
            raise ValueError('F7 policy changed')
    folder=ROOT/'artifacts/modeling/releases'/name
    folder.mkdir(parents=True,exist_ok=False)
    for family in ('stuff','location','pitching'):
        for head in ('event','contact','groundball','chase'):
            src=f4/family/head
            dst=folder/'models'/family/head
            dst.mkdir(parents=True)
            for filename in ('calibration_policy.json','temperature.json','decision.json','baseline.json'):
                if (src/filename).exists():shutil.copy2(src/filename,dst/filename)
            if (src/'model').exists():shutil.copytree(src/'model',dst/'model')
        shutil.copy2(f7/(family+'_event_utility_proxy_v1.json'),folder/(family+'_scale.json'))
    shutil.copytree(f6/'environment/model',folder/'environment/model')
    for filename in ('calibration_policy.json','temperature.json'):
        shutil.copy2(f6/'environment'/filename,folder/'environment'/filename)
    shutil.copy2(f7/'reference_ids.parquet',folder/'reference_ids.parquet')
    shutil.copy2(ROOT/'artifacts/modeling'/cfg['F4']['f3_reference_experiment']/'F3/A/B1.json',folder/'B1.json')
    shutil.copy2(ROOT/cfg['data_contract'],folder/'data_contract.json')
    write(folder/'config.json',cfg)
    cohort=pd.read_parquet(f6/'cohort.parquet')
    train=cohort.loc[cohort.partition.eq('train')]
    write(folder/'training_support.json',dict(pitchers=sorted(train.pitcher_anon_id.unique()),
        pitchers_seen_development=sorted(cohort.pitcher_anon_id.unique()),
        fit_ids_sha256=ids_hash(train.pitch_uid.tolist()),
        numeric_bounds={c:[float(train[c].min()),float(train[c].max())] for c in train.select_dtypes(include='number') if c not in ('year','game_cv_fold')}))
    write(folder/'cohorts.json',dict(F4_manifest=sha256_file(f4/'manifest.json'),F6_manifest=sha256_file(f6/'manifest.json'),
        F7_manifest=sha256_file(f7/'manifest.json'),reference=read(f7/'policy.json'),
        partitions={p:dict(n=len(g),ids_sha256=ids_hash(g.pitch_uid.tolist())) for p,g in cohort.groupby('partition')}))
    write(folder/'policy.json',dict(protocol_id='A',route='base',score_version='event_utility_proxy_v1',
        arsenal_promoted=False,environment_promoted=False,heads='F4_selected_model_or_training_prevalence',
        comparisons=cfg['F8']['comparisons'],selection_on_test=False,
        evaluation_cohort='common_F0_eligibility_and_known_event',
        inference_cohort='family_observable_inputs_only_without_outcomes',
        subgroup_policy='report_counts_and_metrics_no_promotion',
        environment_mode='not_used_by_approved_policy',provisional=True))
    files={p.relative_to(folder).as_posix():sha256_file(p) for p in sorted(folder.rglob('*')) if p.is_file()}
    lock=dict(schema_version=1,name=name,created_utc=datetime.now(timezone.utc).isoformat(),data_run=dataset.run_id,
        data_manifest_sha256=dataset.manifest_hash,database_sha256=sha256_file(dataset.run/'diablos.duckdb'),
        files=files,code_hashes={str(p.relative_to(ROOT)):sha256_file(p) for p in sorted((ROOT/'modeling').glob('*.py'))},
        requirements_sha256=sha256_file(ROOT/'requirements-modeling.txt'),test_opened_at_freeze=False,
        test_quality_previously_profiled=True,score_version='event_utility_proxy_v1')
    lock['release_id']=digest(lock)
    write(folder/'release_lock.json',lock)
    dataset.assert_unchanged()
    print(json.dumps(dict(folder=str(folder),release_id=lock['release_id']),indent=2),flush=True)
    return folder


def authorize_test(folder,release_id,reproduce=False):
    lock=verify_release(folder,release_id)
    dataset=ModelingDataset()
    if dataset.run_id!=lock['data_run'] or dataset.manifest_hash!=lock['data_manifest_sha256']:
        raise ValueError('Pinned data mismatch')
    if sha256_file(dataset.run/'diablos.duckdb')!=lock['database_sha256']:
        raise ValueError('Pinned database changed')
    marker=ROOT/'artifacts/modeling/test_exposure.json'
    event=dict(release_id=release_id,opened_utc=datetime.now(timezone.utc).isoformat(),
               purpose='reproduction' if reproduce else 'final_evaluation',data_run=dataset.run_id)
    if marker.exists():
        previous=read(marker)
        if not reproduce or previous['release_id']!=release_id:
            raise PermissionError('Test already opened; explicit reproduction of the same release required')
    else:
        if reproduce:raise PermissionError('No initial evaluation to reproduce')
        with marker.open('x',encoding='utf-8') as handle:json.dump(event,handle,indent=2)
    with (ROOT/'artifacts/modeling/test_access.jsonl').open('a',encoding='utf-8') as handle:
        handle.write(json.dumps(event)+'\n')
    return dataset,lock
