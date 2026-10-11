# Fase 3: Location y Pitching sin ambiente

Fecha de implementación: 7 de octubre de 2026. Entorno: `.venv`, CPU, LightGBM 4.6.0.

**Implementación verificada; decisión científica: `promote`.** Pitching sin ambiente supera
a Location y B1 en los protocolos temporal y por pitcher. Pasaron 60 pruebas automatizadas
y 69 controles completos. La verificación independiente reprodujo las predicciones sin
diferencias. F4 queda habilitada; 2026 sigue sellado. Las cifras e intervalos completos
están en la sección «Resultado verificado».

## Qué se implementó y por qué

F3 compara B1, Stuff, Location y Pitching sobre una intersección explícita de lanzamientos
válidos para las tres familias. Las uniones se hacen uno a uno por `pitch_uid`; los índices
de un DataFrame nunca sustituyen la identidad del lanzamiento.

| Componente | Implementación | Motivo |
|---|---|---|
| Location | Clasificador multiclase con las siete variables de ubicación/contexto permitidas. | Medir la predicción condicionada a dónde llegó el lanzamiento y al contexto observable. No mide comando causal ni distancia al objetivo del catcher. |
| Pitching | Clasificador entrenado con las 16 variables físicas y contextuales, sin `altitude_category`. | Medir el aporte físico sobre Location. No es un promedio de las probabilidades de Stuff y Location. |
| Stuff | Conserva exactamente sus once variables; el modelo aprobado de F2 se reutiliza en A completo. | Mantener una referencia física estable y no incorporar conteo, ubicación o bateador a escondidas. |
| Backend compartido | `TabularEventModel` centraliza ajuste, transformación, validación y guardado. `StuffModel` conserva compatibilidad con F2. | Evitar implementaciones divergentes y poder cargar los modelos ya aprobados. |
| Protocolo A | Ajuste 2024; desarrollo, calibración y revisión 2025 con las asignaciones originales. B1 y Stuff congelados desde F2 en la corrida completa. | Comparación temporal directamente trazable a las fases previas. |
| Protocolo B | Modelos nuevos, incluido B1, ajustados solo con pitchers train y años 2024–2025. Desarrollo y calibración en pitchers validation; revisión en pitchers test. | Evaluar jugadores que el modelo no vio en ajuste, sin contaminar el experimento con modelos de A. |
| Selección | Tres configuraciones predeclaradas por familia/protocolo, hasta 400 rondas, paciencia 30; solo desarrollo selecciona. | Mantener el presupuesto de búsqueda y reservar revisión para las comparaciones declaradas. |
| Guardado | Modelos nativos, vocabularios JSON, hashes de datos/código/configuración, IDs de cohortes y predicciones por modelo/protocolo. | Reproducir resultados sin pickle y detectar archivos modificados. |
| Decisión | Location frente a B1; Pitching requiere superar tanto Location como B1. | Promover el componente cuyo aporte tenga evidencia y conservar la referencia cuando no la tenga. |

Las listas concretas están en `modeling/datasets.py`:

```text
Stuff (11): auto_pitch_type, pitcher_throws, rel_speed, spin_rate,
spin_axis_sin, spin_axis_cos, rel_height, rel_side, extension,
induced_vert_break, horz_break

Location (7): auto_pitch_type, pitcher_throws, plate_loc_height,
plate_loc_side, balls, strikes, batter_side

Pitching (16): unión de las dos listas, sin duplicados y sin altitud
```

Los vocabularios se aprenden solo durante ajuste. Las categorías desconocidas siguen la
política de F2: rama de categoría faltante del backend, con advertencia por fila. Los valores
nulos, no numéricos/no finitos y conteos fuera de rango o no enteros rechazan el lote.
F3 no implementa todavía la respuesta individual para entradas inválidas de la interfaz F8.

## Separación de protocolos y poblaciones

La versión de datos sigue siendo `c1c8ba48818dc878`; target `y_event`, semilla `20260929`.
Las seis clases mantienen su orden: ball, called_strike, whiff, foul, in_play, hit_by_pitch.

En B se utiliza el `pitcher_split` preparado, después de restringir los datos a 2024 y 2025.
El hash SHA256 de `diablos-modeling-pitcher-validation-v1|game_anon_id`, con los primeros
16 caracteres hexadecimales módulo 10000, asigna los partidos de pitchers validation:
0–4999 a desarrollo; 5000–9999 a calibración. Un pitcher validation puede participar en
ambos conjuntos, pero un partido de validation no cruza esas dos particiones.
Los años reales se conservan; no se renombran temporadas para reutilizar un entrenador.

B no es una evaluación temporal ni un holdout por partido: un mismo partido puede contener
pitchers de grupos distintos, incluso train y test. Esa superposición se registra en
`B/cohort_manifest.json`. No se incorpora historia de arsenal. La validez de los IDs entre
temporadas sigue pendiente de confirmación de los organizadores.

Cada `coverage.json` separa cobertura propia elegible por familia de la cohorte común usada
para comparar, con recuentos por partición e IDs resumidos mediante hash. No se presentan
las métricas comunes como rendimiento sobre toda la cobertura propia. Se preservan las
banderas de calidad preparadas; la elegibilidad de Pitching aún exige disponibilidad ambiental
por el contrato de datos previo, aunque altitud no sea un predictor. No se modifica esa
población para mejorar resultados.

## Cómo se decide

Métrica primaria: log loss multiclase. Secundaria: Brier como suma de errores cuadrados
sobre las seis clases, promediada por pitch. Se guardan curvas de calibración descriptivas
en diez intervalos de amplitud fija, sin ajustar calibradores.

Cada comparación utiliza los mismos IDs y targets, con bootstrap pareado por partido:
500 remuestreos en completo, 20 en smoke, intervalo percentil del 95%. Se requiere una
reducción relativa de log loss de al menos 1% y límite superior del intervalo de
`loss_candidato - loss_referencia` menor que cero. Se reportan por separado
Stuff/B1, Location/B1, Pitching/Location y Pitching/B1 para A y B.

Las decisiones de A y B son independientes. A es el protocolo principal; no se promedian
métricas entre protocolos ni se escoge uno después de ver resultados. En A la revisión se
ha usado en fases anteriores y no es una prueba final independiente. El bootstrap describe
la incertidumbre de las pérdidas sobre partidos, no causalidad ni incertidumbre individual.

## Archivos y artefactos

| Ruta | Contenido |
|---|---|
| `modeling/phase3.py` | Verificación de F2, selección, entrenamiento, evaluación y decisiones F3. |
| `modeling/protocols.py` | Particiones B y validación explícita de conjuntos autorizados para ajuste. |
| `modeling/models.py` | Backend de familias con listas de variables y compatibilidad Stuff. |
| `modeling/baselines.py` | B1 con ajuste explícito en A o B; A sigue siendo el valor predeterminado. |
| `tests/modeling/test_families.py` | Pruebas de familias, ausencia de fugas, particiones, guardado y promoción. |
| `scripts/check_phase3.py` | Recarga independiente de los cuatro modelos, métricas y bootstrap de ambos protocolos. |
| `artifacts/modeling/f3-smoke-check/F3/` | Ejecución rápida; no sustenta decisiones científicas. |
| `artifacts/modeling/f3-full-check/F3/` | Ejecución completa, separada en carpetas `A/` y `B/`. |

Cada protocolo guarda `cohort.parquet`, `cohort_manifest.json`, `coverage.json`,
`selection.json`, `predictions.parquet`, `comparison_table.csv`, `metrics.json`,
`calibration.csv`, `reproducibility.json`, `B1.json` y modelos `stuff/`, `location/`,
`pitching/`. Los candidatos se conservan en `candidates/`. En la raíz F3 quedan
`manifest.json`, `config.json`, `checks.json`, `metrics.json`, `decision.md` y el resumen
de cohortes. Los datos y modelos permanecen locales y excluidos de Git.

## Cómo probarlo

Desde la raíz del proyecto, usando siempre el entorno virtual:

```powershell
# Pruebas sintéticas: no necesitan abrir la base completa.
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Comprobar el contrato y verificar la ejecución completa ya guardada.
.\.venv\Scripts\python.exe scripts/check_modeling_contract.py
.\.venv\Scripts\python.exe scripts/check_phase3.py --experiment-id f3-full-check

# Nuevas ejecuciones con IDs automáticos; preservan los experimentos existentes.
.\run_modeling.ps1 f3-smoke
.\run_modeling.ps1 f3

# Equivalentes sin depender del permiso para ejecutar scripts de PowerShell.
.\.venv\Scripts\python.exe -m modeling.cli train --phase F3 --smoke
.\.venv\Scripts\python.exe -m modeling.cli train --phase F3
```

Si falta el entorno en otra computadora, crearlo con `python -m venv .venv` e instalar
`requirements-modeling.txt` usando su propio Python. El entrenamiento completo requiere la
versión local autorizada de datos y las dependencias aprobadas F0, F1 y F2. No se descargan
datos del reto desde GitHub. Un ID de experimento existente produce un error explícito;
para repetir entrenamiento usar otro ID o dejar que el programa genere uno.

El verificador debe devolver `status: verified`, diferencias de predicción como máximo
`1e-8` y métricas reproducidas en ambos protocolos. Las pruebas comprueban, entre otros,
que ubicación/conteo no afectan Stuff, física excluida no afecta Location, altitud no afecta
Pitching, categorías de desarrollo no entran al vocabulario, no se ajusta en revisión y
las uniones no duplican ni desplazan etiquetas.

## Límites y siguiente fase

F3 entrega probabilidades de eventos y evidencia de comparación; no calcula scores,
xRunValue, calibradores, cabezas de contacto, arsenal ni simulación ambiental. No se han
abierto etiquetas de 2026; solo existe el perfilado de calidad previo, declarado desde F0.
F4 es la siguiente fase y requiere un cierre técnico satisfactorio de F3; no se inicia
automáticamente.

## Resultado verificado

**F3 está implementada y verificada.** Pasaron 60 pruebas automatizadas, 67 controles rápidos y 69 controles completos. Las verificaciones independientes reprodujeron todos los modelos, las 24 combinaciones modelo/partición y ocho comparaciones bootstrap por ejecución. Diferencia máxima al recargar: **0.0**. Los reajustes de las configuraciones elegidas también dieron **0.0**.

Los cambios al backend se comprobaron además contra F2: sus 251,969 predicciones, nueve métricas agrupadas y dos comparaciones bootstrap se reprodujeron sin cambios. No quedan fallos técnicos observados de F3. **F4 queda habilitada, sin iniciarse.**

Tiempo local de la corrida completa: 14.45 minutos, cuatro hilos CPU. Incluye búsqueda, predicción, refit de comprobación y guardado; no es una garantía de latencia.

Evidencia estructurada: `docs/F3_VALIDATION.json`, `docs/F3_SMOKE_VALIDATION.json` y `docs/F3_FULL_VALIDATION.json`. La configuración de cada experimento conserva el estado `in_progress` previo al entrenamiento; su manifiesto final certifica `verified`. El contrato actual se actualiza después del cierre. Los hashes del código ejecutado coinciden con la entrega.

### Protocolo A

| Partición | Pitches | Partidos | Pitchers |
|---|---:|---:|---:|
| train | 239,709 | 833 | 538 |
| development | 134,420 | 447 | 540 |
| calibration | 59,367 | 197 | 479 |
| phase_review | 58,182 | 192 | 492 |

| Modelo, misma revisión | Log loss | Brier |
|---|---:|---:|
| B1 | 1.463495407 | 0.736557705 |
| Stuff | 1.515176368 | 0.754008705 |
| Location | 1.049467005 | 0.542457183 |
| Pitching | 1.032505818 | 0.534757237 |

| Comparación | Reducción relativa de log loss | IC 95% de diferencia de pérdida | Regla de promoción |
|---|---:|---|---|
| Stuff_vs_B1 | -3.531% | [0.048604, 0.054510] | inconclusive |
| Location_vs_B1 | 28.290% | [-0.420851, -0.406790] | promote |
| Pitching_vs_Location | 1.616% | [-0.018848, -0.015004] | promote |
| Pitching_vs_B1 | 29.449% | [-0.437590, -0.423836] | promote |

Decisión: **`promote`**; referencia predictiva: **Pitching**. Stuff: `retain_reference`; Location: `promote`; Pitching: `promote`.

Selección hecha exclusivamente en desarrollo:

| Familia | Candidato | Rondas elegidas |
|---|---|---:|
| stuff | modelo congelado de F2 | 108 |
| location | candidate_01 | 400 |
| pitching | candidate_02 | 323 |

### Protocolo B

| Partición | Pitches | Partidos | Pitchers |
|---|---:|---:|---:|
| train | 360,035 | 1,667 | 607 |
| development | 33,081 | 643 | 110 |
| calibration | 34,049 | 652 | 111 |
| phase_review | 64,513 | 1,313 | 104 |

| Modelo, misma revisión | Log loss | Brier |
|---|---:|---:|
| B1 | 1.470613279 | 0.740018142 |
| Stuff | 1.524153922 | 0.758350160 |
| Location | 1.047425370 | 0.543338633 |
| Pitching | 1.031972315 | 0.536318937 |

| Comparación | Reducción relativa de log loss | IC 95% de diferencia de pérdida | Regla de promoción |
|---|---:|---|---|
| Stuff_vs_B1 | -3.641% | [0.050590, 0.056296] | inconclusive |
| Location_vs_B1 | 28.776% | [-0.429022, -0.417315] | promote |
| Pitching_vs_Location | 1.475% | [-0.017131, -0.013918] | promote |
| Pitching_vs_B1 | 29.827% | [-0.444613, -0.432667] | promote |

Decisión: **`promote`**; referencia predictiva: **Pitching**. Stuff: `retain_reference`; Location: `promote`; Pitching: `promote`.

Hay 1,313 partidos presentes tanto en ajuste como en revisión por contener pitchers de grupos distintos. Los pitchers de revisión están separados de los usados para ajuste y selección. Esta cifra no convierte B en un holdout por partido.

Selección hecha exclusivamente en desarrollo:

| Familia | Candidato | Rondas elegidas |
|---|---|---:|
| stuff | candidate_01 | 137 |
| location | candidate_02 | 304 |
| pitching | candidate_03 | 288 |

### Cobertura propia y población común

Denominador: 499,398 lanzamientos de 2024–2025 antes de filtros por familia.

| Familia | Elegibles propios | Cobertura del denominador | Cohorte comparada |
|---|---:|---:|---:|
| stuff | 497,006 | 99.521% | 491,678 |
| location | 492,501 | 98.619% | 491,678 |
| pitching | 491,678 | 98.454% | 491,678 |

Los límites de rondas se mantuvieron aunque un candidato los alcanzara. No se amplió la búsqueda después de conocer revisión. Una reducción negativa indica empeoramiento; `inconclusive` en la comparación significa que no se cumple la regla de promoción y la decisión de familia conserva la referencia.
