"""Small read-only API. Predictors are explicit allowlists, never all columns."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if sys.prefix == sys.base_prefix and (ROOT / '.analysis_deps').exists():
    sys.path.insert(0, str(ROOT / '.analysis_deps'))
import duckdb
import pandas as pd


def current_run():
    pointer = ROOT / 'data' / 'CURRENT'
    if not pointer.exists():
        raise FileNotFoundError('Run python scripts/prepare_data.py first.')
    name = pointer.read_text(encoding='utf-8').strip()
    if not re.fullmatch('[0-9a-f]{16}', name):
        raise ValueError('Invalid run pointer')
    path = ROOT / 'data' / 'runs' / name
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['status'] != 'validated':
        raise ValueError('Run has not passed validation')
    return path


def connect():
    """Portable materialized DuckDB database; no absolute path dependencies."""
    return duckdb.connect(str(current_run() / 'diablos.duckdb'), read_only=True)


def load_model_data(feature_set='stuff', target='y_event', split='train', protocol='season'):
    """Return X, y, metadata. Complete eligible rows only; no imputation or fitting.

    The separate pitcher protocol spans years and is NOT a temporal test.
    Arsenal is deliberately excluded from default matrices: 2024 has no history.
    """
    features = json.loads((current_run() / 'feature_sets.json').read_text(encoding='utf-8'))
    if feature_set not in ('stuff','location','pitching'):
        raise ValueError('feature_set must be stuff, location or pitching')
    if protocol not in ('season','pitcher') or split not in ('train','validation','test'):
        raise ValueError('Unsupported protocol or split')
    with connect() as db:
        targets = {r[1] for r in db.execute("PRAGMA table_info('targets')").fetchall() if r[1].startswith('y_')}
        if target not in targets: raise ValueError('Unknown target')
        cols = features[feature_set]
        quoted = ', '.join('"'+c+'"' for c in cols)
        eligibility = {'stuff':'eligible_stuff_default','location':'eligible_event AND eligible_location','pitching':'eligible_pitching_default'}[feature_set]
        sql = f'SELECT {quoted}, "{target}", pitch_uid, year, game_anon_id, pitcher_anon_id FROM model_base WHERE {protocol}_split = ? AND ({eligibility}) AND "{target}" IS NOT NULL'
        frame = db.execute(sql,[split]).df()
    frame = frame.dropna(subset=cols).reset_index(drop=True)
    return frame[cols], frame[target], frame[['pitch_uid','year','game_anon_id','pitcher_anon_id']]


def load_arsenal():
    """Explicit opt-in historical covariates, with status and source year."""
    return pd.read_parquet(current_run() / 'arsenal_features.parquet')
