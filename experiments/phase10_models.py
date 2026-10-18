"""F10 fixed-budget event and movement models; no review-based selection."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from modeling.models import TabularEventModel, BACKEND_VERSION
from modeling.arsenal import ArsenalEventModel
from modeling.datasets import STUFF, require_unique, ids_hash, sha256_file
from modeling.baselines import CLASSES
from experiments.phase9 import FEATURES as F9_FEATURES
from experiments.phase10_features import REGULARIZED, GEOMETRY, POINTS

EVENT_FEATURES = {'base':F9_FEATURES['context_physics'],
                  'regularized':F9_FEATURES['context_physics']+REGULARIZED,
                  'trajectory':F9_FEATURES['context_physics']+REGULARIZED+POINTS+['geometry_valid'],
                  'geometry':F9_FEATURES['context_physics']+REGULARIZED+POINTS+GEOMETRY,
                  'environment':F9_FEATURES['context_physics']+REGULARIZED+POINTS+GEOMETRY+['altitude_category']}
MOVEMENT_FEATURES=[c for c in STUFF if c not in ('induced_vert_break','horz_break')]


class EventModel(TabularEventModel):
    def __init__(self, variant, seed=20260929, threads=4):
        super().__init__(seed,threads,'stuff','A')
        self.variant=variant; self.protocol='C'; self.with_arsenal=variant!='base'
        self.features=EVENT_FEATURES[variant].copy()
        self.categorical=[c for c in self.features if c in ['auto_pitch_type','pitcher_throws','batter_side','altitude_category']]
        self.numeric=[c for c in self.features if c not in self.categorical]

    def fit_f10(self, rows, cfg, smoke=False):
        ArsenalEventModel.fit(self,rows,cfg['parameters'],20 if smoke else cfg['event_rounds'])
        self.metadata.update(f10_variant=self.variant,f10_version=cfg['version'])
        return self

    @classmethod
    def load(cls, folder):
        folder=Path(folder); m=json.loads((folder/'preprocessing.json').read_text(encoding='utf-8'))
        obj=cls(m['f10_variant'],m['seed'],m['threads'])
        if (m['fit_year']!=2025 or m['fit_partition']!='development' or m['protocol_id']!='C'
            or m['features']!=obj.features or m['classes']!=list(CLASSES) or m['backend_version']!=BACKEND_VERSION
            or m['model_sha256']!=sha256_file(folder/'model.txt')): raise ValueError('Invalid event artifact')
        obj.metadata=m; obj.vocabularies=m['vocabularies']; obj.booster=lgb.Booster(model_file=str(folder/'model.txt'))
        if obj.booster.feature_name()!=obj.features or obj.booster.num_model_per_iteration()!=6: raise ValueError('Invalid model schema')
        return obj


class MovementModel(TabularEventModel):
    def __init__(self, target, environment=False, seed=20260929, threads=4):
        super().__init__(seed,threads,'stuff','A')
        if target not in ('induced_vert_break','horz_break'): raise ValueError('Unknown movement target')
        self.target,self.environment=target,bool(environment)
        self.features=MOVEMENT_FEATURES+(['altitude_category'] if environment else [])
        self.categorical=[c for c in self.features if c in ('auto_pitch_type','pitcher_throws','altitude_category')]
        self.numeric=[c for c in self.features if c not in self.categorical]

    def fit_f10(self, rows, cfg, smoke=False):
        require_unique(rows)
        if rows.empty or not rows.year.eq(2024).all() or not rows.partition.eq('train').all(): raise PermissionError('Movement fit restricted to 2024/train')
        rows=rows.sort_values('pitch_uid')
        if not np.isfinite(rows[self.target]).all(): raise ValueError('Invalid movement labels')
        self.vocabularies={c:sorted(rows[c].unique().tolist()) for c in self.categorical}
        params=dict(cfg['parameters'],objective='regression',metric='l2',seed=self.seed,deterministic=True,force_col_wise=True,num_threads=self.threads,verbosity=-1)
        rounds=20 if smoke else cfg['movement_rounds']
        self.booster=lgb.train(params,lgb.Dataset(self.transform(rows),label=rows[self.target],categorical_feature=self.categorical),num_boost_round=rounds)
        self.metadata=dict(schema_version=1,target=self.target,environment=self.environment,seed=self.seed,threads=self.threads,features=self.features,vocabularies=self.vocabularies,best_iteration=rounds,fit_year=2024,fit_partition='train',fit_n=len(rows),fit_ids_sha256=ids_hash(rows.pitch_uid.tolist()),backend_version=BACKEND_VERSION)
        return self

    def predict(self, rows):
        if self.booster is None: raise RuntimeError('Unfitted movement model')
        result=np.asarray(self.booster.predict(self.transform(rows),num_threads=self.threads),dtype=float)
        if not np.isfinite(result).all(): raise ValueError('Non-finite movement predictions')
        return result

    @classmethod
    def load(cls, folder):
        folder=Path(folder); m=json.loads((folder/'preprocessing.json').read_text(encoding='utf-8'))
        obj=cls(m['target'],m['environment'],m['seed'],m['threads'])
        if (m['fit_year']!=2024 or m['fit_partition']!='train' or m['features']!=obj.features
            or m['model_sha256']!=sha256_file(folder/'model.txt') or m['backend_version']!=BACKEND_VERSION): raise ValueError('Invalid movement artifact')
        obj.metadata=m; obj.vocabularies=m['vocabularies']; obj.booster=lgb.Booster(model_file=str(folder/'model.txt'))
        if obj.booster.feature_name()!=obj.features: raise ValueError('Invalid movement feature schema')
        return obj


def movement_support(train, cfg):
    if train.empty or not train.year.eq(2024).all(): raise PermissionError('Support uses training only')
    groups=train.groupby(['auto_pitch_type','pitcher_throws','altitude_category']).size().rename('n').reset_index()
    counts=train.groupby(['pitcher_anon_id','auto_pitch_type','pitcher_throws','altitude_category']).size().rename('n').reset_index()
    counts=counts.loc[counts.n.ge(cfg['movement_overlap_min_pitches'])]
    overlaps=[]
    for (typ,hand),group in counts.groupby(['auto_pitch_type','pitcher_throws']):
        for source in sorted(train.altitude_category.unique()):
            for target in sorted(train.altitude_category.unique()):
                n=len(set(group.loc[group.altitude_category.eq(source),'pitcher_anon_id'])&set(group.loc[group.altitude_category.eq(target),'pitcher_anon_id']))
                overlaps.append(dict(auto_pitch_type=typ,pitcher_throws=hand,source=source,target=target,n_pitchers=n))
    numeric=[c for c in MOVEMENT_FEATURES if c not in ('auto_pitch_type','pitcher_throws')]
    return dict(groups=groups.to_dict('records'),overlaps=overlaps,numeric_bounds={c:[float(train[c].min()),float(train[c].max())] for c in numeric},min_rows=cfg['movement_support_min_rows'],min_pitchers=cfg['movement_overlap_min_pitchers'])


def scenario_support(rows, target, support):
    groups={(r['auto_pitch_type'],r['pitcher_throws'],r['altitude_category']):r['n'] for r in support['groups']}
    pairs={(r['auto_pitch_type'],r['pitcher_throws'],r['source'],r['target']):r['n_pitchers'] for r in support['overlaps']}
    reasons=[]
    for _,row in rows.iterrows():
        typ,hand,source=row.auto_pitch_type,row.pitcher_throws,row.altitude_category
        reason='supported_marginal_ranges_only'
        if min(groups.get((typ,hand,source),0),groups.get((typ,hand,target),0))<support['min_rows']: reason='insufficient_category_support'
        elif pairs.get((typ,hand,source,target),0)<support['min_pitchers']: reason='insufficient_within_pitcher_overlap'
        elif any(not np.isfinite(float(row[c])) or not low<=float(row[c])<=high for c,(low,high) in support['numeric_bounds'].items()): reason='outside_training_range'
        reasons.append(reason)
    return np.array(reasons,dtype=object)
