# Plan de Implementación para cerrar el Hackathon (Base: rama `fase-9` de Ceci)

**Fecha:** 18 de octubre de 2026
**Rama base del plan:** `fase-9` (código y releases de Ceci)
**Rama descartada:** `fase-9-ian` (nuestro trabajo en `DiablosHack` ya no será la base; se reutilizarán solo piezas puntuales si encajan).

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

## 2. Estado actual ya implementado en la rama de Ceci (`fase-9`)

Lo que ya existe y verificó:

| Componente | Estado |
|---|---|
| Preparación de datos y contrato (`data/CURRENT`, `data_catalog.csv`, `quality_summary.csv`) | ✅ Implementado y verificado |
| F0–F7: baselines B0/B1/B2, Stuff/Location/Pitching, calibración, cabezas de contacto, arsenal F5, simulador categórico F6, índices S0/S1 F7 | ✅ Implementado |
| F8: release congelado, API local, ficha de modelo, informe técnico PDF | ✅ Implementado |
| F9: protocolos A/B/C, contexto+física, arsenal, altura, índice estandarizado `context_standardized_event_utility_F9_v1`, auditoría independiente | ✅ Implementado y verificado |
| F10: auditoría de trayectorias, arsenal regularizado 8 tipos, modelos de movimiento IVB/HB ± altura, simulador residual `F10_regularized_context_standardized_utility_v1`, `scouting.csv`, escenarios de delta de score | ✅ Implementado y verificado |
| Backend FastAPI con Swagger (`backend/main.py`, `backend/schemas.py`, `tests/test_backend.py`, `docs/BACKEND.md`) | ✅ Implementado en rama `backend` (commit `7ccd42d` que parte de F10) |
| Cobertura de arsenal ampliada (de ~52% a 100% con prior de grupo) | ✅ Implementado en F10 |
| Simulador contrafactual que cambia movimiento (residual anchored) | ✅ Implementado en F10 |
| Escenarios `No/Medium/Extreme Altitude` y deltas de score | ✅ Implementado en F10 |

---

## 3. Lo que NO se puede implementar (bloqueado por datos)

| Requisito del hackathon / rúbrica | Por qué está bloqueado |
|---|---|
| **Park holdout real (validación por estadio)** | No hay `stadium_id`/`park_id`; `game_anon_id` es un identificador anónimo de cada partido, no de cada estadio, y no se puede agrupar juegos por parque real. Lo que **sí** se puede hacer es un **holdout por categoría de altitud** (`Extreme` vs `No` vs `Medium Altitude`), no un holdout por estadio físico. |
| Delta específico Harp Helú vs. nivel del mar | No hay identificación del Harp ni `altitude_m`; solo bucket `altitude_category`. `Extreme Altitude` agrupa todos los parques de alta altitud, no es solo el Harp Helú. |
| Simulación física exacta de densidad/aire | Faltan densidad, temperatura, presión, humedad; no se puede convertir altitud en efecto físico exacto de Magnus/arrastre. |
| xRunValue / expected runs por estado | Faltan `runners_on_base`, PA ID y run value por estado; `RunsScored`/`OutsOnPlay` no son equivalentes. |
| `tunnel_similarity` / efecto túnel real | Se puede aproximar con geometría de trayectoria, pero no hay secuencia real ni "túnel" entre pitches consecutivos. |
| `prev_pitch_type` (secuencia real) | No existe orden/cronología dentro del PA ni `pitch_sequence`. |
| `P(out within PA)` | No se puede agregar por PA sin identificador de aparición al plato ni resultados posteriores del bateador. |

---

## 4. Qué falta implementar en la rama de Ceci (tareas pendientes)

Estas son las tareas que sí podemos hacer con lo que ya existe en `DiablosHack-ceci-fase-9`, sin depender de nuevos datos externos:

### 4.1 Mergear la rama `backend` a `fase-9` (o integrar el backend dentro de `fase-9`)

- **Estado:** El backend FastAPI está en `origin/backend` (commit `7ccd42d`) que ya incluye F10; falta hacer merge a la rama principal de trabajo `fase-9` o mantener `fase-9` como rama única y sincronizar.
- **Por qué:** Para tener el servicio `GET /score`, `POST /simulate`, `GET /scouting`, `GET /health` y Swagger accesibles desde la misma base de código de F9/F10.
- **Entregable:** `backend/` integrado y ejecutándose con `run_backend.ps1`/`run_backend.sh`.

### 4.2 Dashboard / Simulador funcional para el coach

- **Qué falta:** Una interfaz (puede ser CLI, notebook, o pequeña web) donde el coach pueda:
  - Ingresar las features físicas de un pitch (11 inputs) o un `pitch_uid` y obtener el `experimental_score`/`F10` index y probabilidades de eventos.
  - Comparar lado a lado el mismo pitch en `No Altitude` vs. `Extreme Altitude` (o `Medium`) usando el simulador residual de F10 (`experiments/phase10_simulator.py`).
  - Ver el "mapa de movimiento" (IVB vs HB) coloreado por score y por `altitude_category`.
- **Por qué:** Entregable obligatorio #4 del hackathon ("Dashboard Simulador").
- **Restricción:** Como no hay Harp Helú específico, la comparación será por `altitude_category` (ej. `Extreme Altitude` como proxy de CDMX), con advertencia explícita de que no es un delta específico del Harp.

### 4.2.1 Validación "park-holdout" propuesta (versión factible: holdout por categoría de altitud)

> **Estado: implementado para movimiento IVB/HB** (`experiments/altitude_holdout.py`, `docs/ALTITUDE_HOLDOUT.md`). Quedan pendientes los eventos (log loss/Brier) y la integración con el simulador.

- **Qué podemos implementar en lugar de un park holdout real:**
  1. **Entrenamiento/exclusión por categoría de altitud:** entrenar el modelo de eventos/movimiento usando solo `No Altitude` + `Medium Altitude` y evaluar únicamente en `Extreme Altitude` (o viceversa), para medir generalización entre ambientes altos y bajos.
  2. **Comparación de coeficientes/métricas por categoría:** reportar log loss/Brier/RMSE de `IVB`/`HB` y delta de score F10 por `altitude_category` (`Extreme`, `Medium`, `No`) como sustituto de comparación entre estadios de altitud alta y baja.
  3. **Simulador contrafactual como "park comparator":** usar `phase10_simulator.py` para mover un pitch de `No Altitude` a `Extreme Altitude` y viceversa, como comparador de categorías de parque (no como identificación de estadios específicos).
- **Por qué es la mejor aproximación factible:** agrupa estadios por el único atributo ambiental disponible (`altitude_category`), que ya viene asignado por los organizadores, y no requiere `stadium_id`/`park_id`.
- **Limitación explícita:** esto **no** es un park holdout real ni una prueba de transferencia a un estadio concreto (no hay identificación del Harp Helú ni de cada parque). Es una evaluación de generalización entre *categorías* de altitud.

### 4.3 Reportes visuales (gráficas) para F9 y F10

- **Qué falta:** Generar las figuras SVG/PNG similares a las de `REPORTE_F*.md` de nuestra carpeta anterior:
  - Curvas de calibración por categoría de altitud y por protocolo (A/B/C).
  - Importancia de features (permutación) del arsenal regularizado y de los modelos de movimiento.
  - Comparación de RMSE de `IVB`/`HB` con y sin `altitude_category` por categoría.
  - Barras/heatmap de los deltas del simulador (`No→Extreme`, `Extreme→No`, etc.).
  - Distribución del score F10 por `altitude_category` y por tipo de pitch.
- **Por qué:** El hackathon pide cuantificación visual del efecto altitud y comparación CDMX vs. otros estadios (usando buckets como proxy).
- **Scripts a crear:** `scripts/generar_reporte_f9.py`, `scripts/generar_reporte_f10.py` (o `reporte_f9/*.svg`, `reporte_f10/*.svg`) y un `docs/REPORTE_F9.md` / `docs/REPORTE_F10.md` ejecutivo en español con las gráficas.

### 4.4 Documento técnico final (6–10 páginas)

- **Qué falta:** Redactar el informe técnico que cubra:
  - Marco teórico sabermétrico + física del béisbol (separación Stuff/Location/Pitching, efecto Magnus, densidad del aire, referencias a Nathan/SABR/FanGraphs).
  - Decisiones de modelado (LightGBM, calibración por temperatura, protocolos A/B/C, arsenal regularizado, simulador residual, controles de soporte).
  - Definición formal de la escala `100 + 10·z` y del score usado (S0 para eventos, `F10_regularized_context_standardized_utility_v1` para simulador).
  - Validación fuera de muestra: season holdout (A), pitcher holdout (B y pitchers no vistos 2024 en movimiento), y "park holdout proxy" por `altitude_category` explicando sus límites.
  - Cuantificación del efecto altitud en movimiento (RMSE −13.7% / −14.2% y deltas de score ~−3.17/+2.74 en Extreme↔No).
  - Alcance y fronteras (no xRunValue, no stadium ID, no causalidad, no secuencia PA).
- **Por qué:** Entregable obligatorio #5 del hackathon.

### 4.5 Perfil físico ideal y recomendaciones operativas

- **Qué falta:** Un análisis/deliverable que responda explícitamente:
  - ¿Qué combinación de velocidad, movimiento (IVB/HB), spin, release y arsenal maximiza el score en `Extreme Altitude`? (H1)
  - ¿Los pitch types basados en `velo_diff_vs_fb` (changeup, splitter) ganan valor relativo vs. rectas? (H2)
  - ¿Los pitchers con más `groundball` o más `ivb_diff_vs_fb`/`hb_diff_vs_fb` extremos son más valiosos en altitud? (H3)
  - ¿`spin_rate` solo es insuficiente y `spin_per_mph`/`movement_magnitude`/geometría capturan mejor el "shape"? (H4)
- **Por qué:** Entregables obligatorios #2 y #3 del hackathon.
- **Método:** Usar el simulador F10 para agrupar por pitcher/tipo/arsenal y reportar agregados con soporte mínimo (`scouting.csv` extendido a nivel pitcher-arsenal, no solo pitcher-tipo).

### 4.6 Entrevista de 10 minutos con coach/director (Aplicabilidad real)

- **Qué falta:** Preparar un script/demo de 10 minutos mostrando:
  - Score de un pitch en `Extreme` vs. `No` altitud.
  - Ranking de pitchers por score en cada bucket.
  - Perfil ideal de prospecto para CDMX.
  - Una recomendación táctica (ej. "preferir sinker/groundball profiles en Extreme").
- **Por qué:** Criterio de evaluación "Aplicabilidad real" (25%): el jurado evalúa si cambiarían decisiones de reclutamiento y táctica.

### 4.7 Integración final de artefactos y validación

- **Qué falta:** Ejecutar localmente en `DiablosHack-ceci-fase-9` con datos y `.venv` propios:
  - Restaurar `data/runs/e9e0b1114dc68eb2`, `artifacts/modeling/f8-release-20261013`, `artifacts/modeling/f9-full`, `artifacts/modeling/f10-full`.
  - Correr `run_phase9.ps1 check`, `run_phase10.ps1 check`, tests, y levantar `backend` para verificar endpoints.
- **Nota:** Los artefactos pesados no están en Git por `.gitignore`; se tienen que copiar de la máquina de Ceci o de nuestra carpeta `DiablosHack` (ajustando `RELEASE = .../f8-release-20261013` en `experiments/phase9.py` y `phase10.py`).

---

## 5. Resumen de prioridades

| Prioridad | Tarea | Dependencia |
|---|---|---|
| 🔴 Alta | Mergear `backend` a `fase-9` y exponer F10 simulator + scores | Ninguna (código ya existe) |
| 🔴 Alta | Dashboard/simulador comparativo `Extreme` vs `No` altitude | Backend + `phase10_simulator.py` |
| 🔴 Alta | Implementar holdout por categoría de altitud (entrenar en `No`+`Medium` y evaluar en `Extreme`, o viceversa) | Cohorte F10 + `altitude_category` existente |
| 🔴 Alta | Documento técnico 6–10 páginas + `REPORTE_F9.md`/`REPORTE_F10.md` con gráficas | Resultados F9/F10 ya calculados |
| 🟡 Media | Perfil físico ideal + recomendaciones operativas (H1–H4) | Simulador F10 + `scouting.csv` agregado |
| 🟡 Media | Preparar demo de 10 minutos para coach/director | Dashboard + perfil ideal |
| 🟡 Media | Ejecutar `check` F9/F10 localmente y generar artefactos faltantes | Copiar `data/` y `artifacts/` de la máquina o carpeta anterior |
| ⚪ Baja | Pedir a organizadores `stadium_id`, `altitude_m`, `runners_on_base` | Imposible según instrucción actual; solo para cerrar brecha final |

---

## 6. Advertencias finales

- **No inventar xRunValue ni stadium mapping:** el contrato prohíbe sustituir insumos faltantes con supuestos. Todo delta de altitud se reportará como asociación por `altitude_category`, no como efecto causal del Harp Helú.
- **Rama base:** Todo el desarrollo se hará sobre `DiablosHack-ceci-fase-9` (rama `fase-9` de Ceci + merge de `backend`), no sobre `fase-9-ian`.
- **Reutilización permitida:** Solo se pueden tomar de `fase-9-ian` piezas que no requieran re-entrenar (ej. guiones de visualización `scripts/generar_reporte_*.py` como referencia), pero el código/modelos/reportes finales deben basarse en F9/F10 de Ceci.
