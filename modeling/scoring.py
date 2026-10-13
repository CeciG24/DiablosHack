"""Fixed provisional utility scales; never expected runs or query normalization."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from modeling.baselines import CLASSES
from modeling.datasets import ids_hash, require_unique

S0 = 'event_utility_proxy_v1'
S1 = 'event_contact_utility_proxy_v1'
PROBS = ['p_'+c for c in CLASSES]
WEIGHTS = dict(ball=-0.5, called_strike=1., whiff=1., foul=0., in_play=0., hit_by_pitch=-1.)
CONTACT = ['p_'+c+'_given_in_play' for c in ('weak','medium','hard')]


def valid_probabilities(matrix):
    return (np.isfinite(matrix).all(axis=1) & (matrix >= 0).all(axis=1)
            & (matrix <= 1).all(axis=1) & (np.abs(matrix.sum(axis=1)-1) <= 1e-6))


def utility(frame, version=S0, weights=None, contact_weights=(0.5,-1.)):
    if version not in (S0,S1):
        raise ValueError('Unknown score version')
    weights = WEIGHTS if weights is None else weights
    if set(weights) != set(CLASSES) or not np.isfinite(list(weights.values())).all():
        raise ValueError('Invalid weights')
    p = frame.reindex(columns=PROBS).to_numpy(dtype=float)
    valid = valid_probabilities(p)
    value = p @ np.array([weights[c] for c in CLASSES])
    reason = np.where(valid,'ok','invalid_or_missing_event_probabilities').astype(object)
    if version == S1:
        q = frame.reindex(columns=CONTACT).to_numpy(dtype=float)
        promoted = (frame.get('contact_status',pd.Series('',index=frame.index)).eq('validated')
                    & frame.get('contact_route',pd.Series('',index=frame.index)).eq('model')).to_numpy()
        contact_valid = valid_probabilities(q) & promoted
        reason[valid & ~contact_valid] = 'verified_contact_head_unavailable'
        valid &= contact_valid
        value += p[:,CLASSES.index('in_play')] * (contact_weights[0]*q[:,0]+contact_weights[1]*q[:,2])
    value[~valid] = np.nan
    return value,reason


class FixedScale:
    def __init__(self, metadata):
        self.metadata = dict(metadata)
        m = self.metadata
        if (m['score_version'] not in (S0,S1) or m['family'] not in ('stuff','location','pitching')
                or m['ddof'] != 0 or m['reference_year'] != 2025 or m['reference_partition'] != 'calibration'
                or m['reference_n'] < 2 or not np.isfinite([m['mu'],m['sigma']]).all()
                or m['sigma'] <= 1e-12 or m['weights'] != WEIGHTS
                or m['contact_weights'] != [0.5,-1.]):
            raise ValueError('Invalid fixed scale metadata')

    @classmethod
    def fit(cls, reference, family, version, data_version):
        require_unique(reference)
        if not (reference.year.eq(2025).all() and reference.partition.eq('calibration').all()
                and reference.family.eq(family).all()):
            raise ValueError('Reference must be one family on 2025 calibration')
        values,reasons = utility(reference,version)
        if not (reasons == 'ok').all():
            raise ValueError('Reference probabilities or contact head unavailable')
        return cls(dict(family=family,score_version=version,mu=float(values.mean()),sigma=float(values.std(ddof=0)),
            ddof=0,reference_year=2025,reference_partition='calibration',reference_n=len(reference),
            reference_id=ids_hash(reference.pitch_uid.tolist()),data_version=data_version,
            weights=WEIGHTS,contact_weights=[0.5,-1.],semantics=version,represents_expected_runs=False))

    def transform(self, values):
        values = np.asarray(values,dtype=float)
        return np.where(np.isfinite(values),100+10*(values-self.metadata['mu'])/self.metadata['sigma'],np.nan)

    def score(self, frame):
        require_unique(frame)
        if 'family' in frame and not frame.family.eq(self.metadata['family']).all():
            raise ValueError('Wrong score family')
        if 'data_version' in frame and not frame.data_version.dropna().eq(self.metadata['data_version']).all():
            raise ValueError('Wrong data version')
        result = frame.copy()
        values,reasons = utility(frame,self.metadata['score_version'])
        result['utility'],result['score'],result['score_status'] = values,self.transform(values),reasons
        for key in ('score_version','reference_id'):
            result[key] = self.metadata[key]
        result['score_semantics'] = self.metadata['score_version']
        result['provisional'] = True
        return result

    def save(self,path):
        Path(path).write_text(json.dumps(self.metadata,indent=2,allow_nan=False)+'\n',encoding='utf-8')

    @classmethod
    def load(cls,path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8')))


def aggregate(frame, by):
    """Keep versions/references/partitions separate; denominator includes excluded pitches."""
    keys = ['family','score_version','reference_id','partition']+by
    if frame.duplicated(['family','score_version','pitch_uid']).any():
        raise ValueError('Duplicate score rows')
    rows = []
    for key,group in frame.groupby(keys,dropna=False,sort=True):
        valid = group.score.notna() & group.score_status.eq('ok')
        n = int(valid.sum())
        item = dict(zip(keys,key))
        item.update(n_total=len(group),n_valid=n,coverage=n/len(group),score=float(group.loc[valid,'score'].mean()) if n else None,
                    score_status='ok' if n else 'no_valid_predictions',estimand='observed_mix_mean_valid_pitches')
        for column in PROBS:
            item[column] = float(group.loc[valid,column].mean()) if n else None
        rows.append(item)
    return pd.DataFrame(rows)
