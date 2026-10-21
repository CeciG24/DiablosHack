"""Run with: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001."""
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
from threading import RLock, Thread

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from backend.schemas import (Batch, PredictionRequest, PredictionResponse,
    SimulationRequest, SimulationResponse, SummaryResponse, MovementResponse,
    RecommendationResponse, FinalScoreResponse)
from modeling.datasets import FEATURES
from modeling.final_score import FinalScorePredictor
from modeling.inference import ReleasePredictor
from experiments.phase10_simulator import Simulator
from backend.xrv import ExternalRunValue
from backend.score_cache import score_frame
from backend.profiler import install_profiler
from modeling.baselines import EventBaseline

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger(__name__)


class BodyLimit:
    """Limit bytes actually received, including requests without Content-Length."""
    def __init__(self, app, maximum=1_000_000):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > self.maximum:
                return await JSONResponse({'detail': 'Máximo 1000000 bytes'}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get('more_body', False):
                break
        async def replay():
            return chunks.pop(0) if chunks else await receive()
        await self.app(scope, replay, send)


def create_app(predictor=None, simulator=None, final_predictor=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.predictor, app.state.simulator = predictor, simulator
        app.state.final_predictor = final_predictor
        for name, factory, path in (
            ('predictor', ReleasePredictor, os.getenv('DIABLOS_RELEASE', str(ROOT/'artifacts/modeling/releases/f8-release-20261013'))),
            ('simulator', lambda path: Simulator(path, contact=False), os.getenv('DIABLOS_F10', str(ROOT/'artifacts/modeling/f10-full/F10'))),
        ):
            if getattr(app.state, name) is None:
                try:
                    instance = factory(path)
                    if name == 'simulator':
                        instance.contact = app.state.predictor
                    setattr(app.state, name, instance)
                except Exception:
                    # Verification failures must never fall back to unverified models.
                    log.exception('No se pudo cargar %s', name)
        model = app.state.predictor
        baseline = EventBaseline.load(model.folder/'B1.json') if model is not None and hasattr(model, 'folder') else None
        app.state.xrv = ExternalRunValue(baseline=baseline)

        final_path = Path(os.getenv('DIABLOS_FINAL_SCORE', str(ROOT/'artifacts/modeling/final-score-v1')))
        if predictor is None and final_predictor is None and (final_path/'manifest.json').is_file():
            try:
                app.state.final_predictor = FinalScorePredictor(final_path)
            except Exception:
                log.exception('No se pudo verificar Pitch Value+; F8 permanece disponible')

        def warm():
            try:
                scored(review_frame())
                try:
                    scored(test2026_frame())
                except HTTPException:
                    pass
            except Exception:
                log.exception('Precálculo F8 en segundo plano falló')
        if predictor is None and app.state.predictor is not None:
            Thread(target=warm, daemon=True).start()
        yield
        app.state.predictor = app.state.simulator = app.state.review = app.state.scenarios = None
        app.state.final_predictor = None

    app = FastAPI(title='Diablos — Stuff+ API', version='1.2.0', lifespan=lifespan,
        description='Backend del hackathon LMB. F8: Stuff+, Location+ y Pitching+ provisionales, '
        '100 + 10 × z(utilidad), referencia fija de calibración 2025. F10: escenarios '
        'experimentales de movimiento y arsenal. F11: Pitch Value+ experimental con '
        'fisicas, ubicacion, arsenal y contexto, escala propia; no reemplaza F8. '
        'xRV aproximado con pesos LMB 2024; no es xRunValue oficial del hackathon. No representa probabilidad de out '
        'en PA, barril ni jonrón. Las categorías de altura no identifican Harp Helú. '
        'No requiere outcomes. El perfilador usa 2025/2026 como referencia descriptiva autorizada, sin reentrenar.',
        openapi_tags=[{'name': n} for n in ('Sistema', 'Modelo', 'Scores', 'Dashboard', 'Simulador')])
    app.state.inference_lock = RLock()
    app.state.scoring_lock = RLock()
    app.state.review = None
    app.state.scenarios = None
    app.state.test2026 = None
    app.state.bundle_cache = {}
    app.add_middleware(BodyLimit)
    origins = [s.strip() for s in os.getenv('DIABLOS_CORS_ORIGINS', '').split(',') if s.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    def require(name):
        instance = getattr(app.state, name, None)
        if instance is None:
            raise HTTPException(503, 'Artefactos no disponibles o no verificados; consultar configuración y logs del servidor')
        return instance

    def score(payload):
        model = require('predictor')
        families = ('stuff', 'location', 'pitching') if payload.family == 'all' else (payload.family,)
        rows = [p.record() for p in payload.records]
        for family in families:
            missing = sorted({f for row in rows for f in FEATURES[family] if f not in row})
            if missing:
                raise HTTPException(422, f'Faltan variables para {family}: '+', '.join(missing))
        with app.state.inference_lock:
            predictions = {f: model.records(rows, f) for f in families}
        for family in families:
            for row, prediction in zip(rows, predictions[family]):
                prediction['xrv'] = app.state.xrv.evaluate(
                    prediction['probabilities'], row, prediction['status'])
        return {'release_id': model.lock['release_id'],
                'records': [{f: predictions[f][i] for f in families} for i in range(len(rows))]}

    def simulate(payload):
        model = require('simulator')
        with app.state.inference_lock:
            results = model.simulate([p.record() for p in payload.records], payload.target)
        predictor = getattr(app.state, 'predictor', None)
        pairs, indices = [], []
        # pandas introduces NaN IDs in heterogeneous batches; restore caller IDs.
        for i, (pitch, result) in enumerate(zip(payload.records, results)):
            result['pitch_uid'] = pitch.pitch_uid
            result['stuff_comparison'] = {'status': 'unavailable'}
            movement = [result.get('target_ivb'), result.get('target_hb')]
            if (predictor is None or result['status'] != 'experimental' or
                    any(v is None or not np.isfinite(v) or abs(v) > 40 for v in movement)):
                continue
            source = pitch.record()
            destination = source | dict(altitude_category=payload.target,
                induced_vert_break=movement[0], horz_break=movement[1])
            pairs.extend([source, destination])
            indices.append(i)
        if pairs:
            # Same frozen physical model and scale on both shapes; never reuse F10's utility.
            with app.state.inference_lock:
                predictions = predictor.records(pairs, 'stuff')
            for j, i in enumerate(indices):
                source, target = predictions[2*j:2*j+2]
                comparison = results[i]['stuff_comparison']
                comparison.update(release_id=predictor.lock['release_id'],
                    score_version=source['score_version'],
                    warnings=';'.join(filter(None, [source['warnings'], target['warnings']])))
                if all(p['score'] is not None and np.isfinite(p['score']) for p in (source, target)):
                    comparison.update(status='experimental', source_score=source['score'],
                        target_score=target['score'], delta_score=target['score']-source['score'])
        return results

    install_profiler(app, ROOT, require, simulate)

    @app.get('/', include_in_schema=False)
    def root():
        return RedirectResponse('/docs')

    @app.get('/health', tags=['Sistema'], summary='Estado del proceso')
    def health() -> dict:
        return {'status': 'ok', 'models': {n: getattr(app.state, n, None) is not None
                                         for n in ('predictor', 'simulator', 'final_predictor')}}

    @app.get('/ready', tags=['Sistema'], summary='Disponibilidad de F8 y F10', responses={503: {'description': 'Faltan modelos verificados'}})
    def ready() -> dict:
        require('predictor'); require('simulator')
        return {'status': 'ready'}

    @app.get('/api/v1/models', tags=['Modelo'], summary='Versiones, variables, escala y límites')
    def models() -> dict:
        model = require('predictor')
        return {'release_id': model.lock['release_id'], 'features': FEATURES,
                'physical_bounds': model.contract['physical_review_bounds'],
                'scale': '100 + 10 * z(P(whiff)+P(called_strike)-0.5*P(ball)-P(hit_by_pitch))',
                'scale_bands': [{'min': 120, 'label': 'elite', 'detail': '~percentil 97 (2+ desviaciones mejor que promedio)'},
                                {'min': 110, 'label': 'sobre promedio', 'detail': 'una desviación estándar mejor'},
                                {'min': 90, 'label': 'promedio', 'detail': '±1 desviación estándar de la media'},
                                {'min': 80, 'label': 'bajo promedio', 'detail': 'una desviación estándar peor'},
                                {'min': 0, 'label': 'por debajo de reemplazo', 'detail': 'dos o más desviaciones peor'}],
                'scale_caveat': 'Referencia fija de calibración 2025 por familia; ajustada por temporada '
                                'pero NO por estadio (sin stadium_id). Las bandas son orientativas.',
                'reference': 'F8 calibration 2025, fixed per family',
                'environment': model.contract['altitude_categories'],
                'f10_available': getattr(app.state, 'simulator', None) is not None,
                'final_score': {
                    'available': app.state.final_predictor is not None,
                    'features': app.state.final_predictor.model.features if app.state.final_predictor else [],
                    'experimental': True,
                    'endpoint': '/api/v1/final-score',
                    'scope': 'F11: fisica + ubicacion + arsenal fijo 2024 + conteo/lado; escala propia',
                    'targets': 'Utilidad de eventos; cabezas auxiliares F8 no alimentan este score'},
                'limitations': ['F8 no ajusta arsenal ni ambiente', 'Stuff físico F8 es diagnóstico',
                    'F10 es experimental, asociación categórica con historia fija 2024',
                    'Sin mapping Harp Helú, metros, park holdout o efecto causal',
                    'xRV aproximado con pesos LMB 2024; sin validación individual de carreras ni ajuste por estadio',
                    'Sin xRunValue oficial, HR, barrel ni out dentro de PA']}

    @app.get('/api/v1/xrv', tags=['Modelo'], summary='Pesos xRV aproximado LMB 2024, cobertura y procedencia')
    def xrv_metadata() -> dict:
        return app.state.xrv.metadata()

    @app.get('/api/v1/validation', tags=['Modelo'], summary='Evidencia guardada F8/F10 y holdout de altitud; no reentrena')
    def validation() -> dict:
        return {name: json.loads((ROOT/'docs'/filename).read_text(encoding='utf-8'))
                for name, filename in [('f8', 'F8_FINAL_METRICS.json'), ('f10', 'F10_RESULTS.json'),
                                       ('altitude_holdout', 'ALTITUDE_HOLDOUT_RESULTS.json'),
                                       ('final_score', 'FINAL_SCORE_RESULTS.json')]}

    @app.post('/api/v1/predict', response_model=PredictionResponse, tags=['Scores'],
              summary='Score por lanzamiento, una familia o las tres', responses={503: {'description': 'F8 no disponible'}})
    def predict(payload: PredictionRequest):
        return score(payload)

    @app.post('/api/v1/final-score', response_model=FinalScoreResponse, tags=['Scores'],
              summary='Pitch Value+ experimental: fisica, ubicacion, arsenal y contexto',
              description='Escala F11 propia (100 + 10 z), calibracion 2025; no sustituye F8. '
              'Arsenal regularizado de 2024; sin historia usa prior de grupo, informado en history_status.')
    def final_score(payload: Batch):
        model = require('final_predictor')
        missing = sorted({field for pitch in payload.records for field in FEATURES['pitching']
                          if field not in pitch.record()})
        if missing:
            raise HTTPException(422, 'Faltan variables para Pitch Value+: '+', '.join(missing))
        with app.state.inference_lock:
            rows = [p.record() for p in payload.records]
            predictions = model.records(rows)
        for row, prediction in zip(rows, predictions):
            prediction['xrv'] = app.state.xrv.evaluate(
                prediction.get('probabilities') or {}, row,
                'ok' if prediction['status'] == 'experimental' else prediction['status'])
        return {'records': predictions}

    @app.post('/api/v1/summary', response_model=SummaryResponse, tags=['Scores'],
              summary='Agregación por pitcher y arsenal del lote enviado')
    def summary(payload: Batch):
        result = score(PredictionRequest(records=payload.records))
        groups = {'pitchers': {}, 'arsenal': {}}
        for pitch, predictions in zip(payload.records, result['records']):
            for kind, key in [('pitchers', (pitch.pitcher_anon_id, None)), ('arsenal', (pitch.pitcher_anon_id, pitch.auto_pitch_type))]:
                groups[kind].setdefault(key, []).append(predictions)
        output = {'release_id': result['release_id']}
        for kind, grouped in groups.items():
            output[kind] = []
            for (pitcher, pitch_type), rows in grouped.items():
                valid = [r for r in rows if all(r[f]['status'] == 'ok' for f in ('stuff', 'location', 'pitching'))]
                item = dict(pitcher_anon_id=pitcher, auto_pitch_type=pitch_type,
                            requested=len(rows), scored=len(valid), coverage=len(valid)/len(rows))
                for family in ('stuff', 'location', 'pitching'):
                    item[family+'_plus'] = sum(r[family]['score'] for r in valid)/len(valid) if valid else None
                output[kind].append(item)
        return output

    @app.post('/api/v1/movement-map', response_model=MovementResponse, tags=['Dashboard'],
              summary='Puntos HB/IVB y Pitching+ para graficar')
    def movement_map(payload: Batch):
        result = score(PredictionRequest(records=payload.records, family='pitching'))
        return {'records': [dict(pitch_uid=p.pitch_uid, auto_pitch_type=p.auto_pitch_type,
                    pitcher_anon_id=p.pitcher_anon_id, ivb=p.induced_vert_break,
                    hb=p.horz_break, pitching_plus=r['pitching']['score'], status=r['pitching']['status'])
                for p, r in zip(payload.records, result['records'])]}

    @app.post('/api/v1/simulate', response_model=SimulationResponse, tags=['Simulador'],
              summary='Origen/destino: movimiento, score, delta y soporte F10',
              description='50 pitches máximo. Requiere físicas y categoría origen. Ubicación/conteo son opcionales para contacto. '
              'Incluye stuff_comparison: F8 físico en origen y movimiento proyectado F10, misma escala. '
              'Sin intervalos individuales. Los scores F10 originales permanecen separados; no identifica estadios.')
    def simulation(payload: SimulationRequest):
        return {'records': simulate(payload)}

    @app.post('/api/v1/recommendations', response_model=RecommendationResponse, tags=['Simulador'],
              summary='Perfiles candidatos ordenados por score en categoría destino',
              description='Exploración sobre los candidatos enviados. Incluye perfil físico y delta; '
              'no extrapola un perfil ideal fuera de la muestra ni infiere riesgo de jonrón.')
    def recommendations(payload: SimulationRequest):
        results = simulate(payload)
        ranked = [dict(input_index=i, profile=p.record(), simulation=r)
                  for i, (p, r) in enumerate(zip(payload.records, results)) if r['status'] == 'experimental']
        ranked.sort(key=lambda r: r['simulation']['target_score'], reverse=True)
        return dict(supported=len(ranked), unsupported=len(results)-len(ranked), ranked_candidates=ranked)

    def scouting_file():
        candidates = [os.getenv('DIABLOS_SCOUTING'),
                      ROOT/'artifacts/modeling/f10-full/F10/scouting.csv',
                      ROOT/'artifacts/modeling/f9-full/F9/scouting.csv']
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return Path(candidate)
        return None

    @app.get('/api/v1/scouting', tags=['Scores'], summary='Agregados pitcher×tipo del review 2025 para ranking',
             description='Lee scouting.csv de los artefactos F9/F10 (o la ruta DIABLOS_SCOUTING). '
             'Ordena por score descendente. Medias sobre la mezcla observada de lanzamientos; '
             'no es ranking poblacional ni evidencia causal.',
             responses={503: {'description': 'scouting.csv no disponible'}})
    def scouting(pitcher_anon_id: str | None = None, auto_pitch_type: str | None = None,
                 min_n: int = 30, limit: int = 200):
        path = scouting_file()
        if path is None:
            raise HTTPException(503, 'scouting.csv no disponible; restaurar artefactos F9/F10 o fijar DIABLOS_SCOUTING')
        table = pd.read_csv(path)
        if pitcher_anon_id:
            table = table.loc[table.pitcher_anon_id == pitcher_anon_id]
        if auto_pitch_type:
            table = table.loc[table.auto_pitch_type == auto_pitch_type]
        table = table.loc[table.n >= min_n].sort_values('score', ascending=False).head(min(limit, 1000))
        return {'source': str(path), 'rows': int(len(table)), 'records': table.to_dict('records')}

    REVIEW_FEATURES = ['pitch_uid', 'pitcher_throws', 'rel_speed', 'spin_rate',
        'spin_axis_sin', 'spin_axis_cos', 'rel_height', 'rel_side', 'extension',
        'induced_vert_break', 'horz_break', 'plate_loc_height', 'plate_loc_side',
        'balls', 'strikes', 'batter_side']
    CATEGORIES = ('No Altitude', 'Medium Altitude', 'Extreme Altitude')

    def review_frame():
        """Review 2025: features físicas + score experimental F9, cacheado en memoria."""
        if app.state.review is None:
            f9 = Path(os.getenv('DIABLOS_F9', str(ROOT/'artifacts/modeling/f9-full/F9')))
            scores_path, cohort_path = f9/'standardized_scores.parquet', f9/'cohort.parquet'
            if not scores_path.is_file() or not cohort_path.is_file():
                raise HTTPException(503, 'Artefactos F9 no disponibles; restaurar artifacts/modeling/f9-full o fijar DIABLOS_F9')
            scores = pd.read_parquet(scores_path)
            cohort = pd.read_parquet(cohort_path)
            app.state.review = scores.merge(cohort[REVIEW_FEATURES], on='pitch_uid', validate='1:1')
        return app.state.review

    def test2026_frame():
        """Partición sellada 2026: se sirve para visualización con scores F8
        inferidos en vivo; nunca entró a entrenamiento ni calibración F8/F9/F10.
        """
        if app.state.test2026 is None:
            run = Path(os.getenv('DIABLOS_RUN', str(ROOT/'data/runs/e9e0b1114dc68eb2')))
            path = run/'pitches.parquet'
            if not path.is_file():
                raise HTTPException(503, 'Partición 2026 no disponible; fijar DIABLOS_RUN al run con pitches.parquet')
            cols = ['pitch_uid', 'year', 'game_anon_id', 'pitcher_anon_id', 'pitcher_throws',
                'auto_pitch_type', 'altitude_category', 'spin_axis',
                'rel_speed', 'spin_rate', 'rel_height', 'rel_side', 'extension',
                'induced_vert_break', 'horz_break',
                'plate_loc_height', 'plate_loc_side', 'balls', 'strikes', 'batter_side']
            frame = pd.read_parquet(path, columns=cols)
            frame = frame.loc[frame.year == 2026].copy()
            rad = np.radians(frame.spin_axis.astype(float))
            frame['spin_axis_sin'] = np.sin(rad)
            frame['spin_axis_cos'] = np.cos(rad)
            app.state.test2026 = frame.drop(columns=['spin_axis'])
        return app.state.test2026

    def scenario_frame():
        """Deltas contrafactuales F10 precomputados (scenarios.json) unidos a pitcher/tipo."""
        if app.state.scenarios is None:
            f10 = Path(os.getenv('DIABLOS_F10', str(ROOT/'artifacts/modeling/f10-full/F10')))
            path = f10/'scenarios.json'
            frame = review_frame()
            if not path.is_file():
                raise HTTPException(503, 'scenarios.json no disponible; restaurar artefactos F10')
            scenarios = pd.DataFrame(json.loads(path.read_text(encoding='utf-8')))
            keys = frame[['pitch_uid', 'pitcher_anon_id', 'auto_pitch_type']]
            app.state.scenarios = scenarios.merge(keys, on='pitch_uid', validate='m:1')
        return app.state.scenarios

    def scored(frame):
        """Cache scores once per frame, with separate F8/F11 completion markers."""
        return score_frame(frame, require('predictor'), app.state.final_predictor,
                           app.state.scoring_lock, app.state.inference_lock)

    def clean_json(value):
        """NaN/inf no son JSON válidos: se convierten a null recursivamente."""
        if isinstance(value, dict):
            return {k: clean_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean_json(v) for v in value]
        return None if isinstance(value, (float, np.floating)) and not np.isfinite(value) else value

    def regime(n_a, n_b):
        least = min(n_a, n_b)
        return 'interpolado' if least >= 120 else 'extrapolado' if least >= 40 else 'insuficiente'

    def mean_ci(values):
        series = pd.to_numeric(pd.Series(values), errors='coerce').dropna()
        if series.empty:
            return None, None
        half = 1.96 * series.std(ddof=1) / np.sqrt(len(series)) if len(series) > 1 else 0.0
        return float(series.mean()), [float(series.mean() - half), float(series.mean() + half)]

    @app.get('/api/v1/pitchers', tags=['Dashboard'], summary='Pitchers del review 2025 con volumen y score medio',
             description='Agregados reales de standardized_scores (partición phase_review). '
             'Sirven para poblar selectores; no son ranking poblacional.',
             responses={503: {'description': 'Artefactos F9 no disponibles'}})
    def pitchers(min_n: int = 60, limit: int = 60):
        frame = review_frame()
        try:
            in2026 = set(test2026_frame().pitcher_anon_id.unique())
        except HTTPException:
            in2026 = set()
        grouped = frame.groupby('pitcher_anon_id')
        rows = []
        for pitcher, sub in grouped:
            if len(sub) < min_n:
                continue
            throws = sub.pitcher_throws.mode()
            rows.append(dict(pitcher_anon_id=pitcher, throws=throws.iat[0] if len(throws) else None,
                             n=int(len(sub)), games=int(sub.game_anon_id.nunique()),
                             n_categories=int(sub.altitude_category.nunique()),
                             has_2026=pitcher in in2026,
                             experimental_score=float(sub.experimental_score.mean())))
        rows.sort(key=lambda r: r['experimental_score'], reverse=True)
        return {'scope': 'Review 2025 agregado; score experimental F9, no comparable con F8',
                'rows': int(len(rows[:limit])), 'records': rows[:limit]}

    @app.get('/api/v1/pitcher/{pitcher_anon_id}', tags=['Dashboard'],
             summary='Bundle de un pitcher: scores F8 por pitch, arsenal por categoría y deltas F10',
             description='Pitches reales del review 2025 con físicas y scores F8 (stuff/location/pitching) '
             'más el score experimental F9. Arsenal agregado por tipo×categoría. Deltas contrafactuales '
             'por pareja de categorías desde scenarios.json F10 (escala experimental). '
             'Con include_2026=true agrega pitches de la partición sellada 2026 scoreados '
             'con F8 en vivo (inferencia; nunca entraron a entrenamiento ni calibración) — '
             'llevan partition=test_2026 y no tienen experimental_score F9.',
             responses={404: {'description': 'Pitcher sin lanzamientos en review 2025'},
                        503: {'description': 'Artefactos F9/F8 no disponibles'}})
    def pitcher_bundle(pitcher_anon_id: str, max_pitches: int = 400,
                       include_2026: bool = True, max_2026: int = 200):
        key = (pitcher_anon_id, max_pitches, include_2026, max_2026)
        if key in app.state.bundle_cache:
            return app.state.bundle_cache[key]
        frame = scored(review_frame())
        sub = frame.loc[frame.pitcher_anon_id == pitcher_anon_id].reset_index(drop=True)
        if sub.empty:
            raise HTTPException(404, 'Pitcher sin lanzamientos en el review 2025')
        families = {f: [None if pd.isna(v) else float(v) for v in sub[f + '_plus']]
                    for f in ('stuff', 'location', 'pitching')}
        axes = np.degrees(np.arctan2(sub.spin_axis_sin, sub.spin_axis_cos)) % 360
        pitches = []
        for i, row in enumerate(sub.head(max_pitches).itertuples()):
            pitches.append(dict(pitch_uid=row.pitch_uid, auto_pitch_type=row.auto_pitch_type,
                year=int(row.year), partition='phase_review',
                altitude_category=row.altitude_category,
                rel_speed=row.rel_speed, spin_rate=row.spin_rate,
                spin_axis_sin=row.spin_axis_sin, spin_axis_cos=row.spin_axis_cos,
                rel_height=row.rel_height, rel_side=row.rel_side, extension=row.extension,
                induced_vert_break=row.induced_vert_break, horz_break=row.horz_break,
                plate_loc_height=row.plate_loc_height, plate_loc_side=row.plate_loc_side,
                balls=None if pd.isna(row.balls) else int(row.balls),
                strikes=None if pd.isna(row.strikes) else int(row.strikes),
                batter_side=row.batter_side if isinstance(row.batter_side, str) else None,
                stuff_plus=families['stuff'][i],
                location_plus=families['location'][i],
                pitching_plus=families['pitching'][i],
                stuff_final=getattr(row, 'stuff_final', None),
                final_history_n=getattr(row, 'final_history_n', None),
                final_history_status=getattr(row, 'final_history_status', None),
                experimental_score=row.experimental_score))
        pitches = pitches[:max_pitches]
        # Partición sellada 2026: pitches reales scoreados con F8 en vivo
        # (inferencia pura — nunca entraron a train/calibración). Sin score F9.
        n_2026 = 0
        if include_2026:
            try:
                t26 = scored(test2026_frame())
                own26 = t26.loc[t26.pitcher_anon_id == pitcher_anon_id].head(max_2026).reset_index(drop=True)
                if len(own26):
                    fam26 = {f: [None if pd.isna(v) else float(v) for v in own26[f + '_plus']]
                             for f in ('stuff', 'location', 'pitching')}
                    n_2026 = int(len(own26))
                    for i, row in enumerate(own26.itertuples()):
                        pitches.append(dict(pitch_uid=row.pitch_uid, auto_pitch_type=row.auto_pitch_type,
                            year=int(row.year), partition='test_2026',
                            altitude_category=row.altitude_category,
                            rel_speed=row.rel_speed, spin_rate=row.spin_rate,
                            spin_axis_sin=row.spin_axis_sin, spin_axis_cos=row.spin_axis_cos,
                            rel_height=row.rel_height, rel_side=row.rel_side, extension=row.extension,
                            induced_vert_break=row.induced_vert_break, horz_break=row.horz_break,
                            plate_loc_height=row.plate_loc_height, plate_loc_side=row.plate_loc_side,
                            balls=None if pd.isna(row.balls) else int(row.balls),
                            strikes=None if pd.isna(row.strikes) else int(row.strikes),
                            batter_side=row.batter_side if isinstance(row.batter_side, str) else None,
                            stuff_plus=fam26['stuff'][i],
                            location_plus=fam26['location'][i],
                            pitching_plus=fam26['pitching'][i],
                            stuff_final=getattr(row, 'stuff_final', None),
                            final_history_n=getattr(row, 'final_history_n', None),
                            final_history_status=getattr(row, 'final_history_status', None),
                            experimental_score=None))
            except HTTPException:
                pass
        summaries = {}
        for family in ('stuff', 'location', 'pitching'):
            mean, ci = mean_ci(families[family])
            summaries[family] = dict(mean=mean, ci=ci, n=int(len(sub)))
        arsenal = []
        for (pitch_type, category), cell in sub.groupby(['auto_pitch_type', 'altitude_category']):
            stuff = [families['stuff'][j] for j in cell.index]
            mean, ci = mean_ci(stuff)
            arsenal.append(dict(auto_pitch_type=pitch_type, altitude_category=category, n=int(len(cell)),
                usage=len(cell)/len(sub), rel_speed=float(cell.rel_speed.mean()), spin_rate=float(cell.spin_rate.mean()),
                spin_axis_sin=float(cell.spin_axis_sin.mean()), spin_axis_cos=float(cell.spin_axis_cos.mean()),
                rel_height=float(cell.rel_height.mean()), rel_side=float(cell.rel_side.mean()),
                extension=float(cell.extension.mean()),
                induced_vert_break=float(cell.induced_vert_break.mean()), horz_break=float(cell.horz_break.mean()),
                stuff_plus=mean, ci=ci))
        deltas = []
        try:
            scenarios = scenario_frame()
            own = scenarios.loc[scenarios.pitcher_anon_id == pitcher_anon_id]
            for pitch_type, typed in sub.groupby('auto_pitch_type'):
                counts = typed.altitude_category.value_counts()
                observed = {c: int(counts.get(c, 0)) for c in CATEGORIES}
                cell = own.loc[own.auto_pitch_type == pitch_type]
                for a, b in (('No Altitude', 'Medium Altitude'), ('No Altitude', 'Extreme Altitude'),
                             ('Medium Altitude', 'Extreme Altitude')):
                    direct = cell.delta_score[(cell.source == a) & (cell.target == b)]
                    inverse = -cell.delta_score[(cell.source == b) & (cell.target == a)]
                    oriented = pd.concat([direct, inverse]).dropna()
                    mean, ci = mean_ci(oriented)
                    n_sim = int(len(oriented))
                    # La evidencia del delta exige pitches observados en ambos buckets y
                    # cobertura contrafactual; sin simulaciones el régimen cae a insuficiente.
                    if observed[a] == 0 or observed[b] == 0 or n_sim < 5:
                        delta_regime = 'insuficiente'
                    elif min(observed[a], observed[b]) >= 120 and n_sim >= 15:
                        delta_regime = 'interpolado'
                    else:
                        delta_regime = 'extrapolado'
                    row = dict(auto_pitch_type=pitch_type, scenario_a=a, scenario_b=b,
                        delta_score=mean, ci=ci, n_a=observed[a], n_b=observed[b],
                        n_simulated=n_sim, regime=delta_regime)
                    if len(cell):
                        row['score_version'] = cell.score_version.iloc[0]
                        row['scope'] = cell.scope.iloc[0]
                    deltas.append(row)
        except HTTPException:
            pass
        response = {'pitcher_anon_id': pitcher_anon_id,
                'throws': sub.pitcher_throws.mode().iat[0] if len(sub.pitcher_throws.mode()) else None,
                'n': int(len(sub)), 'games': int(sub.game_anon_id.nunique()),
                'n_2026': n_2026,
                'spin': dict(avg_rpm=float(sub.spin_rate.mean()), max_rpm=float(sub.spin_rate.max()),
                             axis_deg=float(pd.Series(axes).mean())),
                'summaries': summaries, 'arsenal': arsenal,
                'pitches': pitches, 'deltas': deltas,
                'final_score': {
                    'available': app.state.final_predictor is not None,
                    'experimental': True,
                    'score_version': app.state.final_predictor.scale['version'] if app.state.final_predictor else None,
                    'model_id': app.state.final_predictor.model_id if app.state.final_predictor else None},
                'scope': 'Pitches y medias del review 2025; scores F8 provisionales + F9 experimental; '
                         'pitches 2026 = partición sellada con scores F8 inferidos (sin F9); '
                         'deltas en escala F10 experimental, no comparables con F8'}
        # Artefactos inmutables por proceso: el bundle sólo depende de la query.
        app.state.bundle_cache[key] = clean_json(response)
        return app.state.bundle_cache[key]

    @app.get('/api/v1/profile', tags=['Dashboard'], summary='Perfil físico ideal por categoría de altitud (H1–H4)',
             description='Sirve docs/F10_IDEAL_PROFILE.json, evidencia generada offline con el simulador F10 '
             '(plan §4.5). 404 mientras no se haya generado.',
             responses={404: {'description': 'Perfil ideal aún no generado'}})
    def profile():
        path = ROOT/'docs'/'F10_IDEAL_PROFILE.json'
        if not path.is_file():
            raise HTTPException(404, 'Perfil ideal aún no generado; falta docs/F10_IDEAL_PROFILE.json (plan §4.5)')
        return json.loads(path.read_text(encoding='utf-8'))

    return app


app = create_app()
