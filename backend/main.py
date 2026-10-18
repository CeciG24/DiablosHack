"""Run with: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001."""
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from backend.schemas import (Batch, PredictionRequest, PredictionResponse,
    SimulationRequest, SimulationResponse, SummaryResponse, MovementResponse,
    RecommendationResponse)
from modeling.datasets import FEATURES
from modeling.inference import ReleasePredictor
from experiments.phase10_simulator import Simulator

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


def create_app(predictor=None, simulator=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.predictor, app.state.simulator = predictor, simulator
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
        yield
        app.state.predictor = app.state.simulator = None

    app = FastAPI(title='Diablos — Stuff+ API', version='1.0.0', lifespan=lifespan,
        description='Backend del hackathon LMB. F8: Stuff+, Location+ y Pitching+ provisionales, '
        '100 + 10 × z(utilidad), referencia fija de calibración 2025. F10: escenarios '
        'experimentales de movimiento y arsenal. No representa xRunValue, probabilidad de out '
        'en PA, barril ni jonrón. Las categorías de altura no identifican Harp Helú. '
        'No requiere outcomes ni consulta registros del test 2026.',
        openapi_tags=[{'name': n} for n in ('Sistema', 'Modelo', 'Scores', 'Dashboard', 'Simulador')])
    app.state.inference_lock = RLock()
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
        return {'release_id': model.lock['release_id'],
                'records': [{f: predictions[f][i] for f in families} for i in range(len(rows))]}

    def simulate(payload):
        model = require('simulator')
        with app.state.inference_lock:
            results = model.simulate([p.record() for p in payload.records], payload.target)
        # pandas introduces NaN IDs in heterogeneous batches; restore caller IDs.
        for pitch, result in zip(payload.records, results):
            result['pitch_uid'] = pitch.pitch_uid
        return results

    @app.get('/', include_in_schema=False)
    def root():
        return RedirectResponse('/docs')

    @app.get('/health', tags=['Sistema'], summary='Estado del proceso')
    def health() -> dict:
        return {'status': 'ok', 'models': {n: getattr(app.state, n, None) is not None for n in ('predictor', 'simulator')}}

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
                'reference': 'F8 calibration 2025, fixed per family',
                'environment': model.contract['altitude_categories'],
                'f10_available': getattr(app.state, 'simulator', None) is not None,
                'limitations': ['F8 no ajusta arsenal ni ambiente', 'Stuff físico F8 es diagnóstico',
                    'F10 es experimental, asociación categórica con historia fija 2024',
                    'Sin mapping Harp Helú, metros, park holdout o efecto causal',
                    'Sin xRunValue, HR, barrel ni out dentro de PA']}

    @app.get('/api/v1/validation', tags=['Modelo'], summary='Evidencia guardada de validación; no reentrena')
    def validation() -> dict:
        return {name: json.loads((ROOT/'docs'/filename).read_text(encoding='utf-8'))
                for name, filename in [('f8', 'F8_FINAL_METRICS.json'), ('f10', 'F10_RESULTS.json')]}

    @app.post('/api/v1/predict', response_model=PredictionResponse, tags=['Scores'],
              summary='Score por lanzamiento, una familia o las tres', responses={503: {'description': 'F8 no disponible'}})
    def predict(payload: PredictionRequest):
        return score(payload)

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
              'Los escenarios rechazados conservan delta nulo. No comparar este score con la escala F8.')
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

    return app


app = create_app()
