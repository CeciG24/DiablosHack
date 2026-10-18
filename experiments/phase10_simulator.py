"""Experimental categorical movement transport with explicit support checks."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from experiments.phase9 import engineer, standardized_probabilities, UTILITY, write, RELEASE
from experiments.phase9_predict import verify_experiment
from experiments.phase10_features import Repertoire
from experiments.phase10_models import EventModel, MovementModel, scenario_support
from modeling.calibration import TemperatureScaler
from modeling.inference import ReleasePredictor


class Simulator:
    def __init__(self, folder, verify=True, contact=True):
        folder=Path(folder)
        if verify: verify_experiment(folder)
        self.repertoire=Repertoire.load(folder/'repertoire')
        self.quality=EventModel.load(folder/'events/regularized/model')
        self.calibrator=TemperatureScaler.load(folder/'events/regularized/temperature.json')
        self.movement={c:MovementModel.load(folder/'movement'/c/'environment') for c in ('induced_vert_break','horz_break')}
        self.support=json.loads((folder/'movement_support.json').read_text(encoding='utf-8'))
        self.scale=json.loads((folder/'scale.json').read_text(encoding='utf-8'))
        self.context=json.loads((folder/'context_distribution.json').read_text(encoding='utf-8'))
        self.contact=ReleasePredictor(RELEASE) if contact else None
        if self.scale['sigma']<=1e-12: raise ValueError('Invalid scale')

    def quality_probabilities(self, rows):
        prepared=self.repertoire.transform(engineer(rows))
        return standardized_probabilities(self.quality,self.calibrator,prepared,self.context)

    def simulate(self, records, target):
        rows=pd.DataFrame(records).reset_index(drop=True)
        if rows.empty: return []
        required=list(self.quality.features[:11])+['altitude_category']
        output=[]; indices=[]; valid=[]
        for i,row in rows.iterrows():
            result=dict(pitch_uid=row.get('pitch_uid'),source=row.get('altitude_category'),target=target,
                status='unsupported',reason=None,delta_score=None,score_version=self.scale['version'],
                scope='categorical_association_fixed_history_not_causal_not_Harp',interval=None)
            try:
                if any(c not in rows for c in required): raise ValueError('Missing physical or source-category input')
                candidate=pd.DataFrame([row])
                candidate=engineer(candidate)
                # Canonical data-contract ranges; derived movement must also remain in range.
                bounds={'rel_speed':(30,110),'spin_rate':(0,5000),'rel_height':(0,10),'rel_side':(-8,8),'extension':(0,10),'induced_vert_break':(-40,40),'horz_break':(-40,40),'spin_axis_sin':(-1,1),'spin_axis_cos':(-1,1)}
                if any(not np.isfinite(float(row[c])) or not lo<=float(row[c])<=hi for c,(lo,hi) in bounds.items()): raise ValueError('Invalid physical input')
                reason=scenario_support(candidate,target,self.support)[0]
                result['reason']=str(reason)
                if reason=='supported_marginal_ranges_only':
                    indices.append(i);valid.append(candidate)
            except (ValueError,TypeError,KeyError,AttributeError):
                result.update(status='invalid_input',reason='missing_invalid_or_out_of_range_input')
            output.append(result)
        if not valid: return output
        source=pd.concat(valid,ignore_index=True)
        destination=source.copy(); destination['altitude_category']=target
        for col,model in self.movement.items():
            destination[col]=source[col].to_numpy()+model.predict(destination)-model.predict(source)
        supported=destination[['induced_vert_break','horz_break']].abs().le(40).all(axis=1).to_numpy()
        for j in np.flatnonzero(~supported): output[indices[j]]['reason']='projected_movement_out_of_range'
        source=source.loc[supported].reset_index(drop=True);destination=destination.loc[supported].reset_index(drop=True)
        indices=[idx for idx,ok in zip(indices,supported) if ok]
        if source.empty:return output
        p0=self.quality_probabilities(source);p1=self.quality_probabilities(destination)
        s0=100+10*(p0@UTILITY-self.scale['mu'])/self.scale['sigma']
        s1=100+10*(p1@UTILITY-self.scale['mu'])/self.scale['sigma']
        contacts0=self.contact.predict(source,'pitching') if self.contact else None
        contacts1=self.contact.predict(destination,'pitching') if self.contact else None
        history=self.repertoire.transform(source)
        for j,idx in enumerate(indices):
            output[idx].update(status='experimental',source_score=float(s0[j]),target_score=float(s1[j]),delta_score=float(s1[j]-s0[j]),
                source_ivb=float(source.induced_vert_break.iloc[j]),target_ivb=float(destination.induced_vert_break.iloc[j]),
                source_hb=float(source.horz_break.iloc[j]),target_hb=float(destination.horz_break.iloc[j]),
                history_status=history.history_status.iloc[j],history_n=int(history.history_n.iloc[j]),
                probabilities_source=p0[j].tolist(),probabilities_target=p1[j].tolist(),contact_status='unavailable')
            if contacts0 is not None:
                c='p_hard_given_in_play';g='p_groundball_given_in_play'
                if np.isfinite(contacts0[c].iloc[j]) and np.isfinite(contacts1[c].iloc[j]):
                    output[idx].update(contact_status='F8_fixed_location_observed_count_association',
                        hard_contact_given_bip_source=float(contacts0[c].iloc[j]),hard_contact_given_bip_target=float(contacts1[c].iloc[j]),
                        groundball_given_bip_source=float(contacts0[g].iloc[j]),groundball_given_bip_target=float(contacts1[g].iloc[j]))
        return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True);parser.add_argument('--input',required=True)
    parser.add_argument('--target',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if Path(args.output).exists():raise FileExistsError(args.output)
    records=json.loads(Path(args.input).read_text(encoding='utf-8'))
    if not isinstance(records,list) or not all(isinstance(r,dict) for r in records):raise ValueError('Expected array of pitch objects')
    write(args.output,Simulator(args.experiment).simulate(records,args.target))
