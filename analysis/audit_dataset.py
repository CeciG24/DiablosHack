import sys, json, zipfile, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.analysis_deps'))
import pandas as pd
import numpy as np

root = Path(__file__).resolve().parents[1]
out = root / 'analysis'
with zipfile.ZipFile(root / 'Diablos - Hackathon 2026 (1).zip') as z:
    for suffix in ('.parquet', '.csv'):
        name = next(n for n in z.namelist() if n.endswith(suffix))
        dest = out / Path(name).name
        if not dest.exists():
            with z.open(name) as src, dest.open('wb') as dst:
                shutil.copyfileobj(src, dst)
d = pd.read_parquet(out / 'stuff_model_df.parquet')
print('SHAPE', d.shape, flush=True)
profile = pd.DataFrame({'dtype':d.dtypes.astype(str), 'missing':d.isna().sum(), 'missing_pct':d.isna().mean()*100, 'unique':d.nunique()})
profile.to_csv(out / 'column_profile.csv')
print(profile.to_string(), flush=True)
result = {'rows':len(d), 'columns':list(d.columns), 'duplicate_uid':int(d.PitchUID.duplicated().sum()), 'categories':{}}
for c in d:
    if d[c].nunique() <= 40:
        result['categories'][c] = {str(k):int(v) for k,v in d[c].value_counts(dropna=False).items()}
print('CATEGORIES',json.dumps(result['categories'],ensure_ascii=False),flush=True)
nums = d.select_dtypes(include='number')
nums.describe(percentiles=[.01,.5,.99]).T.to_csv(out / 'numeric_profile.csv')
for keys in [['year'], ['altitude_category'], ['year','altitude_category'], ['AutoPitchType']]:
    g=d.groupby(keys,dropna=False,observed=True)
    t=g.agg(pitches=('PitchUID','size'),pitchers=('pitcher_anon_id','nunique'),games=('game_anon_id','nunique'),swing=('is_swing','sum'),whiff=('is_whiff','sum'),bip=('is_ball_in_play','sum'),hr=('home_run','sum'),velo=('RelSpeed','mean'),ivb=('InducedVertBreak','mean'))
    t['whiff_per_swing']=t.whiff/t.swing
    t['hr_per_bip']=t.hr/t.bip
    t.to_csv(out / ('by_'+'_'.join(keys)+'.csv'))
    print('GROUP',keys,'\n',t.to_string(),flush=True)
result['ids']={c:int(d[c].nunique()) for c in ['pitcher_anon_id','batter_anon_id','game_anon_id']}
result['pitchers_multi_altitude']=int((d.groupby('pitcher_anon_id',observed=True).altitude_category.nunique()>1).sum())
result['games_multi_altitude']=int((d.groupby('game_anon_id',observed=True).altitude_category.nunique()>1).sum())
result['pitcher_sample_quantiles']=d.groupby('pitcher_anon_id',observed=True).size().quantile([0,.1,.25,.5,.75,.9,1]).to_dict()
bip=d.is_ball_in_play.eq(1)
result['bip_missing']={c:float(d.loc[bip,c].isna().mean()) for c in ['ExitSpeed','Angle','hit_type','play_result','Distance']}
result['checks']={
 'whiff_vs_swinging_flag':int((d.is_whiff!=d.is_swinging_strike).sum()),
 'whiff_without_swing':int((d.is_whiff.eq(1)&~d.is_swing.eq(1)).sum()),
 'zone_flags_not_complement':int((d.in_strike_zone.astype(int)+d.outside_strike_zone.astype(int)!=1).sum()),
 'swing_not_whiff_plus_contact':int((d.is_swing.astype(int)!=d.is_whiff.astype(int)+d.is_contact.astype(int)).sum()),
 'count_mismatch':int((d['count'].astype(str)!=(d.Balls.astype(int).astype(str)+'-'+d.Strikes.astype(int).astype(str))).sum())}
for c in ['RelSpeed','SpinRate','InducedVertBreak','HorzBreak','Extension','PlateLocHeight','PlateLocSide','ExitSpeed','Angle']:
    result.setdefault('numeric',{})[c]=d[c].describe(percentiles=[.01,.5,.99]).to_dict()
(out/'audit_summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
print('SUMMARY',json.dumps({k:v for k,v in result.items() if k not in ['categories','columns']},ensure_ascii=False),flush=True)
extra={}
ev=pd.to_numeric(d.EffectiveVelo,errors='coerce')
extra['EffectiveVelo_non_numeric']=int(ev.isna().sum())
extra['EffectiveVelo_bad_values']=d.loc[ev.isna(),'EffectiveVelo'].value_counts().to_dict()
extra['extension_negative']=int(d.Extension.lt(0).sum())
extra['extension_above_10']=int(d.Extension.gt(10).sum())
extra['height_zero']=int(d.PlateLocHeight.eq(0).sum())
extra['both_location_zero']=int((d.PlateLocHeight.eq(0)&d.PlateLocSide.eq(0)).sum())
extra['outs_3']=int(d.Outs.eq(3).sum())
extra['hbp_pitchcall']=int(d.PitchCall.eq('HitByPitch').sum())
extra['contact_inconsistency_calls']=d.loc[d.is_swing!=d.is_whiff+d.is_contact,'PitchCall'].value_counts().to_dict()
extra['bip_inconsistent_calls']=d.loc[d.is_ball_in_play.ne(d.PitchCall.eq('InPlay').astype(int)),'PitchCall'].value_counts().to_dict()
extra['chase_mismatch']=int(d.swung_outside_strike_zone.ne(d.is_swing*d.outside_strike_zone).sum())
extra['missing_pitcher_by_year']=d.groupby('year').pitcher_anon_id.apply(lambda s:int(s.isna().sum())).to_dict()
extra['game_year_conflicts']=int((d.groupby('game_anon_id').year.nunique()>1).sum())
core=['RelSpeed','SpinRate','SpinAxis','RelHeight','RelSide','Extension','InducedVertBreak','HorzBreak']
extra['core_complete']=int(d[core].notna().all(axis=1).sum())
known=d.dropna(subset=['pitcher_anon_id'])
sets={int(y):set(x.pitcher_anon_id) for y,x in known.groupby('year')}
extra['new_pitchers_2026']=len(sets[2026]-sets[2025]-sets[2024])
extra['new_pitcher_pitches_2026']=int((d.year.eq(2026)&d.pitcher_anon_id.isin(sets[2026]-sets[2025]-sets[2024])).sum())
g=d.groupby(['pitcher_anon_id','year','AutoPitchType','altitude_category'],observed=True).agg(n=('PitchUID','size'),ivb=('InducedVertBreak','mean'),v=('RelSpeed','mean'))
p=g.unstack('altitude_category')
ok=p[('n','Extreme Altitude')].ge(30)&p[('n','No Altitude')].ge(30)
p=p.loc[ok]
delta=p[('ivb','Extreme Altitude')]-p[('ivb','No Altitude')]
paired=pd.DataFrame({'ivb_delta_extreme_minus_no':delta,'velo_delta':p[('v','Extreme Altitude')]-p[('v','No Altitude')],'n_extreme':p[('n','Extreme Altitude')],'n_no':p[('n','No Altitude')]})
paired.to_csv(out/'matched_pitcher_year_type.csv')
extra['matched_groups']=len(paired)
extra['matched_by_type']=paired.groupby('AutoPitchType',observed=True).agg(groups=('ivb_delta_extreme_minus_no','size'),median_ivb_delta=('ivb_delta_extreme_minus_no','median'),median_velo_delta=('velo_delta','median')).reset_index().to_dict('records')
(out/'additional_checks.json').write_text(json.dumps(extra,indent=2,default=str),encoding='utf-8')
print('EXTRA',json.dumps(extra,default=str),flush=True)
