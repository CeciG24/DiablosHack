"""Candidate exploration with frozen models and outcome-free LMB references."""
import json
import os
from pathlib import Path
from threading import RLock
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas import Altitude, Number, Pitch, SimulationRequest
from diablos_data import current_run
from modeling.datasets import STUFF

TYPES = ('Four-Seam', 'Sinker', 'Cutter', 'Slider', 'Curveball', 'Changeup', 'Splitter', 'Sweeper')
MEASURES = ('rel_speed', 'spin_rate', 'induced_vert_break', 'horz_break',
            'rel_height', 'rel_side', 'extension')
BOUNDS = dict(rel_speed=(30, 110), spin_rate=(0, 5000), induced_vert_break=(-40, 40),
              horz_break=(-40, 40), rel_height=(0, 10), rel_side=(-8, 8), extension=(0, 10))


class CandidateEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(min_length=1, max_length=128)
    pitch: Pitch
    weight: Number = Field(gt=0, le=1000000)
    observed_n: int | None = Field(None, strict=True, ge=1, le=1000000)


class CandidateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['pitches', 'profiles']
    entries: list[CandidateEntry] = Field(min_length=1, max_length=1000)
    target: Altitude = 'Extreme Altitude'

    @model_validator(mode='after')
    def physical(self):
        keys, hands = set(), set()
        for entry in self.entries:
            p = entry.pitch
            if entry.key in keys:
                raise ValueError('Las claves deben ser unicas')
            keys.add(entry.key)
            hands.add(p.pitcher_throws)
            if p.auto_pitch_type not in TYPES or p.pitcher_anon_id is not None:
                raise ValueError('Tipo no soportado o historia de pitcher no permitida')
            if any(getattr(p, c) is None for c in STUFF + ['altitude_category']):
                raise ValueError('Faltan caracteristicas fisicas o categoria de origen')
            if self.mode == 'pitches' and (entry.weight != 1 or entry.observed_n != 1):
                raise ValueError('Cada lanzamiento observado tiene peso y n iguales a 1')
        if len(hands) != 1:
            raise ValueError('Evaluar una sola mano por candidato')
        if self.mode == 'profiles' and abs(sum(e.weight for e in self.entries)-100) > .01:
            raise ValueError('Los pesos de perfiles deben sumar 100 por ciento')
        return self


def reference_frame(root):
    run = Path(os.environ['DIABLOS_RUN']) if os.getenv('DIABLOS_RUN') else current_run()
    manifest = json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'validated':
        raise ValueError('Run no validado')
    columns = ['pitch_uid', 'year', 'pitcher_anon_id', 'auto_pitch_type', 'pitcher_throws', *MEASURES]
    frame = pd.read_parquet(run/'pitches.parquet', columns=columns,
                            filters=[('year', 'in', [2025, 2026])])
    return frame, run.name


def reference_summary(frame, years, hand, run_id):
    selected = frame.loc[frame.year.isin(years).fillna(False).astype(bool) &
                         frame.pitcher_throws.eq(hand).fillna(False).astype(bool) &
                         frame.auto_pitch_type.isin(TYPES).fillna(False).astype(bool)].copy()
    total = len(selected)
    keep = pd.Series(True, index=selected.index)
    for name, (low, high) in BOUNDS.items():
        selected[name] = pd.to_numeric(selected[name], errors='coerce').astype(float)
        keep &= selected[name].between(low, high)
    selected = selected.loc[keep]
    groups, points = [], []
    for name, sub in selected.groupby('auto_pitch_type', sort=True):
        quantiles = {c: {f'p{q}': float(sub[c].quantile(q/100)) for q in (10, 25, 50, 75, 90)}
                     for c in MEASURES}
        groups.append(dict(auto_pitch_type=name, n=len(sub), pitchers=int(sub.pitcher_anon_id.nunique()),
                           quantiles=quantiles))
        ordered = sub.sort_values('pitch_uid')
        sample = ordered.iloc[np.linspace(0, len(ordered)-1, min(30, len(ordered)), dtype=int)]
        points.extend(dict(auto_pitch_type=name, year=int(r.year), ivb=float(r.induced_vert_break),
                           hb=float(r.horz_break), velo=float(r.rel_speed)) for r in sample.itertuples())
    return dict(years=list(years), hand=hand, data_run=run_id, raw_n=total, complete_n=len(selected),
                excluded_n=total-len(selected), groups=groups, points=points,
                by_year={str(y): int(selected.year.eq(y).sum()) for y in years},
                scope='LMB disponible; fisicas completas, no resultados ni roster de Diablos',
                exploratory_2026=2026 in years, score_reference='F8 calibration 2025 unchanged')


def weighted(rows, field):
    valid = [r for r in rows if r.get(field) is not None and np.isfinite(r[field])]
    return (sum(r[field]*r['weight'] for r in valid)/sum(r['weight'] for r in valid)) if valid else None


def summary(rows):
    total = sum(r['weight'] for r in rows)
    paired = [r for r in rows if r['target_score'] is not None and r['source_score'] is not None]
    supported = sum(r['weight'] for r in paired)
    return dict(source_score=weighted(rows, 'source_score'), target_score=weighted(paired, 'target_score'),
                paired_source_score=weighted(paired, 'source_score'), delta=weighted(paired, 'delta'),
                weight=total, supported_weight=supported, coverage=supported/total if total else 0,
                entries=len(rows), observed_n=sum(r['observed_n'] or 0 for r in rows),
                interval=None)


def install_profiler(app, root, require, simulate):
    reference_lock = RLock()
    reference_cache = {}
    source = []

    @app.get('/api/v1/profiler/reference', tags=['Perfilador'],
             summary='Referencia fisica LMB 2025/2026; no entrena ni lee outcomes')
    def reference(season: Literal['2025', '2026', '2025-2026'] = '2025-2026',
                  hand: Literal['Right', 'Left'] = 'Right'):
        key = (season, hand)
        with reference_lock:
            if key not in reference_cache:
                if not source:
                    try:
                        source.extend(reference_frame(root))
                    except (OSError, ValueError, KeyError) as error:
                        raise HTTPException(503, 'Referencia local no disponible o no validada') from error
                years = (2025, 2026) if season == '2025-2026' else (int(season),)
                reference_cache[key] = reference_summary(source[0], years, hand, source[1])
        return reference_cache[key]

    @app.post('/api/v1/profiler/evaluate', tags=['Perfilador'],
              summary='Arsenal candidato: fisica F8 y traslado F10, sin historia inventada')
    def evaluate(payload: CandidateRequest):
        predictor = require('predictor')
        inputs = [e.pitch.record() for e in payload.entries]
        predictions, simulations = [], []
        for start in range(0, len(inputs), 50):
            with app.state.inference_lock:
                predictions.extend(predictor.records(inputs[start:start+50], 'stuff'))
            simulations.extend(simulate(SimulationRequest(
                records=[e.pitch for e in payload.entries[start:start+50]], target=payload.target)))
        rows = []
        for entry, pred, sim in zip(payload.entries, predictions, simulations):
            comparison = sim.get('stuff_comparison', {})
            target = comparison.get('target_score') if comparison.get('status') == 'experimental' else None
            score = pred['score']
            rows.append(dict(key=entry.key, auto_pitch_type=entry.pitch.auto_pitch_type,
                source=entry.pitch.altitude_category, weight=entry.weight, observed_n=entry.observed_n,
                source_score=score, target_score=target,
                delta=target-score if score is not None and target is not None else None,
                target_ivb=sim.get('target_ivb') if target is not None else None,
                target_hb=sim.get('target_hb') if target is not None else None,
                status=sim['status'], reason=sim.get('reason'), warnings=pred['warnings']))
        groups = [dict(auto_pitch_type=name, **summary([r for r in rows if r['auto_pitch_type'] == name]))
                  for name in dict.fromkeys(r['auto_pitch_type'] for r in rows)]
        return dict(mode=payload.mode, target=payload.target, release_id=predictor.lock['release_id'],
                    summary=summary(rows), groups=groups, records=rows,
                    representative=payload.mode == 'profiles', arsenal_in_model=False,
                    scope='Fisica por pitch; relaciones de arsenal descriptivas. No es recomendacion de contratacion.',
                    interval_reason='individual_uncertainty_not_estimated')
