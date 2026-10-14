"""Outcome-free, row-preserving inference for the frozen A base policy."""
from pathlib import Path
import numpy as np
import pandas as pd
from modeling.models import TabularEventModel
from modeling.contact import AuxiliaryModel, HEADS
from modeling.calibration import TemperatureScaler
from modeling.scoring import FixedScale, PROBS
from modeling.release import read, verify_release


class ReleasePredictor:
    def __init__(self, folder, release_id=None):
        self.folder=Path(folder)
        self.lock=verify_release(folder,release_id)
        self.support=read(self.folder/'training_support.json')
        self.contract=read(self.folder/'data_contract.json')
        self.models,self.scales,self.scalers,self.heads={},{},{},{}
        for family in ('stuff','location','pitching'):
            source=self.folder/'models'/family
            self.models[family]=TabularEventModel.load(source/'event/model')
            self.scales[family]=FixedScale.load(self.folder/(family+'_scale.json'))
            self.scalers[family]=self._scaler(source/'event')
            self.heads[family]={}
            for head in HEADS:
                path=source/head
                decision=read(path/'decision.json')
                model=AuxiliaryModel.load(path/'model') if decision['route']=='model' else None
                baseline=read(path/'baseline.json')['probabilities'] if decision['route']=='smoothed_training_prevalence' else None
                self.heads[family][head]=(decision,model,baseline,self._scaler(path) if model else None)

    @staticmethod
    def _scaler(folder):
        return TemperatureScaler.load(folder/'temperature.json') if read(folder/'calibration_policy.json')['route']=='temperature' else None

    def predict(self, inputs, family='pitching'):
        frame=pd.DataFrame(inputs).reset_index(drop=True).copy()
        if not frame.columns.is_unique:raise ValueError('Duplicate input columns')
        output=pd.DataFrame(index=frame.index)
        output['request_id']=frame.get('request_id',pd.Series([str(i) for i in frame.index],index=frame.index))
        output['pitch_uid']=frame.get('pitch_uid',pd.Series([None]*len(frame),index=frame.index))
        output['family'],output['route'],output['status']=family,'base','ok'
        output['warnings']=''
        output['model_version']=self.lock['release_id']
        output['data_version']=self.lock['data_run']
        output['score_version']=output['score_semantics']='event_utility_proxy_v1'
        output['protocol_id']='A'
        output['reference_id']=None
        output['reference_pitch_count']=0
        output['environment_mode']='not_used_by_approved_policy'
        output['input_support_status']='not_evaluated'
        output[PROBS+['score','stuff_plus','location_plus','pitching_plus',
            'p_weak_given_in_play','p_medium_given_in_play','p_hard_given_in_play','p_groundball_given_in_play','p_chase_given_outside']]=np.nan
        output['provisional']=True
        output['score_status']='invalid_input'
        if family not in self.models:
            output['status']=output['score_status']='unsupported_model'
            output['warnings']='unknown_family'
            return output
        model=self.models[family]
        output['reference_id']=self.scales[family].metadata['reference_id']
        invalid=pd.Series(False,index=frame.index)
        for feature in model.features:
            if feature not in frame:frame[feature]=np.nan
        for feature in model.numeric:
            values=pd.to_numeric(frame[feature],errors='coerce')
            invalid |= values.isna() | ~np.isfinite(values) | frame[feature].map(lambda x:isinstance(x,(bool,np.bool_)))
            frame[feature]=values
            if feature in ('balls','strikes'):
                invalid |= ~values.between(0,3 if feature=='balls' else 2) | values.mod(1).ne(0)
            bounds=self.contract['physical_review_bounds'].get(feature)
            if feature in ('spin_axis_sin','spin_axis_cos'):bounds=[-1,1]
            if bounds:invalid |= ~values.between(*bounds)
        for feature in model.categorical:
            invalid |= ~frame[feature].map(lambda x:isinstance(x,str) and bool(x.strip()))
        output.loc[invalid,'status']='invalid_input'
        output.loc[invalid,'warnings']='missing_invalid_or_out_of_contract_feature'
        valid=~invalid
        if valid.any():
            rows=frame.loc[valid]
            p=model.predict(rows)
            scaler=self.scalers[family]
            if scaler is not None:p=scaler.transform(p)
            output.loc[valid,PROBS]=p
            utility=p[:,2]+p[:,1]-.5*p[:,0]-p[:,5]
            output.loc[valid,'score']=self.scales[family].transform(utility)
            output.loc[valid,family+'_plus']=output.loc[valid,'score']
            output.loc[valid,'score_status']='ok'
            warnings=pd.Series(model.warnings(rows),index=rows.index)
            for feature in model.numeric:
                low,high=self.support['numeric_bounds'][feature]
                warnings.loc[~rows[feature].between(low,high)] += ';outside_training_range:'+feature
            output.loc[valid,'input_support_status']=np.where(warnings.eq(''),'within_checked_marginal_support','outside_checked_support')
            if 'pitcher_anon_id' in rows:
                warnings.loc[~rows.pitcher_anon_id.isin(self.support['pitchers'])]+=';unseen_pitcher_base_policy_requires_no_history'
            if 'altitude_category' in rows:
                warnings.loc[~rows.altitude_category.isin(self.contract['altitude_categories'])]+=';unknown_environment_ignored_by_base_policy'
            if family=='stuff':warnings+=';diagnostic_stuff_model'
            output.loc[valid,'warnings']=warnings.str.strip(';')
            for head,(decision,headmodel,baseline,calibrator) in self.heads[family].items():
                output[head+'_status'],output[head+'_route']=decision['status'],decision['route']
                q=headmodel.predict(rows) if headmodel is not None else (np.tile(baseline,(len(rows),1)) if baseline is not None else None)
                if q is None:continue
                if calibrator is not None:q=calibrator.transform(q)
                if head=='contact':
                    for i,label in enumerate(HEADS[head]):output.loc[valid,'p_'+label+'_given_in_play']=q[:,i]
                else:output.loc[valid,'p_'+('groundball_given_in_play' if head=='groundball' else 'chase_given_outside')]=q[:,1]
        for label in ('weak','medium','hard','groundball'):
            output['p_'+label+'_per_pitch']=output.p_in_play*output['p_'+label+'_given_in_play']
        return output

    def records(self,inputs,family='pitching'):
        flat=self.predict(inputs,family)
        records=[]
        for row in flat.to_dict('records'):
            row={k:(None if pd.isna(v) else v) for k,v in row.items()}
            row['probabilities']={c[2:]:row.pop(c) for c in PROBS}
            row['conditional_probabilities']={key:row[column] for key,column in dict(
                hard_contact_bip='p_hard_given_in_play',weak_contact_proxy_bip='p_weak_given_in_play',
                groundball_bip='p_groundball_given_in_play').items()}
            records.append(row)
        return records
