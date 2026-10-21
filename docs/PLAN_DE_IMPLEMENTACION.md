# Plan de Implementación para cerrar el Hackathon (Base: rama `fase-9` de Ceci)

**Fecha de última actualización:** 20 de octubre de 2026

> **Implementación xRV y arranque local (20 de octubre):** por autorización del equipo se implementó `xrv_external_mlb2014_v1` como adaptador de inferencia con pesos externos documentados MLB 2014, conteo explícito y referencia B1 de 2024. API `/predict` + `/xrv` y tarjeta en simulador. No modifica código/modelos congelados F8 ni convierte el delta F10 a carreras. No acredita xRunValue oficial ni validación LMB. Ver [XRV_APROXIMADO.md](XRV_APROXIMADO.md). Build de producción correcto; 18/18 pruebas Python (incluida integración real) y 31/31 Angular. Se verificó en navegador con pitchers reales. `run_full.ps1` arranca ambos servicios con dependencias/caché/logs en D: y configura `DIABLOS_RUN` para el run local, sin modificar manifests.

> **Auditoría de entrega-final (20 de octubre):** rama integrada `entrega-final`, commit `72f81b7`, descargada y activa en esta copia. Comparación actualizada y límites de verificación en [REVISION_ENTREGA_FINAL.md](REVISION_ENTREGA_FINAL.md). Pasan 11/11 pruebas backend con integración real F8/F10 y 8/8 del holdout. El build Angular sigue sin verificar: instalación falló por falta de espacio. El perfil `F10_IDEAL_PROFILE.json` y su endpoint ya existen; queda pendiente cerrar H1–H4 y justificar recomendaciones. El run local `c1c8ba48818dc878` difiere del esperado por esta rama (`e9e0b1114dc68eb2`); la carga real del dashboard debe verificarse por separado. Los estados históricos inferiores no acreditan ejecución en esta computadora.
**Rama base del plan:** `fase-9` (código y releases de Ceci) — HEAD actual: `6eab4c9` (merge de `backend` + holdout por altitud)
**Rama descartada:** `fase-9-ian` (nuestro trabajo en `DiablosHack` ya no será la base; se reutilizarán solo piezas puntuales si encajan).

> **Regla de mantenimiento:** Este documento es la fuente de verdad del estado del proyecto. **Debe actualizarse automáticamente después de cada cambio** (implementación, experimento, merge o decisión). Cada tarea completada se marca en el checklist de la sección 7 y se ajusta su descripción en el cuerpo del documento.

## 1. Supuestos críticos sobre los datos (confirmado)

Los organizadores **NO** proporcionarán los siguientes insumos:

- `stadium_id`, `park_id`, `venue` ni identificación explícita del Estadio Alfredo Harp Helú.
- `altitude_m` (metros sobre el nivel del mar) ni coordenadas de parques.
- Variables de clima/atmósfera: densidad del aire, temperatura, presión barométrica, humedad.
- Ocupación de bases / estados base-out (`runners_on_base`, `runner_1/2/3`, `on_base`) y xRunValue oficial.
- `run_value` por estado, PA ID / orden de aparición al plato.
- Secuencia real del pitch anterior (`prev_pitch_type`).

> **Implicación:** No se puede construir un park holdout real, un delta causal específico del Harp Helú, una simulación física exacta de densidad/Magnus ni un xRunValue/run expectancy por estados base-out. Cualquier "xRunValue" sería inventado y el contrato lo prohíbe (`MODELING_SYSTEM_CONTRACT.md`).

---

## 2. Estado actual ya implementado en la rama `fase-9`

| Componente | Estado |
|---|---|
| Preparación de datos y contrato (`data/CURRENT`, `data_catalog.csv`, `quality_summary.csv`) | ✅ Implementado y verificado |
| F0–F7: baselines B0/B1/B2, Stuff/Location/Pitching, calibración, cabezas de contacto, arsenal F5, simulador categórico F6, índices S0/S1 F7 | ✅ Implementado |
| F8: release congelado, API local, ficha de modelo, informe técnico PDF | ✅ Implementado |
| F9: protocolos A/B/C, contexto+física, arsenal, altura, índice estandarizado `context_standardized_event_utility_F9_v1`, auditoría independiente | ✅ Implementado y verificado |
| F10: auditoría de trayectorias, arsenal regularizado 8 tipos, modelos de movimiento IVB/HB ± altura, simulador residual `F10_regularized_context_standardized_utility_v1`, `scouting.csv`, escenarios de delta de score | ✅ Implementado y verificado |
| Cobertura de arsenal ampliada (de ~52% a 100% con prior de grupo) | ✅ Implementado en F10 |
| Simulador contrafactual que cambia movimiento (residual anchored) | ✅ Implementado en F10 |
| Escenarios `No/Medium/Extreme Altitude` y deltas de score | ✅ Implementado en F10 |
| **Backend FastAPI con Swagger** (`backend/`, `tests/test_backend.py`, `docs/BACKEND.md`) | ✅ **Mergeado a `fase-9`** (`6eab4c9`). Endpoints: `predict`, `summary`, `movement-map`, `simulate`, `recommendations`, `scouting` (lee `scouting.csv` F9/F10 o `DIABLOS_SCOUTING`), `profile` (sirve `docs/F10_IDEAL_PROFILE.json`, 404 hasta §4.5), `validation` (incluye evidencia del holdout). **10/10 tests pasan incluido `test_real_models` con artefactos reales** (`/ready`=200, `/simulate` experimental) |
| **Artefactos restaurados localmente** (`data/runs/e9e0b1114dc68eb2`, release F8, `test_exposure.json`) | ✅ Copiados de `../DiablosHack`. `expected_data_run` del contrato ajustado `c1c8ba48818dc878`→`e9e0b1114dc68eb2`; release hermano `f8-release-20261014` montado como `f8-release-20261013` (lock verifica íntegro contra este `modeling/`) |
| **`f9-full` regenerado localmente** (`artifacts/modeling/f9-full/F9`) | ✅ Corrido completo (11 modelos, protocolos A/B/C, ~240k train / ~58k review). 15/15 checks internos; `check_phase9` independiente 16/16 (`docs/F9_LOCAL_CHECK.json`). Produce `scouting.csv` (2,398 filas pitcher×tipo) y `standardized_scores.parquet` |
| **`f10-full` regenerado localmente** (`artifacts/modeling/f10-full/F10`) | ✅ Corrido completo (5 modelos eventos + 4 movimiento, trayectoria 99.17%, escenarios). 14/14 checks internos; `check_phase10` independiente 14/14 (`docs/F10_LOCAL_CHECK.json`) |
| **Holdout por categoría de altitud — movimiento IVB/HB** (`experiments/altitude_holdout.py`) | ✅ **Implementado y ejecutado** (`e4b67dc`). 8 tests pasan, corrida completa `ah-full` con 2024 train / 2025 review, 3 folds, 2,000 bootstrap |
| Reporte de análisis F10 (`docs/ANALISIS_F10.md`) | ✅ Generado |
| Reporte holdout de altitud (`docs/ALTITUDE_HOLDOUT.md` + `ALTITUDE_HOLDOUT_RESULTS.json`) | ✅ Generado |

### Resultados clave del holdout por altitud (movimiento, 2025 review)

| Categoría retenida | RMSE IVB sin altitud | RMSE IVB ordinal | RMSE HB sin altitud | RMSE HB ordinal | Sesgo IVB control |
|---|---:|---:|---:|---:|---:|
| Extreme (entrena No+Medium) | 2.82 | **2.01** | 2.61 | **1.88** | **+1.59 in** |
| Medium | 2.23 | **2.00** | 2.11 | **1.99** | +0.84 in |
| No | 3.39 | **3.23** | 3.64 | **3.45** | **−1.78 in** |

- El modelo físico sin altitud tiene **sesgo sistemático con signo dependiente de la altitud**: sobreestima movimiento en `Extreme`, lo subestima en `No`. En su propio dominio el sesgo es ≤0.15 in.
- Las **12 comparaciones** (2 targets × 3 folds × 2 variantes) mejoran al control con IC bootstrap pareado por partido bajo corrección Bonferroni.
- Dirección consistente con H1 (menos densidad → menos movimiento), pero **no causal**: Trackman, pitchers y parques mezclados pueden explicarlo.

---

## 3. Lo que NO se puede implementar (bloqueado por datos)

| Requisito del hackathon / rúbrica | Por qué está bloqueado |
|---|---|
| **Park holdout real (validación por estadio)** | No hay `stadium_id`/`park_id`; `game_anon_id` es identificador anónimo de partido, no de estadio. Lo implementado es **holdout por categoría de altitud**, no por estadio físico. |
| Delta específico Harp Helú vs. nivel del mar | No hay identificación del Harp ni `altitude_m`; `Extreme Altitude` agrupa todos los parques de alta altitud. |
| Simulación física exacta de densidad/aire | Faltan densidad, temperatura, presión, humedad. |
| xRunValue / expected runs por estado | Faltan `runners_on_base`, PA ID y run value por estado. |
| `tunnel_similarity` / efecto túnel real | No hay secuencia real entre pitches consecutivos. |
| `prev_pitch_type` (secuencia real) | No existe orden/cronología dentro del PA. |
| `P(out within PA)` | No hay identificador de aparición al plato ni resultados posteriores. |

---

## 4. Tareas pendientes (con lo disponible, sin datos externos)

### 4.1 Holdout por altitud — extensión a eventos ✅ parcial

- **Hecho:** movimiento IVB/HB con 3 folds leave-one-category-out, control vs. ordinal vs. ordinal_linear.
- **Falta:** el mismo protocolo sobre el modelo de **eventos** (log loss/Brier por categoría retenida) para cerrar la evaluación de generalización ambiente→outcome.
- **Falta:** conectar los resultados con el simulador F10 (verificar si el delta de score del simulador se alinea con el sesgo de movimiento observado).

### 4.2 Dashboard / Simulador funcional para el coach ✅ integrado

- **Backend ya integrado** (`backend/main.py` expone scores, simulate, `scouting` — ranking pitcher×tipo — y `profile` para el perfil ideal). **Nuevos endpoints para el frontend Angular:**
  - `GET /api/v1/pitchers`: pitchers reales del review 2025 (n, juegos, mano, score F9 medio) desde `standardized_scores.parquet`.
  - `GET /api/v1/pitcher/{id}`: bundle completo — pitches reales con físicas + scores F8 por familia + score F9, arsenal por tipo×categoría, y deltas contrafactuales por pareja de categorías agregados de `scenarios.json` F10 (con `n_simulated` y régimen que exige soporte observado **y** simulado).
- **Frontend Angular** (`../../altura-plus`, Angular 19): `ApiService` + `api-mappers.ts` (`Four-Seam`→`FB`, `Extreme Altitude`→`Extreme`, etc.). `DataService` intenta el API primero (`source='api'`, badge "API · review 2025"); si el backend no responde cae al generador sintético con badge "SINTÉTICO · demo" — nunca se presentan números inventados como evidencia real. Simulador cableado a `/predict` (scores F8 reales, debounce 250 ms) y `/simulate` (contrafactual F10 con selector origen/destino). Comparador corregido: `Extreme` ya no se etiqueta "Harp Helú" sin disclaimer de proxy.
- **CORS:** `DIABLOS_CORS_ORIGINS=http://localhost:4200` para `ng serve`.
- **Por qué:** Entregable obligatorio #4 del hackathon ("Dashboard Simulador").
- **Restricción:** comparación por `altitude_category` (proxy de CDMX), con advertencia de que no es delta específico del Harp.

### 4.3 Reportes visuales (gráficas) para F9/F10 y holdout de altitud

- **Qué falta:** figuras SVG/PNG:
  - Curvas de calibración por categoría de altitud y protocolo (A/B/C).
  - Importancia de features del arsenal regularizado y modelos de movimiento.
  - Comparación RMSE IVB/HB con/sin `altitude_category` por categoría (ya hay números en `ALTITUDE_HOLDOUT_RESULTS.json`; falta la figura).
  - Barras/heatmap de deltas del simulador (`No→Extreme`, `Extreme→No`).
  - Distribución del score F10 por `altitude_category` y tipo de pitch.
  - **Nueva:** gráfica del sesgo firmado por categoría retenida (+1.59/+0.84/−1.78 IVB) — la evidencia más clara del efecto altitud.
- **Scripts a crear:** `scripts/generar_reporte_f9.py`, `scripts/generar_reporte_f10.py` (o equivalente) + `docs/REPORTE_F9.md` / `docs/REPORTE_F10.md` ejecutivos en español.

### 4.4 Documento técnico final (6–10 páginas)

- **Qué falta:** informe técnico con:
  - Marco teórico sabermétrico + física del béisbol (Stuff/Location/Pitching, efecto Magnus, referencias Nathan/SABR/FanGraphs).
  - Decisiones de modelado (LightGBM, calibración por temperatura, protocolos A/B/C, arsenal regularizado, simulador residual, controles de soporte).
  - Definición formal de la escala `100 + 10·z` y scores usados (S0, `F10_regularized_context_standardized_utility_v1`).
  - Validación fuera de muestra: season holdout (A), pitcher holdout (B), **altitude-category holdout (nuevo, sección 2)** explicando que sustituye al park holdout por falta de `stadium_id`.
  - Cuantificación del efecto altitud: RMSE movimiento −13.7%/−14.2% (F10), deltas de score ~−3.17/+2.74 (F10), y sesgo firmado +1.59/−1.78 del holdout.
  - Alcance y fronteras (no xRunValue, no stadium ID, no causalidad, no secuencia PA).

### 4.5 Perfil físico ideal y recomendaciones operativas

- **Qué falta:** responder explícitamente con evidencia:
  - ¿Qué combinación de velocidad/movimiento/spin/release/arsenal maximiza el score en `Extreme Altitude`? (H1)
  - ¿Los pitch types basados en `velo_diff_vs_fb` (changeup, splitter) ganan valor relativo? (H2)
  - ¿Los perfiles `groundball` son más valiosos en altitud? (H3)
  - ¿`spin_rate` solo es insuficiente vs. `spin_per_mph`/movimiento? (H4)
- **Método:** simulador F10 + agregados por pitcher/tipo/arsenal con soporte mínimo (`scouting.csv` extendido). El holdout de altitud ya muestra que las rectas (Four-Seam) concentran el mayor sesgo — insumo directo para H1.
- **Salida:** generar `docs/F10_IDEAL_PROFILE.json` (versionado); el backend ya lo expone en `GET /api/v1/profile`.

### 4.6 Demo de 10 minutos para coach/director

- **Qué falta:** script/demo mostrando:
  - Score de un pitch en `Extreme` vs. `No` altitud (backend `/simulate`).
  - Ranking de pitchers por score en cada bucket.
  - Perfil ideal de prospecto para CDMX.
  - Recomendación táctica (ej. preferir perfiles sinker/groundball en `Extreme`).
- **Por qué:** "Aplicabilidad real" pesa 25% de la rúbrica.

### 4.7 Integración final de artefactos y validación local ✅ hecho

- **Hecho:** datos `e9e0b1114dc68eb2` + release F8 + `test_exposure.json` restaurados de `../DiablosHack`; `f9-full` y `f10-full` regenerados con el pipeline de esta rama (smoke primero, luego full); `check_phase9`/`check_phase10` independientes en verde; backend levantado contra artefactos reales (`/ready`=200, `test_real_models` pasa).
- **Nota:** los artefactos quedaron fuera de Git (`.gitignore`); reproducibles con `python -m experiments.phase9 --name f9-full` y `python -m experiments.phase10 --name f10-full`.

---

## 5. Resumen de prioridades

| Prioridad | Tarea | Estado | Dependencia |
|---|---|---|---|
| 🔴 Alta | Mergear `backend` a `fase-9` | ✅ **Hecho** (`6eab4c9`) | — |
| 🔴 Alta | Holdout por categoría de altitud (movimiento) | ✅ **Hecho** (`e4b67dc`) | — |
| 🔴 Alta | Holdout por altitud sobre eventos (log loss/Brier) | ⬜ Pendiente | `altitude_holdout.py` + modelo de eventos F9/F10 |
| 🔴 Alta | Documento técnico 6–10 páginas | ⬜ Pendiente | Resultados F9/F10/AH ya calculados |
| 🔴 Alta | Reportes visuales `REPORTE_F9/F10.md` + figuras | ⬜ Pendiente | `ALTITUDE_HOLDOUT_RESULTS.json` y JSONs F9/F10 |
| 🟡 Media | Dashboard/simulador comparativo para coach | ✅ **Integrado** | Angular `altura-plus` + `/pitchers`, `/pitcher/{id}`, `/predict`, `/simulate` |
| 🟡 Media | Perfil físico ideal + recomendaciones (H1–H4) | ⬜ Pendiente | Simulador F10 + `scouting.csv` + sesgo del holdout |
| 🟡 Media | Restaurar artefactos locales y correr checks F9/F10 | ✅ **Hecho** (`docs/F9_LOCAL_CHECK.json`, `docs/F10_LOCAL_CHECK.json`) | — |
| 🟡 Media | Demo de 10 minutos para coach/director | ⬜ Pendiente | Dashboard + perfil ideal |
| ⚪ Baja | Pedir a organizadores `stadium_id`, `altitude_m`, `runners_on_base` | ⬜ Descartado por instrucción | — |

---

## 6. Advertencias finales

- **No inventar xRunValue ni stadium mapping:** el contrato lo prohíbe. Todo delta de altitud se reporta como asociación por `altitude_category`, no como efecto causal del Harp Helú.
- **El holdout por altitud no es park holdout:** nombrarlo así en el informe técnico; `Extreme Altitude` agrupa múltiples parques.
- **El feature ordinal no extrapola:** con `Extreme`/`No` retenidas los árboles saturan al extremo visto; solo el fold `Medium` interpola de verdad.
- **Rama base:** todo el desarrollo sobre `DiablosHack-ceci-fase-9` (rama `fase-9`), no sobre `fase-9-ian`.
- **Reutilización permitida:** solo piezas de `fase-9-ian` que no requieran re-entrenar (ej. guiones de visualización como referencia).

---

## 7. Checklist maestro

> Marcar `[x]` al completar cada ítem y actualizar la sección correspondiente del documento.

### Infraestructura y releases
- [x] Lanzador completo `run_full.ps1` con runtime en D:, CORS, comprobación de modelos, pitchers y HTTP del frontend
- [x] Build producción y 31 pruebas Angular verificados localmente el 20 de octubre
- [x] xRV aproximado externo MLB 2014 implementado en API/simulador, con 7 pruebas específicas; alcance experimental documentado
- [x] F0–F7 implementados
- [x] F8 release congelado
- [x] F9 implementado y verificado (125 tests, protocolos A/B/C)
- [x] F10 implementado y verificado (138 tests, arsenal regularizado + altura)
- [x] Backend FastAPI mergeado a `fase-9` (`6eab4c9`)
- [x] Artefactos pesados restaurados en el clone (data run `e9e0b1114dc68eb2`, f8-release, `f9-full`, `f10-full` regenerados)
- [x] `check` F9/F10 corriendo localmente con artefactos propios (`F9_LOCAL_CHECK.json` 16/16, `F10_LOCAL_CHECK.json` 14/14)
- [x] Backend levantado contra artefactos reales (`test_real_models` pasa, `/ready`=200)

### Validación de generalización
- [x] Holdout por categoría de altitud — movimiento IVB/HB (`e4b67dc`, `ah-full`)
- [x] 3 folds leave-one-category-out con control/ordinal/ordinal_linear
- [x] Bootstrap pareado por partido + Bonferroni (12/12 mejoras significativas)
- [ ] Holdout por altitud sobre eventos (log loss/Brier)
- [ ] Integración de resultados del holdout con el simulador F10
- [ ] Sección del holdout en el documento técnico (como sustituto del park holdout)

### Entregables del hackathon
- [x] Scores por pitch/pitcher/arsenal (F8/F9/F10 + backend `/score`, `/scouting`)
- [x] Comparación CDMX vs. otros estadios por proxy de `altitude_category` (deltas F10 + holdout)
- [ ] Perfil físico ideal para Diablos Rojos (H1–H4 respondidas con evidencia)
- [ ] Recomendaciones operativas (qué perfiles ganan/pierden en altitud, scouting de prospectos)
- [x] Dashboard simulador (comparador `Extreme` vs `No`, mapa de movimiento) — Angular conectado al backend real
- [ ] Documento técnico 6–10 páginas
- [ ] Reportes visuales `REPORTE_F9.md` / `REPORTE_F10.md` / figuras holdout
- [ ] Demo de 10 minutos para coach/director

### Documentación
- [x] Comparación de `entrega-final` contra requisitos transcritos y comprobaciones locales (`docs/REVISION_ENTREGA_FINAL.md`, 20 de octubre de 2026)
- [x] `docs/ANALISIS_F10.md`
- [x] `docs/ALTITUDE_HOLDOUT.md` + `ALTITUDE_HOLDOUT_RESULTS.json`
- [x] `docs/PLAN_DE_IMPLEMENTACION.md` (este archivo)
- [ ] `docs/REPORTE_F9.md` y `docs/REPORTE_F10.md` ejecutivos
- [ ] Informe técnico final del hackathon
