"""Training-only trajectory audit and regularized historical repertoire."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from modeling.datasets import require_unique, ids_hash

TYPES = ['Four-Seam', 'Sinker', 'Cutter', 'Changeup', 'Splitter', 'Slider', 'Curveball', 'Other']
PHYS = ['rel_speed', 'induced_vert_break', 'horz_break', 'rel_height', 'rel_side']
COEFFICIENTS = ['pitch_trajectory_'+axis+'c'+str(i) for axis in 'xyz' for i in range(3)]
POINTS = ['geo_'+str(plane)+'_'+axis for plane in (40,20,8) for axis in ('height','side')]
REGULARIZED = [f'ars_{i}_{suffix}' for i in range(8) for suffix in ('speed','ivb','hb','release','usage','reliability')]+['ars_sd_'+x for x in PHYS]+['ars_history_log_n']
GEOMETRY = ['geometry_valid','geo_reference_reliability','geo_distance_40','geo_distance_20','geo_distance_8','geo_late_minus_early']


def trajectory(rows, cfg, audit=False):
    if audit and (rows.empty or not rows.year.eq(2024).all()):
        raise PermissionError('Trajectory convention audit requires 2024 only')
    out = rows.copy()
    t = pd.to_numeric(out.zone_time, errors='coerce').to_numpy(float)
    coef = {axis:out[['pitch_trajectory_'+axis+'c'+str(i) for i in range(3)]].to_numpy(float) for axis in 'xyz'}
    endpoint = {axis:a[:,0]+a[:,1]*t+a[:,2]*t*t for axis,a in coef.items()}
    errors = {
        'plate_height':np.abs(endpoint['y']-out.plate_loc_height),
        'plate_side':np.abs(-endpoint['z']-out.plate_loc_side),
        'plate_longitudinal':np.abs(endpoint['x']-17/12),
        'release_height':np.abs(coef['y'][:,0]-out.rel_height),
        'release_side':np.abs(-coef['z'][:,0]-out.rel_side),
        'release_longitudinal':np.abs(coef['x'][:,0]-(60.5-out.extension)),
    }
    report = {name:dict(n_finite=int(np.isfinite(v).sum()), median=float(np.nanmedian(v)), p95=float(np.nanquantile(v,.95))) for name,v in errors.items()}
    if audit and any(v['median']>cfg['trajectory_median_error_max_feet'] or v['p95']>cfg['trajectory_p95_error_max_feet'] for v in report.values()):
        raise ValueError('Trajectory convention audit failed; geometry must not be used')
    valid = np.isfinite(out[COEFFICIENTS].to_numpy(float)).all(axis=1) & np.isfinite(t) & (t>.2) & (t<1)
    for v in errors.values():
        valid &= np.isfinite(v) & (v<=cfg['trajectory_row_error_max_feet'])
    x=coef['x']
    for plane in cfg['trajectory_planes_feet']:
        # Bisection avoids unstable quadratic roots and handles nearly linear fits.
        lo=np.zeros(len(out)); hi=t.copy()
        valid &= (x[:,0]>plane) & (endpoint['x']<plane) & (x[:,1]<0) & (x[:,1]+2*x[:,2]*t<0)
        for _ in range(35):
            mid=(lo+hi)/2
            before=x[:,0]+x[:,1]*mid+x[:,2]*mid*mid>plane
            lo=np.where(before,mid,lo); hi=np.where(before,hi,mid)
        mid=(lo+hi)/2
        for axis,label,sign in [('y','height',1),('z','side',-1)]:
            a=coef[axis]
            out[f'geo_{plane}_{label}']=sign*(a[:,0]+a[:,1]*mid+a[:,2]*mid*mid)
    out['geometry_valid']=valid.astype(float)
    out.loc[~valid,POINTS]=np.nan
    return out, dict(convention='x longitudinal, y height, -z side; c0+c1*t+c2*t^2', errors_feet=report,
                     n=len(out),valid=int(valid.sum()),coverage=float(valid.mean()))


class Repertoire:
    def __init__(self, strength=30):
        if not np.isfinite(strength) or strength<=0: raise ValueError('Positive prior strength required')
        self.strength=float(strength)

    def fit(self, history):
        require_unique(history)
        if history.empty or not history.year.eq(2024).all(): raise PermissionError('History must be exclusively 2024')
        h=history.loc[history.pitcher_anon_id.notna() & history.pitcher_throws.isin(['Left','Right']) & history.auto_pitch_type.isin(TYPES) & history[PHYS].notna().all(axis=1)].copy()
        if h.empty: raise ValueError('No valid physical history')
        # All numeric values here were cleaned by the data contract.
        self.stats=h.groupby(['pitcher_anon_id','pitcher_throws','auto_pitch_type'])[PHYS].agg(['count','mean',lambda x:float(np.mean(x*x))])
        self.stats.columns=[a+'_'+{'count':'n','mean':'mean','<lambda_0>':'second'}[b] for a,b in self.stats.columns]
        self.stats=self.stats.reset_index()
        self.priors=h.groupby(['pitcher_throws','auto_pitch_type'])[PHYS].agg(['mean',lambda x:float(np.mean(x*x))])
        self.priors.columns=[a+'_'+{'mean':'mean','<lambda_0>':'second'}[b] for a,b in self.priors.columns]
        self.priors=self.priors.reset_index()
        global_prior={col+'_mean':float(h[col].mean()) for col in PHYS}
        global_prior.update({col+'_second':float((h[col]**2).mean()) for col in PHYS})
        self.global_prior=global_prior
        self.counts=h.groupby(['pitcher_anon_id','pitcher_throws','auto_pitch_type']).size().rename('n').reset_index()
        self.usages=h.groupby(['pitcher_throws','auto_pitch_type']).size().rename('n').reset_index()
        self.usages['usage']=self.usages.n/self.usages.groupby('pitcher_throws').n.transform('sum')
        fb=h.loc[h.auto_pitch_type.isin(['Four-Seam','Sinker']) & h.geometry_valid.eq(1)]
        self.geo=fb.groupby(['pitcher_anon_id','pitcher_throws'])[POINTS].mean().reset_index()
        self.geo['geo_n']=fb.groupby(['pitcher_anon_id','pitcher_throws']).size().to_numpy()
        self.geo_prior=fb.groupby('pitcher_throws')[POINTS].mean().reset_index()
        if set(self.geo_prior.pitcher_throws)!={'Left','Right'}: raise ValueError('Geometry priors need both hands')
        self.metadata=dict(history_year=2024,history_n=len(h),history_ids_sha256=ids_hash(h.pitch_uid.tolist()),strength=self.strength)
        return self

    def transform(self, rows, cold_start=False):
        if not rows.pitcher_throws.isin(['Left','Right']).all(): raise ValueError('Unknown throwing hand')
        # Index-based joins preserve caller order and duplicate pitch identifiers.
        out=rows.reset_index(drop=True).copy()
        ids=out.get('pitcher_anon_id',pd.Series('',index=out.index)).fillna('').astype(str)
        if cold_start: ids=pd.Series('',index=out.index)
        keys=pd.DataFrame(dict(pitcher_anon_id=ids,pitcher_throws=out.pitcher_throws))
        total_table=self.counts.groupby(['pitcher_anon_id','pitcher_throws']).n.sum().rename('total').reset_index()
        total=keys.merge(total_table,how='left',on=['pitcher_anon_id','pitcher_throws'],validate='many_to_one').total.fillna(0).to_numpy()
        own_variance={c:np.zeros(len(out)) for c in PHYS}
        for i,typ in enumerate(TYPES):
            group=keys.merge(self.stats.loc[self.stats.auto_pitch_type.eq(typ)].drop(columns='auto_pitch_type'),how='left',on=['pitcher_anon_id','pitcher_throws'],validate='many_to_one')
            prior=keys[['pitcher_throws']].merge(self.priors.loc[self.priors.auto_pitch_type.eq(typ)].drop(columns='auto_pitch_type'),how='left',on='pitcher_throws',validate='many_to_one')
            n=group.rel_speed_n.fillna(0).to_numpy(); weight=n/(n+self.strength)
            means={}
            for c in PHYS:
                mu=prior[c+'_mean'].fillna(self.global_prior[c+'_mean']).to_numpy()
                second=prior[c+'_second'].fillna(self.global_prior[c+'_second']).to_numpy()
                means[c]=weight*group[c+'_mean'].fillna(0).to_numpy()+(1-weight)*mu
                second=weight*group[c+'_second'].fillna(0).to_numpy()+(1-weight)*second
                mask=out.auto_pitch_type.eq(typ).to_numpy()
                own_variance[c][mask]=np.maximum(0,second-means[c]**2)[mask]
            for c,suffix in [('rel_speed','speed'),('induced_vert_break','ivb'),('horz_break','hb')]:
                out[f'ars_{i}_{suffix}']=out[c].to_numpy()-means[c]
            out[f'ars_{i}_release']=np.hypot(out.rel_height-means['rel_height'],out.rel_side-means['rel_side'])
            usage=keys[['pitcher_throws']].merge(self.usages.loc[self.usages.auto_pitch_type.eq(typ),['pitcher_throws','usage']],how='left',on='pitcher_throws',validate='many_to_one').usage.fillna(0).to_numpy()
            out[f'ars_{i}_usage']=(n+self.strength*usage)/(total+self.strength)
            out[f'ars_{i}_reliability']=weight
        for c in PHYS: out['ars_sd_'+c]=np.sqrt(own_variance[c])
        out['ars_history_log_n']=np.log1p(total)
        out['history_n']=total.astype(int)
        out['history_status']=np.where(total>0,'regularized_2024_history','group_prior_only')
        # Geometric reference = historical fastball pool; no sequential interpretation.
        ref=keys.merge(self.geo,how='left',on=['pitcher_anon_id','pitcher_throws'],validate='many_to_one')
        prior=keys[['pitcher_throws']].merge(self.geo_prior,how='left',on='pitcher_throws',validate='many_to_one')
        gn=ref.geo_n.fillna(0).to_numpy(); w=gn/(gn+self.strength)
        valid=out.get('geometry_valid',pd.Series(0.,index=out.index)).eq(1).to_numpy()
        out['geometry_valid']=valid.astype(float)
        out['geo_reference_reliability']=np.where(valid,w,0.)
        for plane in (40,20,8):
            delta=[]
            for axis in ('height','side'):
                col=f'geo_{plane}_{axis}'
                mean=w*ref[col].fillna(0).to_numpy()+(1-w)*prior[col].to_numpy()
                delta.append(out.get(col,pd.Series(np.nan,index=out.index)).to_numpy()-mean)
            out['geo_distance_'+str(plane)]=np.where(valid,np.hypot(*delta),0.)
        out['geo_late_minus_early']=out.geo_distance_8-out.geo_distance_40
        out[POINTS]=out.reindex(columns=POINTS).fillna(0)
        if not np.isfinite(out[REGULARIZED+GEOMETRY].to_numpy(float)).all(): raise ValueError('Non-finite arsenal features')
        return out

    def save(self, folder):
        from experiments.phase9 import write
        folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
        for name in ('stats','priors','counts','usages','geo','geo_prior'): getattr(self,name).to_parquet(folder/(name+'.parquet'),index=False)
        write(folder/'metadata.json',dict(self.metadata,global_prior=self.global_prior))

    @classmethod
    def load(cls, folder):
        folder=Path(folder); m=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
        if m['history_year']!=2024: raise ValueError('Future history artifact')
        obj=cls(m['strength']); obj.metadata=m; obj.global_prior=m['global_prior']
        for name in ('stats','priors','counts','usages','geo','geo_prior'): setattr(obj,name,pd.read_parquet(folder/(name+'.parquet')))
        return obj
