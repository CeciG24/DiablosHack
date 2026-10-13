# Fase 7: índices provisionales y agregación

Fecha: 12 de octubre de 2026. Protocolo A. Datos: `c1c8ba48818dc878`.

## Qué se implementó

Se convierten las probabilidades calibradas aprobadas en **Stuff+, Location+ y Pitching+ provisionales**. Cada fila conserva las seis probabilidades, familia, identificador del lanzamiento, modelo, versión de datos, versión del score, referencia, advertencias y motivo de ausencia de score. Stuff sigue siendo diagnóstico: esta transformación no demuestra una mejora predictiva que las fases anteriores no encontraron.

La versión publicada por esta fase es `event_utility_proxy_v1` (S0):

```text
S0 = P(whiff) + P(called_strike) - 0.5 P(ball) - P(hit_by_pitch)
índice = 100 + 10 (S0 - μ) / σ
```

Foul e in_play tienen peso cero en S0. Los pesos son los fijados por el contrato; no se ajustaron para mejorar resultados. Es una utilidad exploratoria de eventos, **no carreras esperadas, xRunValue ni el Stuff+ validado de FanGraphs**.

Se guardan cinco normalizadores: S0 para las tres familias y S1 para Location/Pitching. Todos usan los mismos **59,367 lanzamientos elegibles de calibración 2025**, pero cada familia y versión tiene su propia μ y σ poblacional (`ddof=0`). Los IDs y su hash quedan guardados. La referencia completa también se usa en la prueba pequeña, por lo que cambiar la muestra de consulta no cambia la escala.

**100 representa la media de esta cohorte elegible, no de toda la LMB.** Diez puntos representan una desviación de la utilidad en esa referencia. No se asignan percentiles ni niveles de reemplazo. La calibración establece la escala; no constituye una evaluación independiente. Los índices de familias diferentes describen componentes diferentes y no deben sumarse ni compararse como si fueran una sola magnitud.

## Por qué se implementó así

La fase 5 conservó la referencia y la fase 6 no promovió el modelo ambiental. Por ello se reutilizan las probabilidades calibradas del protocolo A de F4. Se comprueba que Pitching coincide exactamente con la rama seleccionada de F6. No se vuelven a entrenar modelos ni a escoger hiperparámetros en F7.

Una referencia fija permite comparar consultas sin que cambie el significado de 100. Ajustar μ/σ a cada pitcher, tipo de lanzamiento o categoría de altura ocultaría diferencias y haría depender el score del resto del lote. La implementación rechaza referencias fuera de calibración 2025, IDs duplicados y escalas degeneradas. Probabilidades ausentes, no finitas o inválidas producen score nulo con motivo.

Se verifica la integridad de los artefactos de F6 y sus dependencias F5/F4 antes de construir los índices. Cada experimento guarda configuración, hashes de código y artefactos, procedencia de los modelos y controles ejecutados. Las ejecuciones crean carpetas nuevas y no sobrescriben resultados anteriores.

## Contacto: experimento separado S1

```text
S1 = S0 + 0.5 P(in_play) P(weak | in_play)
        - P(in_play) P(hard | in_play)
```

La versión `event_contact_utility_proxy_v1` aplica exclusivamente a Location y Pitching, cuyas cabezas de contacto fueron promovidas. Para Stuff devuelve nulo con `verified_contact_head_unavailable`: su fallback de prevalencia no se presenta como una cabeza aprobada ni se sustituye por cero.

El premio de 0.5 al contacto débil y la penalización de 1 al fuerte son los valores exploratorios del contrato. Se evalúan 24 variantes: cada uno de los seis pesos no nulos cambia individualmente ±25%, manteniendo signos, en las dos familias con contacto aprobado. Cada variante usa su propia normalización sobre los mismos IDs de calibración; la sensibilidad se mide únicamente en desarrollo 2025 mediante correlación de rangos y cambios absolutos del score. No se selecciona una variante ganadora. Los resultados S1 se almacenan separados y no se mezclan con S0 en agregados o rankings.

## Agregados y cobertura

Se entregan agregados por pitcher y por pitcher/tipo, separados por partición, familia, versión y referencia. El score agregado es la media de los scores válidos por lanzamiento, ponderando cada lanzamiento por igual. Representa la **mezcla observada**, sin estandarizar el arsenal ni promediar los tipos como si tuvieran igual frecuencia.

Cada agregado incluye `n_total`, `n_valid`, `coverage`, probabilidades medias de los lanzamientos puntuados y `score_status`. El denominador incluye todos los registros 2025 de `model_base` en los partidos seleccionados, incluso los excluidos de la cohorte común de predicción. La ejecución completa incluye todos los partidos de ese año; la pequeña selecciona partidos completos con un límite de 20,000 registros. La cobertura describe disponibilidad bajo la política común, no exactitud predictiva.

Un lanzamiento sin predicción elegible conserva su fila y recibe un motivo de ausencia. Un grupo sin predicciones válidas tiene score nulo y `no_valid_predictions`, nunca 100. Los grupos pequeños se conservan con su tamaño explícito; no se les atribuye estabilidad estadística ni se generan recomendaciones o intervalos individuales.

## Clasificación de altura

Se reutilizan las comparaciones de categorías de altura de F6 y se convierten sus probabilidades de origen/destino usando **el mismo normalizador S0 de Pitching**. Se conservan las probabilidades, soporte y advertencias del simulador. Mantener la misma categoría produce delta cero.

Estos resultados pertenecen al **candidato ambiental experimental**, que no fue promovido; no sustituyen los índices de la política aprobada. Son asociaciones con forma física fija, no efectos causales ni correcciones de movimiento por altitud. Tampoco identifican Harp Helú. Los intervalos probabilísticos de F6 conservan su alcance de promedio de cohorte con modelo fijo; F7 no inventa intervalos individuales del score.

## Archivos principales

| Archivo | Función |
|---|---|
| `modeling/scoring.py` | Utilidad S0/S1, normalizador persistente y agregados |
| `modeling/phase7.py` | Verifica dependencias y genera el experimento completo |
| `scripts/check_phase7.py` | Recalcula fórmulas, referencias, cobertura, sensibilidad y escenarios |
| `tests/modeling/test_scoring.py` | Pruebas de invariantes y casos inválidos |
| `config/modeling_contract.json` | Política F7 y pesos fijos |

Los resultados se guardan localmente en `artifacts/modeling/<experimento>/F7/`:

- `scores.parquet`: S0 por lanzamiento con probabilidades y procedencia.
- `scores_pitcher.parquet` y `scores_pitcher_type.parquet`: agregados S0.
- `experimental_contact_scores*.parquet`: S1 y sus agregados, separados.
- `<familia>_<versión>.json`: μ, σ, pesos y referencia fija.
- `reference_ids.parquet` y `population.parquet`: referencia y denominadores auditables.
- `contact_sensitivity.json`: 24 variantes en desarrollo.
- `environment_score_deltas.parquet`: comparaciones ambientales experimentales.
- `policy.json`, `checks.json`, `config.json` y `manifest.json`: política y trazabilidad.

## Cómo probarlo

Desde la raíz del proyecto, siempre con el entorno virtual existente:

```powershell
.\run_modeling.ps1 contract
.\run_modeling.ps1 tests
.\run_modeling.ps1 f7-smoke
.\run_modeling.ps1 f7
```

Para comprobar los experimentos de cierre sin regenerarlos:

```powershell
.\.venv\Scripts\python.exe scripts/check_phase7.py f7-smoke-final
.\.venv\Scripts\python.exe scripts/check_phase7.py f7-full-check
```

El verificador debe finalizar con `status: verified`. Reproduce las fórmulas de manera independiente de `FixedScale`, compara probabilidades con las fuentes, comprueba los IDs de referencia y vuelve a contar los agregados. También reproduce los cambios de la sensibilidad y los scores ambientales. Un cambio de artefacto o de código respecto al manifiesto hace fallar la comprobación.

Para puntuar un lote de probabilidades ya generado por la política aprobada:

```python
from modeling.scoring import FixedScale

scale = FixedScale.load(
    "artifacts/modeling/f7-full-check/F7/pitching_event_utility_proxy_v1.json"
)
resultado = scale.score(lote_de_probabilidades)
```

El lote requiere IDs únicos y las seis columnas `p_ball`, `p_called_strike`, `p_whiff`, `p_foul`, `p_in_play`, `p_hit_by_pitch`. Si declara familia o versión de datos, deben coincidir con el normalizador. No se llama a `fit` con la consulta. La interfaz de inferencia final y el empaquetado de release corresponden a F8.

Los datos y modelos son artefactos locales ignorados por Git: un clon sin ellos necesita reproducir las fases anteriores y el mismo run de datos. Los verificadores históricos exigen el código de su revisión original; para F6 es `00e3410`. F7 verifica los hashes de esos artefactos sin reescribir sus manifiestos.

## Resultados de las ejecuciones

Los experimentos de cierre son `f7-smoke-final` y `f7-full-check`. Ambos pasaron los 25 controles internos y el verificador independiente completo. La evidencia resumida está en `F7_SMOKE_VALIDATION.json`, `F7_FULL_VALIDATION.json` y `F7_VALIDATION.json`, en esta carpeta. La suite completa pasó **111 pruebas**, incluidas siete nuevas de scoring. El primer intento de la suite encontró una restricción de Windows al escribir carpetas temporales; se repitió fuera del aislamiento, usando el mismo Python de `.venv`, y terminó sin errores.

| Partición 2025 | Total de registros | Score válido por familia |
|---|---:|---:|
| Desarrollo | 136,084 | 134,420 |
| Calibración | 60,399 | 59,367 |
| Revisión | 59,661 | 58,182 |
| Total | 256,144 | 251,969 |

La cobertura S0 es **98.3701%** para cada familia: 4,175 registros por familia conservan score nulo. Se guardan 768,432 filas S0, de las cuales 755,907 tienen score válido. Los tres índices comparten cobertura por usar deliberadamente la cohorte común aprobada, aunque sus probabilidades y escalas son diferentes.

| Familia | μ de S0 | σ de S0 (`ddof=0`) |
|---|---:|---:|
| Stuff | 0.071878684271 | 0.039450253261 |
| Location | 0.088272266905 | 0.353936578046 |
| Pitching | 0.090860702080 | 0.359943212851 |

Los archivos JSON conservan la precisión completa; esta tabla redondea para lectura. La media de referencia del índice es 100 y la desviación poblacional es 10 dentro de tolerancia `1e-6` en las cinco escalas. Una desviación calculada con el valor por defecto de pandas (`ddof=1`) será ligeramente distinta; no indica un fallo del normalizador.

Se generaron 4,713 grupos pitcher/partición/familia y 23,625 grupos pitcher/tipo/partición/familia para S0. Respectivamente, 180 y 783 grupos no tienen cobertura y conservan score nulo. Los grupos y probabilidades de S1 se almacenan aparte, incluyendo las filas nulas de Stuff.

Las 24 variantes de sensibilidad S1 dieron correlaciones de rangos entre **0.996553 y 0.999983** respecto a S1 base en desarrollo; el mayor cambio absoluto medio fue **0.829312 puntos**. Esto describe estabilidad frente a esas perturbaciones, no valida los pesos ni convierte la utilidad en carreras.

La ejecución pequeña incluye 19,799 registros, 59,397 filas por versión y 10,725 escenarios ambientales. La completa incluye 174,546 escenarios ambientales y tardó aproximadamente 337 segundos en esta máquina. Ese tiempo incluye verificación de dependencias, agregación y escritura; no es un benchmark de inferencia.

El contrato se marcó `verified` después de cerrar las ejecuciones; sus copias de configuración conservan el estado `in_progress` original y sus hashes intactos. El verificador compara los parámetros científicos, sin exigir que el estado administrativo posterior sea idéntico.

## Límites y siguiente paso

F7 entrega una escala reproducible de utilidad exploratoria y cobertura visible. No valida un valor oficial de carreras. El mapeo de estadios, altitud numérica y otros campos externos siguen pendientes. No se evaluó 2026, no se escogieron pesos con ese año y no se inició F8. El congelamiento de release y la evaluación final siguen siendo una fase posterior.
