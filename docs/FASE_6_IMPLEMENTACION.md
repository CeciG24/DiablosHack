# Fase 6: ambiente y simulación de asociaciones

Cierre: 11 de octubre de 2026.

**Implementación: verified. Decisión científica: `retain_reference` en protocolo A.**

## Qué se implementó

Se añadió `altitude_category` a Pitching en una ablación con control sin ambiente. Los dos modelos se reentrenan en los mismos pitches de 2024 y usan las mismas particiones de 2025 para desarrollo, calibración y revisión. También se implementó un simulador que cambia exclusivamente la categoría ambiental, guarda deltas de las seis probabilidades y advierte entradas fuera del soporte de ajuste.

- `modeling/environment.py`: modelo ambiental, soporte estimado únicamente en entrenamiento, simulador y bootstrap de promedios de cohorte.
- `modeling/phase6.py`: dependencias verificadas, entrenamiento pareado, calibración, subgrupos, escenarios y decisiones.
- `scripts/check_phase6.py`: reproducción independiente de modelos, calibración, métricas, subgrupos, deltas e intervalos.
- `tests/modeling/test_environment.py`: 18 pruebas nuevas de particiones, simulación, nulos, categorías, soporte y persistencia.
- CLI y `run_modeling.ps1`: acciones `f6-smoke` y `f6`, siempre con el Python de `.venv`.

## Por qué se implementó así

F5 no promovió arsenal. Por eso F6 continúa con el Pitching aprobado de A, sin seleccionar entre A y C mediante métricas que provienen de entrenamientos diferentes. Se conservan las tres familias: Stuff físico y Location no reciben ambiente; el delta ambiental corresponde solamente a Pitching. Arsenal no participa en este modelo A, y el simulador tampoco modifica campos de arsenal que reciba como metadatos.

El control se reentrena para comprobar la comparación sobre filas idénticas; en la corrida completa sus predicciones brutas y calibradas reproducen exactamente el Pitching aprobado de F4. Se conserva la configuración de F3: LightGBM 4.6.0 en CPU, cuatro hilos, semilla 20260929, 31 hojas, mínimo 200 filas por hoja, learning rate 0.05 y L2=5. Presupuesto máximo de 400 rondas (60 en smoke) con parada temprana de 30 rondas en desarrollo. No se hace una nueva búsqueda de hiperparámetros.

Los vocabularios categóricos, rangos y recuentos de soporte se ajustan solo en 2024. Cada candidato se calibra mediante temperatura escalar usando exclusivamente calibración 2025. La revisión puede conservar identidad si la temperatura perjudica log loss, sin reajustarla.

La promoción exige al menos 1% de reducción relativa de log loss y límite superior del IC95% de pérdida candidato menos control inferior a cero, usando 500 remuestreos de partidos completos. Los subgrupos son diagnósticos sin corrección por comparaciones múltiples y no deciden la promoción global.

## Datos y cobertura

Versión fijada: `c1c8ba48818dc878`. No se abrieron etiquetas de 2026. Se conserva la población común F0/F3 con sus filtros originales, incluida disponibilidad de categoría ambiental.

| Partición | Categoría | Pitches | Pitchers | Partidos |
|---|---|---:|---:|---:|
| calibration | Extreme Altitude | 15,603 | 307 | 51 |
| calibration | Medium Altitude | 16,552 | 245 | 54 |
| calibration | No Altitude | 27,212 | 354 | 92 |
| development | Extreme Altitude | 40,752 | 419 | 135 |
| development | Medium Altitude | 33,642 | 380 | 111 |
| development | No Altitude | 60,026 | 461 | 201 |
| phase_review | Extreme Altitude | 15,400 | 275 | 51 |
| phase_review | Medium Altitude | 14,922 | 256 | 48 |
| phase_review | No Altitude | 27,860 | 363 | 93 |
| train | Extreme Altitude | 65,546 | 462 | 223 |
| train | Medium Altitude | 59,924 | 432 | 204 |
| train | No Altitude | 114,239 | 483 | 406 |

Las categorías guardadas son Extreme Altitude, Medium Altitude y No Altitude. No se convierten a metros ni se interpretan como estadios concretos.

## Resultados de la ablación

| Modelo y partición | Pitches | Log loss | Brier multiclase |
|---|---:|---:|---:|
| control / calibration | 59,367 | 1.03268406 | 0.53525908 |
| control / phase_review | 58,182 | 1.03235300 | 0.53472264 |
| environment / calibration | 59,367 | 1.03260876 | 0.53533960 |
| environment / phase_review | 58,182 | 1.03253997 | 0.53490402 |

Comparación de revisión: **-0.0181%** de reducción relativa, 58,182 pitches de 192 partidos. Delta candidato − control: 0.00018697; IC95% [-0.00032030, 0.00068060].

Decisión: **retain_reference**. Se conserva el Pitching sin ambiente. El candidato ambiental y su simulador permanecen experimentales; sus deltas no se anuncian como una mejora predictiva validada.

| Candidato | Temperatura | Calibración seleccionada | Mejor iteración |
|---|---:|---|---:|
| control | 0.98694197 | temperature | 323 |
| environment | 0.98719591 | temperature | 337 |

## Desempeño por subgrupo

Se registraron 61 grupos: 12 con muestra suficiente y 49 marcados `insufficient_data`. Se reporta por categoría, tipo de pitch, mano del pitcher, lado del bateador y combinación categoría/tipo/mano del pitcher. Para informar métricas y bootstrap se exigen 200 filas y 20 por clase tanto en entrenamiento como en revisión. Los insuficientes conservan conteos y cobertura, con métricas nulas y sin ranking.

| Categoría en revisión | Pitches | Log loss control | Log loss ambiente | Mejora relativa |
|---|---:|---:|---:|---:|
| Extreme Altitude | 15,400 | 1.05076890 | 1.05064016 | 0.0123% |
| Medium Altitude | 14,922 | 1.00922110 | 1.00852976 | 0.0685% |
| No Altitude | 27,860 | 1.03456296 | 1.03539487 | -0.0804% |

## Semántica y límites del simulador

La etiqueta obligatoria es `fixed_shape_environment_association`. Para cada entrada se mantienen velocidad, movimiento observado, release, ubicación, conteo, manos y demás campos; únicamente cambia `altitude_category`. **No se reduce IVB nuevamente**. La resta es P(evento | escenario destino) menos P(evento | categoría original), con el mismo modelo y calibrador. Las seis diferencias suman cero salvo precisión numérica. No son carreras, cambios físicos de trayectoria ni efectos causales.

La API devuelve una fila por entrada identificada con `pitch_uid`, probabilidades origen/destino, deltas, estado y advertencias. Las categorías no vistas —incluido un nombre como Harp Helú— devuelven `unsupported_environment` y probabilidades/deltas nulos. Las filas con features inválidas devuelven `invalid_input`; un esquema incompleto o IDs duplicados rechazan el lote.

El soporte combina rangos mínimos/máximos por categoría en las variables numéricas y al menos 200 observaciones en la combinación categoría/tipo/mano del pitcher/lado del bateador. Una combinación escasa o un valor fuera de rango produce `outside_support`. Esto solo comprueba soporte marginal y recuentos: no demuestra plausibilidad física conjunta ni soporte multivariado completo. El simulador devuelve `recommendation_allowed=False` en todos los casos.

Los intervalos remuestrean partidos de revisión con modelos fijos y conservan solo pitches con soporte comprobado tanto en origen como en destino. Describen incertidumbre del promedio de asociación de esa cohorte, ponderado por pitch; no incertidumbre individual, causal ni de reentrenamiento. Las poblaciones pueden cambiar entre destinos: sus medias no forman una comparación pareada entre categorías.

| Destino fijo | Pitches dentro del soporte de ambos escenarios | Excluidos | Partidos |
|---|---:|---:|---:|
| Extreme Altitude | 57,219 | 963 | 192 |
| Medium Altitude | 57,788 | 394 | 192 |
| No Altitude | 57,929 | 253 | 192 |

Ejemplo descriptivo: deltas medios de P(in_play) en **puntos porcentuales**. Cada fila compara el destino fijo con la categoría original de sus pitches elegibles; no es una recomendación.

| Destino | Delta medio | IC95% del promedio |
|---|---:|---|
| Extreme Altitude | 0.10230 | [0.08093, 0.12517] |
| Medium Altitude | -0.21343 | [-0.23605, -0.18952] |
| No Altitude | 0.02787 | [0.01171, 0.04459] |

## Pruebas y reproducción

- 104 pruebas unitarias aprobadas; 18 nuevas de ambiente y simulación.
- Un primer intento de prueba de recarga encontró el bloqueo de la carpeta temporal de Windows. La repetición autorizada fuera del aislamiento, con el mismo `.venv`, aprobó la suite completa.
- Smoke: 45 controles y 31 hashes verificados; 9,321 predicciones y 5,700 filas de escenario. No permite conclusiones científicas.
- Completa: 47 controles, 33 hashes, 251,969 predicciones y 174,546 filas de escenario. Duración del entrenamiento y controles internos: 10.25 minutos.
- Ambos modelos se reentrenaron determinísticamente y se recargaron sin diferencias. El control completo reproduce exactamente las probabilidades aprobadas en F4.
- Verificador independiente: 6 métricas globales, 61 subgrupos y 3 escenarios con intervalos reproducidos. Diferencia máxima de probabilidades: 0.0.
- Stuff y Location permanecen invariantes al cambiar categoría; el simulador conserva física y ubicación. Misma categoría produce delta cero. Entradas fuera de soporte generan advertencias.
- Los calibradores se reprodujeron usando exclusivamente calibración 2025. Contrato y configuración coherentes; 2026 sellado.

Se comprobó además la estructura XML de las ocho curvas SVG de las corridas rápida y completa. Los verificadores que exigen hashes del código deben ejecutarse con la revisión de código de su experimento; para verificar fases anteriores tras cambios de interfaz, usar su commit correspondiente. Sus artefactos originales se conservan.

## Cómo probarlo

Desde la raíz del proyecto:

```powershell
.\run_modeling.ps1 tests
.\run_modeling.ps1 contract
.\.venv\Scripts\python.exe scripts/check_phase6.py f6-smoke-check
.\.venv\Scripts\python.exe scripts/check_phase6.py f6-full-check
```

Para ejecutar nuevos experimentos sin sobrescribir los anteriores:

```powershell
.\run_modeling.ps1 f6-smoke
.\run_modeling.ps1 f6
```

Para probar el simulador con datos de revisión ya autorizados, guarda el siguiente ejemplo en un archivo local y ejecútalo con `.\.venv\Scripts\python.exe archivo.py`:

```python
import pandas as pd
from modeling.environment import EnvironmentSimulator
folder = 'artifacts/modeling/f6-full-check/F6'
inputs = pd.read_parquet(folder + '/cohort.parquet')
inputs = inputs.loc[inputs.partition.eq('phase_review')].head(10).drop(columns='y_event')
simulator = EnvironmentSimulator.load(folder)
comparison = simulator.simulate(inputs, 'Extreme Altitude')
print(comparison[['pitch_uid', 'delta_p_in_play', 'status', 'input_support_status', 'warnings']])
unknown = simulator.simulate(inputs, 'Harp Helu')
assert unknown.status.eq('unsupported_environment').all()
```

Para datos propios basta `pitch_uid`, las variables de `modeling.datasets.PITCHING` y `altitude_category`. No se necesitan etiquetas ni pitcher conocido. `simulator.predict(inputs)` devuelve las probabilidades del candidato ambiental observado, que puede seguir experimental; no sustituye por sí mismo la política aprobada. La rama aprobada queda registrada en `policy.json` y en las columnas `selected_*` de `predictions.parquet`.

## Artefactos y alcance pendiente

- `artifacts/modeling/f6-full-check/F6/`: control y candidato, calibradores, curvas SVG, cohorte, probabilidades, cobertura, soporte, deltas, intervalos y manifiestos.
- `artifacts/modeling/f6-smoke-check/F6/`: prueba rápida.
- `docs/F6_FULL_VALIDATION.json`, `docs/F6_SMOKE_VALIDATION.json`, `docs/F6_VALIDATION.json`: evidencia agregada para versionar.

Los manifiestos conservan la configuración `in_progress` y hashes de inicio; el manifiesto final queda verified, y el contrato vigente se actualiza al cierre. Los datos y modelos permanecen locales y excluidos de Git. No se ejecutó un park holdout ni se simuló Harp específicamente: faltan estadio, condiciones atmosféricas y altitud numérica. La revisión 2025 es reutilizada para decisiones, no test final independiente.

F7 queda habilitada para scores provisionales cuando se solicite. F7/F8 no se ejecutaron; no hay xRunValue ni scores nuevos, y 2026 continúa sellado.
