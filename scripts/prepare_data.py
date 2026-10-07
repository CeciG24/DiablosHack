"""Reproducible, local-only data preparation. Run from any working directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Optional task-local dependencies; normal installations use requirements.txt.
if sys.prefix == sys.base_prefix and (ROOT / '.analysis_deps').exists():
    sys.path.insert(0, str(ROOT / '.analysis_deps'))
import duckdb
import numpy as np
import pandas as pd
import pyarrow

CONFIG = ROOT / 'config' / 'data_contract.json'
CORE = ['rel_speed', 'spin_rate', 'spin_axis', 'rel_height', 'rel_side', 'extension', 'induced_vert_break', 'horz_break']
EVENT_MAP = {
    'BallCalled': 'ball', 'BallinDirt': 'ball', 'BallIntentional': 'ball',
    'StrikeCalled': 'called_strike', 'StrikeSwinging': 'whiff',
    'FoulBall': 'foul', 'FoulBallFieldable': 'foul', 'FoulBallNotFieldable': 'foul',
    'InPlay': 'in_play', 'HitByPitch': 'hit_by_pitch',
}
BIP_RESULTS = {'Out', 'Single', 'Double', 'Triple', 'HomeRun', 'Error', 'FieldersChoice', 'Sacrifice'}
SWING_EVENTS = {'whiff', 'foul', 'in_play'}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def snake(name):
    special = {'PitchUID': 'pitch_uid', 'KorBB': 'kor_bb', 'Top/Bottom': 'half_inning'}
    if name in special:
        return special[name]
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', name).lower()


def bucket(value, seed, n=10000):
    return int(hashlib.sha256(f'{seed}|{value}'.encode()).hexdigest()[:16], 16) % n


def prepare_frame(raw, cfg):
    """Keep every pitch; source columns survive in raw Parquet, never mutated."""
    clean = raw.rename(columns={c: snake(c) for c in raw}).copy()
    clean.insert(0, 'source_row_number', np.arange(1, len(clean) + 1))
    clean['effective_velo'] = pd.to_numeric(clean.effective_velo, errors='coerce')
    for c in clean.select_dtypes(include=['object', 'string', 'category']):
        clean[c] = clean[c].astype('string').str.strip().replace('', pd.NA)
    clean['pitcher_throws'] = clean.pitcher_throws.where(clean.pitcher_throws.isin(['Right', 'Left']))
    clean['batter_side'] = clean.batter_side.where(clean.batter_side.isin(['Right', 'Left']))
    issues = []
    flags = pd.DataFrame({'pitch_uid': clean.pitch_uid})

    def flag(code, mask, severity, action, field):
        mask = mask.fillna(False).astype(bool)
        flags[code] = mask
        if mask.any():
            issues.append(pd.DataFrame({'pitch_uid': clean.loc[mask, 'pitch_uid'], 'rule': code,
                                       'field': field, 'severity': severity, 'action': action}))

    numeric = clean.select_dtypes(include='number').columns
    for c in numeric:
        mask = ~np.isfinite(clean[c].to_numpy(dtype=float)) & clean[c].notna().to_numpy()
        if mask.any():
            flag(f'nonfinite_{c}', pd.Series(mask,index=clean.index), 'review', 'set_clean_null', c)
            clean.loc[mask, c] = np.nan
    for c, (lo, hi) in {**cfg['physical_review_bounds'], **cfg['contact_review_bounds']}.items():
        bad = clean[c].notna() & ~clean[c].between(lo, hi)
        flag(f'out_of_bounds_{c}', bad, 'review', 'set_clean_null', c)
        clean.loc[bad, c] = np.nan
    for c, allowed in [('balls', [0,1,2,3]), ('strikes',[0,1,2]), ('outs',[0,1,2])]:
        bad = clean[c].notna() & ~clean[c].isin(allowed)
        flag(f'invalid_{c}', bad, 'review', 'set_clean_null', c)
        clean.loc[bad,c] = np.nan
        clean[c] = clean[c].astype('Int8')
    clean['year'] = clean.year.astype('Int16')
    for c in ['pitcher_anon_id', 'batter_anon_id', 'altitude_category']:
        flag(f'missing_{c}', clean[c].isna(), 'warning', 'retain_with_eligibility_mask', c)
    flag('unknown_pitcher_hand', clean.pitcher_throws.isna(), 'warning', 'keep_null', 'pitcher_throws')
    flag('unknown_batter_side', clean.batter_side.isna(), 'warning', 'keep_null', 'batter_side')
    flag('zero_plate_height', clean.plate_loc_height.eq(0), 'review', 'exclude_location_default', 'plate_loc_height')
    flag('rare_source_pitch_label', clean.auto_pitch_type.isin(['OneSeamFastBall','TwoSeamFastBall','Knuckleball','Other']), 'warning', 'retain_no_automatic_relabel', 'auto_pitch_type')

    call = clean.pitch_call
    candidate = call.map(EVENT_MAP).astype('string')
    # The 450 contradictions can reflect more than a simple flag bug; quarantine labels.
    contact_conflict = call.eq('StrikeSwinging') & clean.is_contact.eq(1)
    bip_conflict = clean.is_ball_in_play.ne(call.eq('InPlay').astype(int))
    terminal_conflict = (call.eq('HitByPitch') & clean.play_result.ne('HitByPitch')) | (call.eq('StrikeCalled') & clean.play_result.eq('Walk'))
    strong_conflict = contact_conflict | bip_conflict | terminal_conflict
    flag('whiff_contact_conflict', contact_conflict, 'review', 'null_model_event_labels', 'is_contact')
    flag('bip_flag_conflict', bip_conflict, 'review', 'null_model_event_labels', 'is_ball_in_play')
    flag('terminal_event_conflict', terminal_conflict, 'review', 'null_model_event_labels', 'play_result')
    flag('hbp_source_flag_conflict', clean.is_hit_by_pitch.ne(call.eq('HitByPitch').astype(int)), 'warning', 'rebuild_from_call_unless_strong_conflict', 'is_hit_by_pitch')
    flag('unknown_pitch_call', candidate.isna(), 'review', 'null_model_event_labels', 'pitch_call')
    flag('bip_result_unknown', call.eq('InPlay') & ~clean.play_result.isin(BIP_RESULTS), 'review', 'null_bip_result_labels', 'play_result')
    event = candidate.mask(strong_conflict)
    known = event.notna()
    targets = pd.DataFrame({'pitch_uid':clean.pitch_uid, 'event_candidate':candidate, 'y_event':event})
    for name, positive in [('swing',SWING_EVENTS), ('whiff',{'whiff'}), ('contact',{'foul','in_play'}),
                           ('called_strike',{'called_strike'}), ('ball_in_play',{'in_play'}), ('hit_by_pitch',{'hit_by_pitch'})]:
        targets['y_'+name] = event.isin(positive).astype('Int8').where(known)
    swing = event.isin(SWING_EVENTS)
    bip = event.eq('in_play').fillna(False)
    location_ok = clean.plate_loc_height.notna() & clean.plate_loc_height.gt(0) & clean.plate_loc_side.notna()
    targets['y_whiff_given_swing'] = targets.y_whiff.where(swing)
    targets['y_called_strike_given_take'] = targets.y_called_strike.where(known & ~swing)
    targets['y_chase_given_outside'] = targets.y_swing.where(clean.outside_strike_zone.eq(1) & location_ok)
    valid_ev = bip & clean.exit_speed.notna()
    targets['y_hard_contact_bip'] = clean.exit_speed.ge(cfg['hard_contact_threshold_mph']).astype('Int8').where(valid_ev)
    targets['y_weak_contact_proxy_bip'] = clean.exit_speed.lt(cfg['weak_contact_threshold_mph']).astype('Int8').where(valid_ev)
    targets['y_groundball_bip'] = clean.hit_type.eq('GroundBall').astype('Int8').where(bip & clean.hit_type.isin(['GroundBall','FlyBall','LineDrive','Popup','Bunt']))
    result_ok = bip & clean.play_result.isin(BIP_RESULTS)
    targets['y_home_run_bip'] = clean.play_result.eq('HomeRun').astype('Int8').where(result_ok)
    targets['y_hit_bip'] = clean.play_result.isin(['Single','Double','Triple','HomeRun']).astype('Int8').where(result_ok)
    targets['y_exit_speed_bip'] = clean.exit_speed.where(bip)
    targets['y_launch_angle_bip'] = clean.angle.where(bip)
    targets['event_label_policy'] = 'PitchCall_provisional_v1_conflicts_null'

    flags['eligible_event'] = known
    flags['eligible_physical_complete'] = clean[CORE].notna().all(axis=1) & clean.pitcher_throws.notna()
    flags['eligible_location'] = location_ok & clean.balls.notna() & clean.strikes.notna() & clean.batter_side.notna()
    flags['eligible_grouped_pitcher'] = clean.pitcher_anon_id.notna()
    flags['eligible_environment'] = clean.altitude_category.isin(cfg['altitude_categories'])
    flags['eligible_stuff_default'] = flags.eligible_event & flags.eligible_physical_complete
    flags['eligible_pitching_default'] = flags.eligible_stuff_default & flags.eligible_location & flags.eligible_environment

    features = clean[['pitch_uid','auto_pitch_type','pitcher_throws',*CORE,'plate_loc_height','plate_loc_side','balls','strikes','batter_side','altitude_category']].copy()
    features['spin_axis_sin'] = np.sin(np.deg2rad(features.spin_axis))
    features['spin_axis_cos'] = np.cos(np.deg2rad(features.spin_axis))
    issue_df = pd.concat(issues, ignore_index=True) if issues else pd.DataFrame(columns=['pitch_uid','rule','field','severity','action'])
    return clean, features, targets, flags, issue_df


def make_splits(clean, cfg):
    split = clean[['pitch_uid','year','game_anon_id','pitcher_anon_id','altitude_category']].copy()
    split['season_split'] = split.year.map({cfg['train_year']:'train',cfg['validation_year']:'validation',cfg['test_year']:'test'}).astype('string')
    ids = split.pitcher_anon_id.dropna().unique()
    mapping = {v: ('train' if (b:=bucket(v,cfg['split_seed'])) < 7000 else 'validation' if b < 8500 else 'test') for v in ids}
    split['pitcher_split'] = split.pitcher_anon_id.map(mapping).astype('string').fillna('excluded_missing_pitcher')
    old = set(split.loc[split.year.lt(cfg['test_year']),'pitcher_anon_id'].dropna())
    split['is_unseen_pitcher_test'] = split.year.eq(cfg['test_year']) & split.pitcher_anon_id.notna() & ~split.pitcher_anon_id.isin(old)
    split['game_cv_fold'] = split.game_anon_id.map({v:bucket(v,cfg['split_seed']+'-game',5) for v in split.game_anon_id.unique()}).astype('Int8')
    split['environment_group'] = split.altitude_category.fillna('unknown')
    return split


def make_arsenal(clean, cfg):
    """Prior-season covariates only. 2024 references stay null rather than use future data."""
    outputs, refs = [], []
    for year in sorted(clean.year.unique()):
        hist = clean.loc[clean.year.lt(year) & clean.pitcher_anon_id.notna()]
        current = clean.loc[clean.year.eq(year)]
        counts = hist.groupby(['pitcher_anon_id','auto_pitch_type'],observed=True).size().rename('historical_type_n').reset_index()
        total = hist.groupby('pitcher_anon_id').size().rename('historical_pitcher_n').reset_index()
        valid_fb = hist.auto_pitch_type.isin(cfg['fastball_types']) & hist[['rel_speed','induced_vert_break','horz_break','rel_height','rel_side']].notna().all(axis=1)
        ref = hist.loc[valid_fb].groupby(['pitcher_anon_id','auto_pitch_type'],observed=True).agg(
            fb_n=('pitch_uid','size'), fb_velocity=('rel_speed','mean'),fb_ivb=('induced_vert_break','mean'),
            fb_hb=('horz_break','mean'),fb_release_height=('rel_height','mean'),fb_release_side=('rel_side','mean'),
            source_max_year=('year','max')).reset_index()
        ref = ref.loc[ref.fb_n.ge(cfg['minimum_fastball_reference'])].sort_values(['pitcher_anon_id','fb_n','auto_pitch_type'],ascending=[True,False,True]).drop_duplicates('pitcher_anon_id')
        ref = ref.rename(columns={'auto_pitch_type':'reference_fastball_type'})
        ref['target_year'] = int(year)
        refs.append(ref)
        a = current[['pitch_uid','pitcher_anon_id','auto_pitch_type','rel_speed','induced_vert_break','horz_break','rel_height','rel_side']].merge(ref, on='pitcher_anon_id',how='left',validate='many_to_one')
        a = a.merge(counts,on=['pitcher_anon_id','auto_pitch_type'],how='left',validate='many_to_one').merge(total,on='pitcher_anon_id',how='left',validate='many_to_one')
        a['historical_type_usage'] = a.historical_type_n.fillna(0).div(a.historical_pitcher_n)
        a['velo_diff_vs_fb'] = a.rel_speed-a.fb_velocity
        a['ivb_diff_vs_fb'] = a.induced_vert_break-a.fb_ivb
        a['hb_diff_vs_fb'] = a.horz_break-a.fb_hb
        a['release_distance_vs_fb'] = np.sqrt((a.rel_height-a.fb_release_height)**2+(a.rel_side-a.fb_release_side)**2)
        a['has_prior_fastball_reference'] = a.fb_n.notna()
        a['arsenal_status'] = np.where(a.has_prior_fastball_reference,'prior_season_reference','insufficient_prior_history')
        keep=['pitch_uid','reference_fastball_type','fb_n','source_max_year','historical_pitcher_n','historical_type_n','historical_type_usage','velo_diff_vs_fb','ivb_diff_vs_fb','hb_diff_vs_fb','release_distance_vs_fb','has_prior_fastball_reference','arsenal_status']
        outputs.append(a[keep])
    return pd.concat(outputs,ignore_index=True), pd.concat(refs,ignore_index=True)


FEATURE_SETS = {
    'stuff': ['auto_pitch_type','pitcher_throws','rel_speed','spin_rate','spin_axis_sin','spin_axis_cos','rel_height','rel_side','extension','induced_vert_break','horz_break'],
    'location': ['auto_pitch_type','pitcher_throws','plate_loc_height','plate_loc_side','balls','strikes','batter_side'],
    'pitching': ['auto_pitch_type','pitcher_throws','rel_speed','spin_rate','spin_axis_sin','spin_axis_cos','rel_height','rel_side','extension','induced_vert_break','horz_break','plate_loc_height','plate_loc_side','balls','strikes','batter_side','altitude_category'],
    'arsenal_optional': ['historical_type_usage','velo_diff_vs_fb','ivb_diff_vs_fb','hb_diff_vs_fb','release_distance_vs_fb','has_prior_fastball_reference'],
}

TARGET_DEFINITIONS = {
 'y_event': 'Categoría por pitch según PitchCall; nulo ante evento desconocido o contradicción fuerte.',
 'y_swing': 'Swing por lanzamiento con evento válido. Incluye foul, whiff e in_play.',
 'y_whiff': 'Swing fallido por lanzamiento con evento válido; no es whiff rate dado swing.',
 'y_contact': 'Foul o bola en juego por lanzamiento con evento válido.',
 'y_called_strike': 'Strike cantado por lanzamiento con evento válido.',
 'y_ball_in_play': 'Bola en juego según PitchCall con evento válido.',
 'y_hit_by_pitch': 'Golpeado según PitchCall; no usa la bandera fuente siempre cero; contradicciones quedan nulas.',
 'y_whiff_given_swing': 'Swing fallido; disponible solo en swings válidos.',
 'y_called_strike_given_take': 'Strike cantado; disponible solo en eventos válidos sin swing.',
 'y_chase_given_outside': 'Swing; disponible solo fuera de la zona suministrada y con ubicación utilizable. Zona sin calibración geométrica adicional.',
 'y_hard_contact_bip': 'ExitSpeed >=95 mph entre bolas en juego con velocidad medida; umbral configurado.',
 'y_weak_contact_proxy_bip': 'Proxy provisional ExitSpeed <75 mph entre bolas en juego con velocidad medida; no definición oficial.',
 'y_groundball_bip': 'GroundBall entre bolas en juego con hit_type conocido.',
 'y_home_run_bip': 'HomeRun entre bolas en juego con play_result reconocido.',
 'y_hit_bip': 'Single, Double, Triple o HomeRun entre bolas en juego con play_result reconocido.',
 'y_exit_speed_bip': 'Velocidad de salida en mph solo entre bolas en juego con medición válida.',
 'y_launch_angle_bip': 'Ángulo de salida en grados solo entre bolas en juego con medición válida.'
}


def write_catalog(stage, tables, dictionary):
    source_desc = dict(zip(dictionary.clean_column,dictionary.definition))
    source_units = dict(zip(dictionary.clean_column,dictionary.unit_or_values))
    derived = {
      'source_row_number':'Fila del Parquet fuente, empezando en 1. Es trazabilidad, NO orden temporal.',
      'spin_axis_sin':'Seno del eje de spin convertido de grados a radianes.',
      'spin_axis_cos':'Coseno del eje de spin convertido de grados a radianes.',
      'velo_diff_vs_fb':'Velocidad del pitch menos media de la recta histórica de referencia, mph.',
      'ivb_diff_vs_fb':'IVB del pitch menos media histórica de recta, pulgadas.',
      'hb_diff_vs_fb':'HB del pitch menos media histórica de recta, pulgadas; signo de fuente sin normalizar por mano.',
      'release_distance_vs_fb':'Distancia euclidiana entre release lateral/vertical y media de recta, pies. No mide tunneling real.',
      'historical_type_usage':'Proporción del tipo de pitch en temporadas previas del pitcher; cero si tipo nuevo con historial conocido.',
      'source_max_year':'Último año de los pitches usados en la referencia de recta; siempre anterior al pitch evaluado.',
      'season_split':'train=2024, validation=2025, test=2026.',
      'pitcher_split':'Hash SHA256 estable de pitcher: 70/15/15 esperado por IDs, no porcentaje exacto de pitches. No es temporal.',
      'game_cv_fold':'Fold estable 0 a 4 por partido. Filtrar primero una partición; no mezcla automáticamente temporadas.',
      'event_candidate':'Evento propuesto antes de cuarentena; usar y_event para modelado.',
      'arsenal_status':'Referencia histórica disponible o historial insuficiente. No imputar ausencia como arsenal deficiente.',
    }
    records=[]
    for name,frame in tables.items():
        for col in frame:
            role=('target' if col.startswith('y_') else 'grouping_only' if col.endswith('_id') or col in ['pitch_uid','year','source_row_number']
                  else 'optional_arsenal' if name.startswith('arsenal') else 'quality_only' if name.startswith('quality')
                  else 'split_only' if name=='splits' else 'feature' if name=='features' else 'audit_only')
            records.append({'table':name,'column':col,'dtype':str(frame[col].dtype),'null_count':int(frame[col].isna().sum()),
              'role':role,'feature_sets':','.join(k for k,v in FEATURE_SETS.items() if col in v) if name in ['features','arsenal_features'] else '',
              'unit_or_values':source_units.get(col,''),'definition':TARGET_DEFINITIONS.get(col,derived.get(col,source_desc.get(col,'See docs/DATA_CONTRACT.md and preparation rule '+col)))})
    pd.DataFrame(records).to_csv(stage/'data_catalog.csv',index=False,encoding='utf-8-sig')


def validate_tables(tables, cfg):
    c, f, t, q, sp, a = [tables[n] for n in ['pitches','features','targets','quality_flags','splits','arsenal_features']]
    checks=[]
    def check(name,condition):
        checks.append({'check':name,'passed':bool(condition)})
        if not condition: raise ValueError('Validation failed: '+name)
    check('expected_rows',len(c)==cfg['expected_rows'])
    check('unique_pitch_ids',c.pitch_uid.notna().all() and c.pitch_uid.is_unique)
    ids=set(c.pitch_uid)
    for name,x in [('features',f),('targets',t),('quality_flags',q),('splits',sp),('arsenal_features',a)]:
        check(name+'_one_row_per_pitch',len(x)==len(c) and x.pitch_uid.is_unique and set(x.pitch_uid)==ids)
    check('season_split_complete',sp.season_split.notna().all())
    check('game_does_not_cross_season',sp.groupby('game_anon_id').season_split.nunique().le(1).all())
    check('pitcher_does_not_cross_group_split',sp.dropna(subset=['pitcher_anon_id']).groupby('pitcher_anon_id').pitcher_split.nunique().le(1).all())
    check('no_target_in_features',not any(x.startswith('y_') for x in f))
    check('feature_allowlists_available',set(sum([v for k,v in FEATURE_SETS.items() if k!='arsenal_optional'],[])).issubset(f.columns))
    check('no_ids_or_outcomes_in_allowlists',not any(x in sum(FEATURE_SETS.values(),[]) for x in ['pitch_uid','pitcher_anon_id','batter_anon_id','game_anon_id','exit_speed','pitch_call','play_result','year']))
    check('event_partition_coherent',((t.y_swing == t.y_whiff+t.y_contact).fillna(True)).all())
    check('conditional_whiff_only_swings',t.loc[t.y_swing.ne(1).fillna(True),'y_whiff_given_swing'].isna().all())
    check('conditional_contact_only_bip',t.loc[t.y_ball_in_play.ne(1).fillna(True),'y_hard_contact_bip'].isna().all())
    check('conflicting_events_not_labeled',t.loc[q.whiff_contact_conflict|q.bip_flag_conflict|q.terminal_event_conflict,'y_event'].isna().all())
    j=a.merge(c[['pitch_uid','year']],on='pitch_uid',validate='one_to_one')
    check('arsenal_uses_only_prior_years',(j.source_max_year.isna() | j.source_max_year.lt(j.year)).all())
    check('first_year_arsenal_missing',j.loc[j.year.eq(cfg['train_year']),'has_prior_fastball_reference'].eq(False).all())
    check('finite_features',not np.isinf(f.select_dtypes(include='number').to_numpy(dtype=float)).any())
    check('issues_reference_known_pitches',set(tables['quality_issues'].pitch_uid).issubset(ids))
    return checks


def build_database(run, tables):
    db=duckdb.connect(str(run/'diablos.duckdb'))
    for name in tables:
        path=(run/(name+'.parquet')).as_posix().replace("'","''")
        db.execute(f'CREATE TABLE "{name}" AS SELECT * FROM read_parquet(\'{path}\')')
    db.execute('CREATE TABLE metadata (key VARCHAR PRIMARY KEY, value VARCHAR)')
    db.execute('INSERT INTO metadata VALUES (?, ?)', ['data_contract_version','1.0.0'])
    db.execute('CREATE VIEW model_base AS SELECT f.*, s.year, s.game_anon_id, s.pitcher_anon_id, s.season_split, s.pitcher_split, s.is_unseen_pitcher_test, s.game_cv_fold, t.* EXCLUDE(pitch_uid), q.* EXCLUDE(pitch_uid) FROM features f JOIN splits s USING(pitch_uid) JOIN targets t USING(pitch_uid) JOIN quality_flags q USING(pitch_uid)')
    for name in ['train','validation','test']:
        db.execute(f"CREATE VIEW season_{name} AS SELECT * FROM model_base WHERE season_split='{name}'")
    db.execute('CREATE VIEW unseen_pitcher_test AS SELECT * FROM model_base WHERE is_unseen_pitcher_test')
    db.execute('CREATE VIEW review_queue AS SELECT i.*, p.year, p.game_anon_id, p.pitcher_anon_id FROM quality_issues i JOIN pitches p USING(pitch_uid)')
    db.execute('CREATE VIEW summary_year AS SELECT year, count(*) AS pitches, count(DISTINCT pitcher_anon_id) AS pitchers, count(DISTINCT game_anon_id) AS games FROM pitches GROUP BY year')
    n=db.execute('SELECT count(*) FROM model_base').fetchone()[0]
    if n!=len(tables['pitches']): raise ValueError('SQL join changed row count')
    db.execute('CHECKPOINT'); db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'Diablos - Hackathon 2026 (1).zip')
    args=parser.parse_args()
    cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
    source=args.source.resolve()
    print('Verifying source archive',flush=True)
    source_hash=sha256(source)
    identity=hashlib.sha256((source_hash+sha256(CONFIG)+sha256(__file__)+pd.__version__+pyarrow.__version__+duckdb.__version__+np.__version__).encode()).hexdigest()[:16]
    rawdir=ROOT/'data'/'raw'/source_hash[:16]; rawdir.mkdir(parents=True,exist_ok=True)
    rawfiles={}
    with zipfile.ZipFile(source) as z:
        for suffix in ['.parquet','.csv']:
            names=[n for n in z.namelist() if n.endswith(suffix)]
            if len(names)!=1: raise ValueError('Expected exactly one '+suffix)
            name=names[0]; destination=rawdir/Path(name).name
            # Reading to EOF validates ZIP CRC. Replace only this pipeline-owned extraction.
            tmp=destination.with_suffix(destination.suffix+'.tmp')
            with z.open(name) as a,tmp.open('wb') as b: shutil.copyfileobj(a,b,8*1024*1024)
            tmp.replace(destination)
            rawfiles[destination.name]={'path':str(destination.relative_to(ROOT)), 'sha256':sha256(destination)}
    rawpath=rawdir/'stuff_model_df.parquet'
    raw=pd.read_parquet(rawpath)
    if len(raw)!=cfg['expected_rows'] or len(raw.columns)!=cfg['expected_columns']:
        raise ValueError('Source shape differs from contract. Review before changing config.')
    if raw.PitchUID.isna().any() or not raw.PitchUID.is_unique: raise ValueError('Invalid source key')
    source_dictionary=pd.read_csv(rawdir/'stuff_plus_data_dictionary.csv')
    if set(source_dictionary.column_name)!=set(raw.columns): raise ValueError('Source dictionary/schema mismatch')
    if set(raw.year.unique())!={cfg['train_year'],cfg['validation_year'],cfg['test_year']}: raise ValueError('Unexpected seasons')
    if not set(raw.altitude_category.dropna()).issubset(cfg['altitude_categories']): raise ValueError('Unknown altitude category')
    print(f'Preparing {len(raw):,} pitches',flush=True)
    clean, features, targets, quality, issues=prepare_frame(raw,cfg)
    splits=make_splits(clean,cfg)
    arsenal, references=make_arsenal(clean,cfg)
    tables={'pitches':clean,'features':features,'targets':targets,'quality_flags':quality,'quality_issues':issues,
            'splits':splits,'arsenal_features':arsenal,'arsenal_references':references}
    checks=validate_tables(tables,cfg)
    rundir=ROOT/'data'/'runs'/identity
    if rundir.exists():
        manifest_path=rundir/'manifest.json'
        if not manifest_path.exists(): raise ValueError('Existing incomplete run; retain it and investigate: '+str(rundir))
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        for name,info in manifest['outputs'].items():
            if sha256(rundir/name)!=info['sha256']: raise ValueError('Existing run checksum mismatch: '+name)
        (ROOT/'data'/'CURRENT').write_text(identity,encoding='utf-8')
        print('Existing verified run reused: '+identity,flush=True)
        return
    stage=rundir.with_name(identity+'.building')
    stage.mkdir(parents=True,exist_ok=False)
    for name,table in tables.items():
        table.to_parquet(stage/(name+'.parquet'),index=False,compression='zstd')
    print('Building portable SQL database',flush=True)
    build_database(stage,tables)
    dictionary=pd.read_csv(rawdir/'stuff_plus_data_dictionary.csv')
    dictionary.insert(1,'clean_column',dictionary.column_name.map(snake))
    dictionary.to_csv(stage/'source_dictionary.csv',index=False,encoding='utf-8-sig')
    write_catalog(stage,tables,dictionary)
    diagnostics=quality.merge(clean[['pitch_uid','year','altitude_category','auto_pitch_type']],on='pitch_uid',validate='one_to_one')
    for group in ['year','altitude_category','auto_pitch_type']:
        cols=[c for c in quality if c.startswith('eligible_')]
        rates=diagnostics.groupby(group,dropna=False,observed=True)[cols].mean().add_suffix('_rate')
        rates.insert(0,'pitches',diagnostics.groupby(group,dropna=False,observed=True).size())
        rates.to_csv(stage/('quality_by_'+group+'.csv'))
    pd.DataFrame({'column':clean.columns,'dtype':clean.dtypes.astype(str).values,'missing':clean.isna().sum().values,'missing_pct':clean.isna().mean().values*100}).to_csv(stage/'clean_column_profile.csv',index=False)
    issues.groupby(['rule','severity','action']).size().rename('issue_count').reset_index().to_csv(stage/'quality_summary.csv',index=False)
    target_profile=[]
    for col in targets:
        if col.startswith('y_'):
            x=targets[col]
            target_profile.append({'target':col,'eligible_rows':int(x.notna().sum()),'null_rows':int(x.isna().sum()),'positives':int(x.eq(1).sum()) if col not in ['y_event','y_exit_speed_bip','y_launch_angle_bip'] else None})
    pd.DataFrame(target_profile).to_csv(stage/'target_profile.csv',index=False)
    dump(stage/'feature_sets.json',FEATURE_SETS)
    dump(stage/'validation_checks.json',checks+[{'check':'sql_model_base_row_count','passed':True}])
    summary={
      'rows':len(clean),'raw_columns':len(raw.columns),'clean_columns':len(clean.columns),'pitchers':int(clean.pitcher_anon_id.nunique()),'games':int(clean.game_anon_id.nunique()),
      'season_counts':splits.season_split.value_counts().to_dict(),'pitcher_split_counts':splits.pitcher_split.value_counts().to_dict(),
      'eligibility':{c:int(quality[c].sum()) for c in quality if c.startswith('eligible_')},
      'issues':issues.rule.value_counts().to_dict(),'pitches_with_issues':int(issues.pitch_uid.nunique()),
      'event_counts':targets.y_event.value_counts(dropna=False).astype(int).rename(index=lambda x:str(x)).to_dict(),
      'unseen_pitcher_test_rows':int(splits.is_unseen_pitcher_test.sum()),
      'arsenal_reference_coverage':arsenal.merge(clean[['pitch_uid','year']],on='pitch_uid').groupby('year').has_prior_fastball_reference.agg(['sum','count']).reset_index().to_dict('records'),
      'validation_check_count':len(checks)+1,
    }
    dump(stage/'summary.json',summary)
    outputs={p.name:{'sha256':sha256(p),'bytes':p.stat().st_size} for p in stage.iterdir() if p.is_file()}
    manifest={'run_id':identity,'created_utc':datetime.now(timezone.utc).isoformat(),'source_zip':source.name,'source_zip_sha256':source_hash,
      'raw_files':rawfiles,'config_sha256':sha256(CONFIG),'pipeline_sha256':sha256(__file__),
      'versions':{'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'pyarrow':pyarrow.__version__,'duckdb':duckdb.__version__},
      'outputs':outputs,'status':'validated'}
    dump(stage/'manifest.json',manifest)
    # Publish only after all data, SQL joins, contracts and reports passed.
    stage.rename(rundir)
    pointer=ROOT/'data'/'CURRENT.tmp'; pointer.write_text(identity,encoding='utf-8'); pointer.replace(ROOT/'data'/'CURRENT')
    print(json.dumps({'run_id':identity,'summary':summary},ensure_ascii=False,default=str),flush=True)


if __name__=='__main__': main()
