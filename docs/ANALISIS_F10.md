# Análisis Detallado de Resultados — Fase 10 (Rama `fase-9` de Ceci)

**Fecha de análisis:** 18 de octubre de 2026
**Commit revisado:** `7dff757` (*Implement F10 regularized arsenal and altitude-conditioned movement experiments*)
**Experimento:** `f10-full`
**Archivos de evidencia originales:**
- `docs/FASE_10_IMPLEMENTACION.md`
- `docs/FASE_10_ESTRATEGIA.md`
- `docs/F10_RESULTS.json`
- `docs/F10_AUDIT.json`
- `docs/F10_VALIDATION.json`

---

## 1. Resumen Ejecutivo (Resultado Central)

La Fase 10 de Ceci resuelve una de las principales limitaciones metodológicas dejadas por la Fase 9: el efecto del ambiente/altitud se separó correctamente en una cadena causal de dos pasos: **`altitude_category` $\rightarrow$ Movimiento Físico (`IVB`/`HB`) $\rightarrow$ Eventos / Score**.

**Hallazgos clave:**

1.  **La altitud SÍ es un predictor fuerte del movimiento físico de la bola.**
    Incluir `altitude_category` en los modelos de movimiento reduce el error de predicción (RMSE) en ~14% tanto para quiebre vertical (`induced_vert_break`) como horizontal (`horz_break`), con diferencias estadísticamente muy significativas (MSE baja 25.5% y 26.4%).
2.  **Sin embargo, esta ruta *aún no* se traduce en una mejora significativa del modelo de eventos (Stuff+) ni en un cambio a producción.**
    *   El arsenal regularizado mejoró la cobertura de pitchers con historia (de 30,443 a 58,182 lanzamientos en review 2025), pero la mejora de su log loss es marginal (+0.076% relativo).
    *   La inclusión de trayectoria física real bajó el log loss ~28%, pero un control estricto demostró que esto se debe a que los puntos cercanos al plato filtran información de ubicación final (`Location`), no por "tunneling" ni relación con el arsenal.
    *   El score simulado muestra penalizaciones de ~3.2 puntos en el índice al trasladar un pitch de `No Altitude` a `Extreme Altitude` debido a la pérdida de quiebre proyectada.
3.  **Estado general:** Verificado como `verified_exploratory` (138 tests unitarios pasados, 14 controles internos y 14 controles de auditoría en `true`). No se accedió a datos de 2026. Los modelos F8 y F9 permanecen intactos y no fueron reemplazados.

---

## 2. Arquitectura Implementada y Métodos

Ceci añadió código nuevo aislado en `experiments/` para no romper F8/F9:

-   **`experiments/phase10.py`**: Orquestador principal; entrena 5 modelos de eventos (Protocolo C ampliado con población completa) y 4 de movimiento; corre los 6 contrastes predeclarados; genera el índice y los escenarios.
-   **`experiments/phase10_features.py`**: Auditoría geométrica de trayectorias 2024 y construcción de las referencias de arsenal regularizadas.
-   **`experiments/phase10_models.py`**: Envoltorios de LightGBM para modelos de eventos y regresores de movimiento.
-   **`experiments/phase10_simulator.py`**: Simulador contrafactural con anclaje de residuos y control de soporte.
-   **`experiments/check_phase10.py`**: Auditoría independiente que recalcula métricas, recompone probabilidades, verifica hashes de F8/F9 y valida el comportamiento del simulador.
-   **`config/phase10.json`**: Configuración fijada (200 rondas, semilla `20260929`, fuerza del prior $k=30$, 2000 remuestreos de bootstrap y tolerancias de trayectoria).

### Métodos estadísticos y diseño
-   **Población:** Cohorte común del contrato ($N_{\text{review}} = 58,182$ lanzamientos 2025). Se amplió el modelo de arsenal a pitchers sin historia usando priors de grupo ($\text{mano},\text{tipo}$) en lugar de descartarlos.
-   **Regularización de historia:** Para cada pitcher, mano y tipo de pitch se calcula el promedio de la historia 2024 y se mezcla con el promedio del grupo (mano-tipo) con peso $w = n / (n + 30)$.
-   **Auditoría Geométrica:** El polinomio de trayectoria se validó como $p(t) = c_0 + c_1 t + c_2 t^2$ (eje $x$ longitudinal al home, $y$ vertical, $-z$ lateral), exigiendo error mediano $\le 0.05$ pies y $p95 \le 0.25$ pies.
-   **Evaluación:** 6 contrastes incrementales predeclarados con **bootstrap pareado por partido (2,000 remuestreos)** e intervalos de confianza al 99.1667% (corrección Bonferroni).

---

## 3. Resultados de los Modelos de Movimiento (IVB y HB)

Los modelos de regresión usaron únicamente variables físicas pre-evento (tipo de pitch, mano, velocidad, spin/eje, release, extensión, sin ubicación ni resultado) entrenados exclusivamente en 2024 ($N=239,709$).

### 3.1. Desempeño General en `review` 2025

| Variable de Movimiento | Población de evaluación | $N$ | RMSE sin altura (pulgadas) | RMSE con `altitude_category` (pulgadas) | Reducción de RMSE |
|---|---|---:|---:|---:|---:|
| `induced_vert_break` (IVB) | Todos (review 2025) | 58,182 | 2.4057 | **2.0760** | **−13.71%** |
| `induced_vert_break` (IVB) | Solo pitchers no vistos en 2024 | 26,057 | 2.5037 | **2.1749** | **−13.13%** |
| `horz_break` (HB) | Todos (review 2025) | 58,182 | 2.4380 | **2.0917** | **−14.20%** |
| `horz_break` (HB) | Solo pitchers no vistos en 2024 | 26,057 | 2.5671 | **2.2075** | **−14.01%** |

### 3.2. Desglose por Categoría de Altitud (Auditoría Independiente)

| Variable de Movimiento | Categoría de Altitud | $N$ | RMSE Control (sin altura) | RMSE Ambiente (con altura) | Mejora absoluta (in) | Mejora relativa |
|---|---|---:|---:|---:|---:|---:|
| `induced_vert_break` | `Extreme Altitude` | 15,400 | 2.3967 | **1.8605** | −0.5362 | −22.37% |
| `induced_vert_break` | `Medium Altitude` | 14,922 | 2.0547 | **1.8895** | −0.1652 | −8.04% |
| `induced_vert_break` | `No Altitude` | 27,860 | 2.5787 | **2.2748** | −0.3039 | −11.79% |
| `horz_break` | `Extreme Altitude` | 15,400 | 2.2547 | **1.7778** | −0.4770 | −21.16% |
| `horz_break` | `Medium Altitude` | 14,922 | 1.9864 | **1.8645** | −0.1219 | −6.14% |
| `horz_break` | `No Altitude` | 27,860 | 2.7367 | **2.3513** | −0.3855 | −14.09% |

> **Conclusión de Movimiento:** El efecto de la categoría de altitud sobre la predicción de quiebres verticales y horizontales es masivo (supera ampliamente el umbral del 1% e incluso el 25% en MSE) y se confirma incluso en pitchers que no tienen historia en 2024.

---

## 4. Resultados de los Modelos de Eventos (`y_event`)

Los 5 modelos se entrenaron en `development` 2025 (134,420 filas), se calibraron en `calibration` 2025 (59,367 filas) y se evaluaron en `review` 2025 (58,182 filas).

### 4.1. Métricas en `review` 2025

| Variante F10 | Features adicionales sobre `base` | Log Loss Calibrado | Brier Multiclase |
|---|---|---:|---:|
| `base` | *(Contexto + física derivada, igual a F9 `context_physics`)* | 1.446522 | 0.731647 |
| `regularized` | Arsenal regularizado 8 tipos + fiabilidad y uso | **1.445426** | **0.730977** |
| `trajectory` | `regularized` + coordenadas/velocidades en planos a 40/20/8 pies | **1.037725** | **0.535532** |
| `geometry` | `trajectory` + distancias/deltas contra perfil de rectas histórico | 1.043683 | 0.538187 |
| `environment` | `geometry` + `altitude_category` | 1.043714 | 0.538204 |
| **Referencia F8** | *Modelo `Pitching` congelado en F8, aplicado a estas mismas filas* | ***1.032353*** | ***0.534723*** |

### 4.2. Los 6 Contrastes Estadísticos Predeclarados

| Contraste | Medida de pérdida | Reducción rel. | $\Delta$ (Candidato − Control) | Intervalo de Confianza 99.17% | ¿Supera umbral de promoción (≥1% e IC<0)? |
|---|---|---:|---:|---|---|
| `regularized` vs `base` | Log Loss | +0.076% | $-0.001096$ | $[-0.002308, +0.000293]$ | **No** (incolcuyente) |
| `trajectory` vs `regularized` | Log Loss | **+28.206%** | $-0.407701$ | $[-0.416261, -0.398165]$ | **Sí** *(pero por ubicación, no arsenal)* |
| `geometry` vs `trajectory` | Log Loss | −0.574% (empeora) | $+0.005958$ | $[+0.003279, +0.008602]$ | **No** (descartado) |
| `environment` vs `geometry` | Log Loss | −0.003% | $+0.000032$ | $[-0.000657, +0.000800]$ | **No** |
| `IVB`: Ambiente vs Control | MSE | **+25.533%** | $-1.477646$ | $[-1.805393, -1.163467]$ | **Sí** |
| `HB`: Ambiente vs Control | MSE | **+26.389%** | $-1.568555$ | $[-1.884931, -1.286272]$ | **Sí** |

### 4.3. Comparación retrospectiva F9 vs F10 (subcohorte con historia válida $N=30,443$)

| Candidato | Log Loss F9 | Log Loss F10 | Reducción relativa |
|---|---:|---:|---:|
| `base` | 1.453850 | 1.450187 | +0.252% |
| `regularized` | 1.451866 | 1.448603 | +0.225% |
| `environment` | 1.451452 | **1.057931** | **+27.112%** |

> **Aclaración importante (mencionada por Ceci):** El salto del ~27% en `environment` de F9 a F10 no se debe a la altura en sí misma, sino a que el `environment` de F10 hereda la variable `trajectory` que captura información de ubicación final del lanzamiento.

---

## 5. Simulador Ambiental Contrafactural (`phase10_simulator.py`)

El simulador de F10 aplica un ajuste contrafactual que **conserva el residuo individual del pitch**:
$$ \text{movimiento}_{\text{destino}} = \text{movimiento}_{\text{observado}} + \hat{g}(\text{físicas}, \text{destino}) - \hat{g}(\text{físicas}, \text{origen}) $$

Luego recalcula todas las variables físicas derivadas, el diferencial de arsenal y el score del modelo `regularized` (`F10_regularized_context_standardized_utility_v1`, escala 100±10).

### Resultados de escenarios exploratorios sobre muestra de 1,000 lanzamientos `review` 2025:

| Cambio de ambiente simulado (Origen $\rightarrow$ Destino) | Lanzamientos soportados / solicitados | $\Delta$ medio del Score F10 | Intervalo de Confianza 99.17% |
|---|---:|---:|---|
| `No Altitude` $\rightarrow$ `Extreme Altitude` | 490 / 493 | **−3.171 puntos** | $[-3.642, -2.724]$ |
| `No Altitude` $\rightarrow$ `Medium Altitude` | 478 / 493 | **−2.697 puntos** | $[-3.117, -2.272]$ |
| `Medium Altitude` $\rightarrow$ `Extreme Altitude` | 231 / 260 | **−0.519 puntos** | $[-0.812, -0.217]$ |
| `Extreme Altitude` $\rightarrow$ `No Altitude` | 244 / 247 | **+2.737 puntos** | $[+2.196, +3.352]$ |
| `Medium Altitude` $\rightarrow$ `No Altitude` | 254 / 260 | **+3.034 puntos** | $[+2.275, +3.789]$ |
| `Extreme Altitude` $\rightarrow$ `Medium Altitude` | 217 / 247 | **+0.471 puntos** | $[+0.236, +0.725]$ |
| `Origen = Destino` (ej. `No` $\rightarrow$ `No`) | 998 / 1,000 | **0.000 puntos** | $[0.000, 0.000]$ |

*(Interpretación: al pasar de `No Altitude` a `Extreme Altitude`, el pitch pierde quiebre proyectado, lo que baja el score de calidad promedio en ~3.2 puntos; el efecto inverso ocurre al bajar a nivel del mar).*

**Controles de soporte del simulador:** Rechaza explícitamente escenarios sin soporte (ej. pedir "Harp Helú" directo) si no hay al menos 200 lanzamientos y 5 pitchers con 30 lanzamientos del mismo tipo en ambas categorías de origen y destino, además de validar que el lanzamiento esté dentro del rango físico del contrato.

---

## 6. Auditoría, Validación y Estado Actual

- **Pruebas ejecutadas:** Pasaron **138 pruebas unitarias** (13 nuevas específicas de F10 en `tests/test_phase10.py`).
- **Controles internos y auditoría externa:** **14 controles internos** y **14 controles de auditoría independiente** verificados, incluyendo recálculo de features de arsenal, reconstrucción de referencias 2024, recálculo de RMSE de movimiento y hashes de artefactos.
- **Consistencia de releases:** Los hashes de F8 y F9 se comprobaron (`F8_unchanged: true`, `F9_unchanged: true`) y el acceso a 2026 sigue bloqueado (`new_2026_access: false`, `test_access_unchanged: true`).
- **Estado final declarado:** `verified_exploratory` (resultados válidos como evidencia exploratoria, pero no sustituyen el release F8 de producción).

---

## 7. Qué falta o qué está pendiente (Siguientes pasos)

Aunque F10 aportó evidencia física importante (la altitud sí cambia el movimiento), para el hackathon y el producto real aún falta:

1.  **Identificación física real de estadios:** `altitude_category` es una variable gruesa; sigue faltando el `stadium_id`/`park_id`, la identificación del Estadio Alfredo Harp Helú, metros reales de altitud y variables de densidad del aire/temperatura para medir el efecto causal físico exacto.
2.  **Validación fuera de muestra (Park Holdout):** No se hizo un "park holdout" (evaluar en estadios nunca vistos en entrenamiento); se validó en review 2025 y pitchers sin historia, pero el modelo de eventos con `trajectory`/`geometry` se entrenó y evaluó sobre los mismos estadios.
3.  **Target oficial de valor (`xRunValue`):** El índice `F10_regularized_context_standardized_utility_v1` sigue siendo una utilidad provisional de eventos, no el valor de carreras oficial de la liga ni RMSE en carreras.
4.  **Prueba de valor real (Scouting/Coach):** Falta documentar la sesión de 10 minutos con coach/director usando este simulador F10 (ej. "¿Cuánto baja el Stuff+ de este pitcher si lanzamos en CDMX?") y evidenciar cómo eso cambiaría una decisión táctica real.
5.  **Cierre de la brecha de señal de eventos:** El arsenal regularizado aportó poco al log loss (+0.076%); la señal de arsenal sigue siendo débil en la predicción de eventos puros. El gran salto vino de ubicación (trayectoria), que a su vez sigue sin superar al `Pitching` congelado de F8.
