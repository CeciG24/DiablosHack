# Backend FastAPI — Diablos Stuff+

Desde la raíz del repositorio (Python 3.12):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\run_backend.ps1
```

Swagger interactivo: http://127.0.0.1:8001/docs. ReDoc: `/redoc`.
Contrato OpenAPI: `/openapi.json`. `/` abre Swagger. El servidor permanece
en ejecución hasta Ctrl+C. Alternativa sin scripts PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

## Modelos y configuración

Se carga una sola vez el release F8 verificado y el simulador F10 con su
manifest verificado; la inferencia comparte un lock para evitar llamadas
concurrentes sobre las mismas instancias nativas. No reentrena, cambia hashes,
reescribe modelos ni lee observaciones de 2026. F10 usa historia fija de 2024.
Los artefactos privados siguen excluidos de Git.

Variables opcionales (rutas absolutas recomendadas):

```powershell
$env:DIABLOS_RELEASE = 'C:\ruta\f8-release-20261013'
$env:DIABLOS_F10 = 'C:\ruta\f10-full\F10'
$env:DIABLOS_SCOUTING = 'C:\ruta\scouting.csv'
$env:DIABLOS_F9 = 'C:\ruta\f9-full\F9'
$env:DIABLOS_CORS_ORIGINS = 'http://localhost:3000,http://localhost:5173,http://localhost:4200'
.\run_backend.ps1 -Port 8001
```

Sin configuración usa los artefactos actuales en `artifacts/modeling/`.
Un fallo de integridad o una carpeta ausente deja esa capacidad con HTTP 503;
Swagger y `/health` continúan disponibles. `/ready` exige ambas capacidades.
La excepción detallada se registra sólo en el servidor.

## Endpoints y relación con el hackathon

| Método y ruta | Función |
|---|---|
| GET `/health`, `/ready` | Proceso y disponibilidad real de modelos |
| GET `/api/v1/models` | Variables, rangos, versiones, escala y límites |
| GET `/api/v1/validation` | Evidencia existente F8/F10 y holdout por categoría de altitud, sin reevaluar test |
| POST `/api/v1/predict` | Stuff+, Location+, Pitching+ por pitch; `family=all` por defecto |
| POST `/api/v1/summary` | Medias por pitcher y pitcher–tipo, conteos y cobertura |
| POST `/api/v1/movement-map` | HB/IVB, tipo y Pitching+ para scatterplot del dashboard |
| POST `/api/v1/simulate` | Movimiento y score F10 origen/destino, delta, soporte y contacto disponible |
| POST `/api/v1/recommendations` | Ordena perfiles enviados por score destino F10, con sus físicas y delta |
| GET `/api/v1/scouting` | Agregados pitcher×tipo de `scouting.csv` (artefactos F9/F10 o `DIABLOS_SCOUTING`); filtros `pitcher_anon_id`, `auto_pitch_type`, `min_n`, `limit`; ordenado por score |
| GET `/api/v1/profile` | `docs/F10_IDEAL_PROFILE.json` (perfil físico ideal por altitud, H1–H4 + respuestas a las 3 preguntas del brief); 404 hasta generarse. Generar con `python experiments/phase10_profile.py` |
| GET `/api/v1/pitchers` | Pitchers del review 2025 con `n`, juegos, mano, `n_categories` (cobertura de escenarios de altitud), `has_2026` y score experimental F9 medio (`min_n`, `limit`) |
| GET `/api/v1/pitcher/{id}` | Bundle para el dashboard: pitches reales con físicas y scores F8 por familia + score F9, arsenal por tipo×categoría, y deltas contrafactuales F10 por pareja de categorías desde `scenarios.json` (`max_pitches` default 400, `include_2026` default true, `max_2026` default 200). Pitches `partition=test_2026` son la partición sellada: score F8 inferido en vivo, sin calibración F9, marcados en la respuesta |

Los endpoints `/pitchers` y `/pitcher/{id}` leen `standardized_scores.parquet` y
`cohort.parquet` de los artefactos F9 (`DIABLOS_F9`, default
`artifacts/modeling/f9-full/F9`) y `scenarios.json` de F10; sin ellos responden
503 y `/pitcher/{id}` devuelve `deltas` vacío si falta solo `scenarios.json`.
El frame se cachea en memoria tras la primera llamada. Los deltas agregan los
escenarios contrafactuales precomputados del pitcher (orientados a la pareja
`a`→`b`), con `n_simulated` y un `regime` que exige cobertura observada **y**
simulada; no son promedios en vivo del simulador. El score por pitch es F8
(`event_utility_proxy_v1`, provisional); los deltas usan la escala F10
experimental — no son comparables entre sí.

Las agregaciones usan la distribución de lanzamientos enviada (cada pitch pesa
igual), no una media equiponderada de tipos ni un ranking poblacional. Los IDs
ausentes forman un grupo anónimo. La cobertura cuenta filas con las tres familias
en estado `ok`; categorías fuera del vocabulario pueden producir advertencias.
Revisar siempre `warnings` y soporte antes de interpretar los scores.

## Ejemplo ejecutable

```powershell
$pitches = Get-Content docs/F10_INPUT_EXAMPLE.json -Raw | ConvertFrom-Json
$body = @{ family = 'all'; records = @($pitches) } | ConvertTo-Json -Depth 10
Invoke-RestMethod http://127.0.0.1:8001/api/v1/predict -Method Post -ContentType 'application/json' -Body $body
$scenario = @{ records = @($pitches); target = 'Extreme Altitude' } | ConvertTo-Json -Depth 10
Invoke-RestMethod http://127.0.0.1:8001/api/v1/simulate -Method Post -ContentType 'application/json' -Body $scenario
```

Swagger incluye un pitch sintético como ejemplo de `Pitch`. Los inputs conservan
los nombres del proyecto: mph, rpm, pies para release/extensión/ubicación y
pulgadas para IVB/HB. El eje se entrega como seno/coseno del mismo ángulo.
`pitcher_anon_id` es opcional; F10 informa si usa historia o prior de grupo.
`stuff` requiere sólo físicas y tipo/mano; `location` requiere tipo/mano,
ubicación, conteo y lado del bateador; `all`/`pitching` requieren ambos conjuntos.
Simulación requiere físicas y categoría origen. Ubicación/conteo/lado son
opcionales para su diagnóstico de contacto.

Máximo 200 pitches para scores/summary/mapa, 50 para F10 y 1 MB por petición.
Errores de contrato (campos extra, outcomes, rangos, categorías ambientales,
conteos no enteros, NaN/infinito) devuelven 422; cuerpo excesivo devuelve 413.
Los rechazos de soporte F10 devuelven 200 con estado `unsupported` y delta nulo:
son resultados de evaluación y no deben tratarse como score cero.

## Alcance para la entrega

Actualización con arsenal: [Stuff+ final experimental F11](FINAL_SCORE.md).
`POST /api/v1/final-score` combina físicas, ubicación, arsenal histórico fijo y
contexto, con su propia escala de calibración 2025. No reemplaza las familias
F8: la comparación con/sin arsenal no demuestra una mejora global. La columna
y el modal de Análisis de lanzamientos lo identifican como experimental.
Configurar `DIABLOS_FINAL_SCORE` si los artefactos no están en
`artifacts/modeling/final-score-v1`.

F8 conserva las tres escalas provisionales congeladas de utilidad de eventos;
100 representa la referencia de calibración 2025 de cada familia, no una nueva
normalización sobre el lote. F8 no usa ambiente ni arsenal. F10 integra arsenal
regularizado y propaga diferencias predichas de IVB/HB entre categorías;
su escala experimental es distinta y no se resta de F8.

Los datos no identifican Harp Helú, estadio, metros ni atmósfera. Comparar
`No Altitude` con `Extreme Altitude` es una asociación categórica; no es una
estimación Harp–mar ni causal. No se inventan xRunValue, out dentro de PA,
barrels, HR, SHAP o park holdout. El contacto débil es el proxy F8 y las cabezas
condicionales conservan su ruta/estado original. Faltan esos insumos y validación
para completar esas partes del hackathon. Como sustituto del park holdout,
`/api/v1/validation` incluye la evidencia del holdout por categoría de altitud
sobre movimiento IVB/HB (`docs/ALTITUDE_HOLDOUT.md`): es generalización entre
buckets ambientales, no entre estadios físicos. Las recomendaciones sólo ordenan
el conjunto de candidatos evaluado; no prueban un óptimo físico global.

Este backend alimenta un dashboard; no incluye una interfaz gráfica de coaching.
El documento técnico y las métricas previas se conservan. El servicio se inicia
en loopback sin autenticación, para uso local del equipo; un despliegue compartido
requiere configurar acceso y HTTPS según el entorno.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_backend -v
$env:DIABLOS_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m unittest tests.test_backend -v
```

La primera ejecución no requiere datos ni modelos privados. La integración usa
artefactos reales y entradas sintéticas: compara scores con F8 directo, comprueba
probabilidades y rutas HTTP, y verifica delta cero al conservar categoría.

Referencia de Swagger/OpenAPI: [documentación oficial de FastAPI](https://fastapi.tiangolo.com/tutorial/metadata/).
