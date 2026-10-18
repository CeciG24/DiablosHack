# Plan de Implementación para cerrar el Hackathon (Base: rama `fase-9` de Ceci)

**Fecha de última actualización:** 18 de octubre de 2026
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
| **Backend FastAPI con Swagger** (`backend/`, `tests/test_backend.py`, `docs/BACKEND.md`) | ✅ **Mergeado a `fase-9`** (`6eab4c9`). 6 tests pasan; `test_real_models` skipped (requiere artefactos F8/F10 no versionados) |
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

### 4.2 Dashboard / Simulador funcional para el coach

- **Backend ya integrado** (`backend/main.py` expone scores, simulate, scouting). Falta la capa de presentación:
  - CLI o mini-web donde el coach ingrese features físicas de un pitch y obtenga score F10 + probabilidades de eventos.
  - Comparación lado a lado `No Altitude` vs. `Extreme Altitude` vía `phase10_simulator.py`.
  - Mapa de movimiento (IVB vs HB) coloreado por score y por `altitude_category`.
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

### 4.6 Demo de 10 minutos para coach/director

- **Qué falta:** script/demo mostrando:
  - Score de un pitch en `Extreme` vs. `No` altitud (backend `/simulate`).
  - Ranking de pitchers por score en cada bucket.
  - Perfil ideal de prospecto para CDMX.
  - Recomendación táctica (ej. preferir perfiles sinker/groundball en `Extreme`).
- **Por qué:** "Aplicabilidad real" pesa 25% de la rúbrica.

### 4.7 Integración final de artefactos y validación local

- **Qué falta:** restaurar en el clone los artefactos no versionados:
  - `data/runs/e9e0b1114dc68eb2`, `artifacts/modeling/f8-release-20261013`, `f9-full`, `f10-full` (copiar de `../DiablosHack` ajustando el data run `c1c8ba48818dc878`↔`e9e0b1114dc68eb2` y `RELEASE` en `experiments/phase9.py`/`phase10.py`).
  - Correr `run_phase9.ps1 check`, `run_phase10.ps1 check` y levantar el backend contra artefactos reales (desbloquea `test_real_models`).
- **Nota:** el holdout de altitud ya corre sin esos artefactos usando `--data-run` externo.

---

## 5. Resumen de prioridades

| Prioridad | Tarea | Estado | Dependencia |
|---|---|---|---|
| 🔴 Alta | Mergear `backend` a `fase-9` | ✅ **Hecho** (`6eab4c9`) | — |
| 🔴 Alta | Holdout por categoría de altitud (movimiento) | ✅ **Hecho** (`e4b67dc`) | — |
| 🔴 Alta | Holdout por altitud sobre eventos (log loss/Brier) | ⬜ Pendiente | `altitude_holdout.py` + modelo de eventos F9/F10 |
| 🔴 Alta | Documento técnico 6–10 páginas | ⬜ Pendiente | Resultados F9/F10/AH ya calculados |
| 🔴 Alta | Reportes visuales `REPORTE_F9/F10.md` + figuras | ⬜ Pendiente | `ALTITUDE_HOLDOUT_RESULTS.json` y JSONs F9/F10 |
| 🟡 Media | Dashboard/simulador comparativo para coach | ⬜ Pendiente | Backend ya mergeado + `phase10_simulator.py` |
| 🟡 Media | Perfil físico ideal + recomendaciones (H1–H4) | ⬜ Pendiente | Simulador F10 + `scouting.csv` + sesgo del holdout |
| 🟡 Media | Restaurar artefactos locales y correr checks F9/F10 | ⬜ Pendiente | Copiar `data/` y `artifacts/` de `../DiablosHack` |
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
- [x] F0–F7 implementados
- [x] F8 release congelado
- [x] F9 implementado y verificado (125 tests, protocolos A/B/C)
- [x] F10 implementado y verificado (138 tests, arsenal regularizado + altura)
- [x] Backend FastAPI mergeado a `fase-9` (`6eab4c9`)
- [ ] Artefactos pesados restaurados en el clone (data run, f8-release, f9-full, f10-full)
- [ ] `check` F9/F10 corriendo localmente con artefactos propios
- [ ] Backend levantado contra artefactos reales (`test_real_models` sin skip)

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
- [ ] Dashboard simulador (comparador `Extreme` vs `No`, mapa de movimiento)
- [ ] Documento técnico 6–10 páginas
- [ ] Reportes visuales `REPORTE_F9.md` / `REPORTE_F10.md` / figuras holdout
- [ ] Demo de 10 minutos para coach/director

### Documentación
- [x] `docs/ANALISIS_F10.md`
- [x] `docs/ALTITUDE_HOLDOUT.md` + `ALTITUDE_HOLDOUT_RESULTS.json`
- [x] `docs/PLAN_DE_IMPLEMENTACION.md` (este archivo)
- [ ] `docs/REPORTE_F9.md` y `docs/REPORTE_F10.md` ejecutivos
- [ ] Informe técnico final del hackathon
