"""Validate the published artifacts and row-level contracts again."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_data import sha256, validate_tables, pd
from diablos_data import current_run, connect, load_model_data

run=current_run()
manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
for name,info in manifest['outputs'].items():
    assert sha256(run/name)==info['sha256'], name+' checksum mismatch'
for name,info in manifest['raw_files'].items():
    assert sha256(ROOT/info['path'])==info['sha256'], name+' raw checksum mismatch'
tables={p.stem:pd.read_parquet(p) for p in run.glob('*.parquet')}
cfg=json.loads((ROOT/'config/data_contract.json').read_text(encoding='utf-8'))
checks=validate_tables(tables,cfg)
with connect() as db:
    assert db.execute('SELECT count(*) FROM pitches').fetchone()[0]==cfg['expected_rows']
    assert db.execute('SELECT count(*) FROM model_base').fetchone()[0]==cfg['expected_rows']
    assert db.execute('SELECT count(*) FROM unseen_pitcher_test').fetchone()[0]==42162
    for name in ['train','validation','test']:
        X,y,meta=load_model_data('stuff','y_event',name)
        assert len(X)==len(y)==len(meta) and len(X)>0
        assert not X.isna().any().any()
        assert not any(c.endswith('_anon_id') or c.startswith('y_') for c in X)
        print(name,len(X),'usable stuff/event rows')
    for family,target in [('location','y_chase_given_outside'),('pitching','y_hard_contact_bip')]:
        X,y,meta=load_model_data(family,target,'validation')
        assert len(X)>0 and len(X)==len(y)==len(meta)
        assert y.isin([0,1]).all()
        print(family,target,len(X),'usable validation rows')
print(json.dumps({'run':run.name,'checks':'PASS','table_contract_checks':len(checks),'artifact_hashes_verified':len(manifest['outputs'])}))
