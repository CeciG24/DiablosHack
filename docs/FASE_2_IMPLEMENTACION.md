# Fase 2: modelo físico Stuff, decisiones y pruebas

Fecha de entrega: 5 de octubre de 2026, zona America/Mexico_City.

## Resultado y decisión

**F2 está implementada y verificada.** Pasaron 47 pruebas unitarias, 49 controles de la
prueba rápida y **52 controles de la ejecución completa**. Un verificador en otro proceso
recargó el modelo, reprodujo las probabilidades de los 251,969 pitches de evaluación,
las nueve combinaciones modelo/partición de métricas y las dos comparaciones bootstrap.
No se consultaron etiquetas de 2026.

La decisión científica es **`retain_reference`**. Stuff mejoró la log loss de B0 un 1.04%,
pero tuvo una pérdida 3.53% mayor que B1 en revisión. Se conserva B1 como referencia y
Stuff como candidato diagnóstico. **F3 queda habilitada, sin implementarse ni ejecutarse.**
No quedan fallos técnicos observados de F2; no se presenta este modelo como superior a B1.

## Alcance y decisiones de implementación

F2 incorpora un clasificador multiclase de `y_event` construido únicamente con las
11 variables permitidas para Stuff. Se ejecuta dentro de `.venv` y utiliza LightGBM 4.6.0
en CPU, fijado junto con SciPy 1.16.3 en `requirements-modeling.txt`. No modifica los datos
preparados ni abre las etiquetas de 2026. F3 no se inicia automáticamente.

| Decisión | Implementación | Motivo |
|---|---|---|
| Un backend inicial | LightGBM 4.6.0, objetivo multiclase con seis probabilidades conjuntas. | Se ajusta a datos tabulares, permite categorías explícitas, parada temprana y guardado nativo sin pickle. Se fija una versión concreta para reproducibilidad. |
| Separación física | Lista cerrada `STUFF`; se ignoran las columnas adicionales al predecir. | Evitar que conteo, ubicación, bateador, ambiente, IDs u outcomes se conviertan en predictores físicos. |
| Cohorte | `f0_common_v1`, exactamente la utilizada en F1. | Comparar el modelo nuevo con B0/B1 sobre los mismos pitches y los mismos datos de entrenamiento. |
| Preprocesamiento | Vocabularios de tipo de pitch y mano aprendidos exclusivamente en 2024/train. Los numéricos se conservan en sus unidades. | No aprender categorías de desarrollo ni estadísticas de imputación de otros periodos. Los árboles no necesitan escalado. |
| Selección | Tres configuraciones predeclaradas; gana la menor log loss de desarrollo. | Respetar el presupuesto máximo de 12 configuraciones sin buscar ajustes con revisión. |
| Parada temprana | Hasta 400 rondas; paciencia de 30 rondas sobre desarrollo de 2025. | Limitar el sobreajuste sin usar calibración, revisión o test para decidir la longitud del modelo. |
| Baselines | Reutilizar los modelos JSON aprobados de F1 en la ejecución completa. | Mantener una referencia estable; comprobar los hashes de IDs de entrenamiento y las probabilidades anteriores. |
| Interpretación | Permutar cada variable en desarrollo y repetir tres veces. | Medir cuánto aumenta la log loss cuando se rompe su asociación con el target, sin usar revisión para explicar o seleccionar variables. |
| Reproducibilidad | Semilla fija, cuatro hilos CPU, modo determinista, orden estable por ID y guardado del modelo nativo más metadatos. | Comprobar tanto recarga como un segundo ajuste de la configuración ya seleccionada. |

LightGBM documenta la parada temprana y la conservación de `best_iteration` en su
[API oficial de la versión 4.6.0](https://lightgbm.readthedocs.io/en/v4.6.0/pythonapi/lightgbm.early_stopping.html).
La elección de modo determinista con `force_col_wise` y el uso de valores categóricos
negativos como faltantes siguen los
[parámetros oficiales](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html).
No se pretende reproducibilidad universal entre distintos sistemas, compiladores o versiones.

### Variables físicas y comportamiento ante entradas nuevas

Las once columnas son:

```text
auto_pitch_type, pitcher_throws, rel_speed, spin_rate,
spin_axis_sin, spin_axis_cos, rel_height, rel_side,
extension, induced_vert_break, horz_break
```

Una categoría nueva se codifica como −1 y usa la rama de categoría faltante del backend.
Se registra `unknown_category:<columna>` como advertencia. Esta política no utiliza las
etiquetas del pitch nuevo ni amplía el vocabulario aprendido. Una categoría desconocida
no garantiza buen soporte estadístico, aunque se pueda producir una probabilidad válida.

La ausencia de una columna requerida, un valor físico nulo/no finito o un tipo inválido
produce `ValueError` y rechaza el lote. F2 no imputa ni inventa un score. La política de
respuesta por fila de la interfaz final sigue reservada a las fases de producto posteriores.

### Búsqueda fijada antes de la evaluación

| Candidato | Hojas | Mínimo de filas por hoja | Learning rate | Regularización L2 |
|---|---:|---:|---:|---:|
| candidate_01 | 15 | 200 | 0.05 | 5 |
| candidate_02 | 31 | 200 | 0.05 | 5 |
| candidate_03 | 63 | 400 | 0.05 | 10 |

Los candidatos se ajustan con 2024 y se seleccionan exclusivamente con desarrollo 2025.
`selection.json` queda escrito antes de calcular predicciones y comparaciones de revisión.
No se continúa buscando configuraciones tras conocer el resultado de revisión.
Se comprueba que los cinco folds existentes de entrenamiento preserven los partidos;
no se crea una división aleatoria por pitch ni se realiza una búsqueda adicional por folds.

En smoke se usa una sola configuración, hasta 60 rondas, una permutación por variable y
20 remuestreos bootstrap. En completo se usan las tres configuraciones, hasta 400 rondas,
tres permutaciones y 500 remuestreos. El segundo ajuste del candidato elegido comprueba
reproducibilidad; no constituye otra configuración ni cambia la selección.

## Población

Datos: `c1c8ba48818dc878`; protocolo A; target `y_event`; semilla `20260929`.
Orden de clases: ball, called_strike, whiff, foul, in_play, hit_by_pitch.

| Partición | Pitches | Partidos | Uso |
|---|---:|---:|---|
| 2024/train | 239,709 | 833 | Ajuste de árboles y vocabularios. |
| 2025/development | 134,420 | 447 | Selección, parada temprana e importancia por permutación. |
| 2025/calibration | 59,367 | 197 | Diagnóstico de probabilidades, sin ajustar calibradores. |
| 2025/phase_review | 58,182 | 192 | Comparación predefinida contra B0/B1. |

La cohorte común contiene 491,678 pitches. Las probabilidades evaluadas cubren
251,969 pitches de 2025 para cada modelo. El archivo largo contiene una fila por
`(pitch_uid, model)`, con modelos B0, B1 y Stuff. Se conserva la cobertura y el resumen
de exclusiones por familia de F0; no se amplía silenciosamente a toda la población física.

Hash de IDs de la cohorte completa:

```text
655d826b2a1ede2e153bd4461d74b208dcb18041f698f50b6a000dfed8270d92
```

La comparación de revisión usa bootstrap pareado por partido y la regla de promoción
de reducción relativa de log loss ≥1%, con límite superior del IC 95% de
`loss_Stuff − loss_referencia` menor que cero. El Brier se suma sobre las seis clases
y después se promedia por pitch. No se divide adicionalmente entre seis.

## Resultados medidos

La selección eligió `candidate_01`: 15 hojas, mínimo 200 filas por hoja, learning rate
0.05 y regularización L2 de 5. La mejor iteración fue la 108; se evaluaron 138 antes de
activar la parada temprana. Los otros candidatos obtuvieron su mejor iteración en 78 y 54.

| Candidato | Log loss de desarrollo | Mejor iteración |
|---|---:|---:|
| candidate_01 | 1.517715648 | 108 |
| candidate_02 | 1.517729793 | 78 |
| candidate_03 | 1.518190232 | 54 |

La diferencia entre las dos primeras configuraciones es pequeña. Se aplicó la regla
predefinida de menor pérdida sin anunciar superioridad estadística entre hiperparámetros.

| Partición | Modelo | Log loss | Brier |
|---|---|---:|---:|
| Desarrollo | B0 | 1.533553 | 0.759431 |
| Desarrollo | B1 | 1.467188 | 0.737938 |
| Desarrollo | Stuff | 1.517716 | 0.755177 |
| Calibración | B0 | 1.529024 | 0.757031 |
| Calibración | B1 | 1.462729 | 0.735876 |
| Calibración | Stuff | 1.512593 | 0.752599 |
| Revisión | B0 | 1.531096 | 0.758257 |
| Revisión | B1 | 1.463495 | 0.736558 |
| Revisión | Stuff | 1.515176 | 0.754009 |

Comparación sobre los 58,182 pitches de los 192 partidos de revisión, con 500 remuestreos:

| Comparación | Reducción relativa de log loss | Delta Stuff − referencia | IC 95% delta | Decisión |
|---|---:|---:|---|---|
| Stuff / B0 | 1.0398% | −0.015920 | [−0.017229, −0.014599] | Pasa la regla frente a B0. |
| Stuff / B1 | −3.5313% | +0.051681 | [+0.048604, +0.054510] | Conservar B1. |

El comparador genérico registra `inconclusive` cuando no se cumple la regla de promoción;
en este caso concreto los datos muestran una pérdida mayor que B1 y un intervalo positivo.
El cierre de F2 utiliza `retain_reference`, como exige el contrato, sin esconder ese resultado.

Las cinco variables con mayor incremento medio de log loss al permutarse en desarrollo fueron:

| Variable | Aumento medio de log loss |
|---|---:|
| Tipo de pitch (`auto_pitch_type`) | 0.007692 |
| Movimiento vertical inducido (`induced_vert_break`) | 0.007552 |
| Velocidad del lanzamiento al release (`rel_speed`) | 0.005959 |
| Spin rate (`spin_rate`) | 0.002297 |
| Altura de release (`rel_height`) | 0.001927 |

Las once variables y sus tres repeticiones quedan en `permutation_importance.json`;
el CSV incluye medias y desviaciones estándar. No se usaron estos resultados para cambiar
la lista de variables ni reabrir la búsqueda de configuraciones.

### Evidencia técnica y artefactos

- Prueba rápida: `artifacts/modeling/f2-smoke-check/F2/`, 49 controles aprobados.
- Ejecución completa: `artifacts/modeling/f2-full-check/F2/`, 52 controles aprobados.
- Resumen de validación: `docs/F2_VALIDATION.json`.

El experimento completo conserva 25 artefactos además del manifiesto: modelos de los tres
candidatos, modelo seleccionado, vocabularios e historial de desarrollo, B0/B1 originales,
configuración, cohorte, métricas, predicciones, controles, decisión, importancia de variables,
curvas de calibración y evidencia de reproducción. Los checksums se registran recursivamente.
`predictions.parquet` tiene 755,907 filas, una por pitch/modelo, sin incluir entrenamiento.

La diferencia máxima absoluta fue **0.0** tanto tras guardar/recargar como al volver a
entrenar la configuración seleccionada. Un proceso independiente volvió a obtener **0.0**
en los 251,969 pitches y reprodujo las nueve tablas de métricas y ambos bootstrap.
La tolerancia exigida era 1e-8. La ejecución completa tardó aproximadamente 240 segundos
en este equipo, incluyendo interpretación, evaluación y segundo ajuste; no es una promesa
de latencia de inferencia en otros equipos.

Las 13 pruebas nuevas, junto con las 34 previas, cubren listas exactas, invariancia a
contexto/outcomes/IDs, faltantes y no finitos, categorías nuevas, vocabulario aprendido solo
en entrenamiento, rechazo de particiones no autorizadas, separación de partidos, clases,
persistencia, archivo alterado, ajuste tras barajar, permutación y límite de configuraciones.
Los datos y artefactos de F0/F1 se verificaron antes de entrenar.

Las copias históricas conservan F2 en `in_progress`: la configuración principal se cambió
a `verified` después de las verificaciones. Los hashes del contrato y código en el
manifiesto describen los archivos al ejecutar; la actualización final de estado/documentación
y de los textos de ayuda de CLI no cambia los modelos entrenados.

## Archivos implementados y operación

| Archivo | Responsabilidad |
|---|---|
| `modeling/models.py` | Stuff físico, validación, vocabularios, entrenamiento, guardado nativo, recarga y permutación. |
| `modeling/phase2.py` | Verificar F1, seleccionar con desarrollo, evaluar, comparar y registrar F2. |
| `modeling/metrics.py` | Permite etiquetar las curvas como F2 y mostrar Stuff, conservando el comportamiento de F1. |
| `modeling/cli.py` | Añade `train --phase F2` y su modo `--smoke`. |
| `tests/modeling/test_stuff.py` | Pruebas físicas, de separación temporal, entradas nuevas, persistencia y reproducibilidad. |
| `requirements-modeling.txt` | Backend y dependencia numérica fijados, además de las dependencias base. |
| `config/modeling_contract.json` | Configuraciones, presupuesto, referencia F1 y política de cohorte. |
| `run_modeling.ps1` | Acciones `f2-smoke` y `f2`, usando exclusivamente `.venv`. |
| `scripts/check_phase2.py` | Verificación independiente de integridad, recarga, métricas y bootstrap de una ejecución guardada. |

Desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-modeling.txt
.\run_modeling.ps1 contract
.\run_modeling.ps1 tests
.\run_modeling.ps1 f2-smoke
.\run_modeling.ps1 f2
```

Si PowerShell bloquea scripts, ejecutar el Python directamente:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m modeling.cli train --phase F2 --smoke
.\.venv\Scripts\python.exe -m modeling.cli train --phase F2
```

Se espera `verified` en la ejecución técnica, incluso si el candidato pierde frente a B1.
La salida muestra la ruta, la configuración seleccionada, el número de rondas y la decisión
científica. Cada ejecución crea una carpeta nueva y rechaza IDs de experimento existentes.

Para verificar la entrega sin volver a entrenar:

```powershell
.\.venv\Scripts\python.exe scripts/check_phase2.py --experiment-id f2-full-check
```

Resultado esperado: `verified`, diferencia máxima de predicción 0.0, nueve grupos de
métricas y dos comparaciones bootstrap reproducidas. Este comando solo consulta datos
permitidos de 2024–2025 y artefactos locales. Necesita conservar la versión de datos y los
artefactos de F1 referenciados para las ejecuciones nuevas de entrenamiento.

Para predecir desde un modelo guardado, proporcionar las once columnas físicas:

```python
from modeling.models import StuffModel
from modeling.datasets import ModelingDataset

model = StuffModel.load("artifacts/modeling/f2-full-check/F2/stuff")
cohort = ModelingDataset().load(maximum=20000)
X, _, metadata = ModelingDataset.matrices(cohort, "stuff")
probabilities = model.predict(X)
warnings = model.warnings(X)
print(probabilities.shape, warnings[:3])
```

El ejemplo usa una cohorte pequeña para demostrar inferencia; no es una evaluación nueva.
Para repetir toda la ejecución, utilizar un `--experiment-id` distinto. Comparar las
probabilidades y métricas con tolerancia 1e-8 dentro del mismo entorno, no las fechas ni
los tiempos de los manifiestos.

## Límites

Los resultados corresponden a la cohorte común con sus filtros de calidad, no a todos
los pitches brutos. La revisión de 2025 se reutiliza entre fases y no es un test final
independiente. El perfilado anterior de calidad de 2026 ya estaba declarado; F2 no lo reabre.

La importancia por permutación es diagnóstica, no causal. Variables correlacionadas pueden
compartir información; permutar por separado seno y coseno del spin puede crear combinaciones
que no describen un ángulo real. No se usa esta tabla para recomendar cambios físicos ni
para retirar variables del modelo en esta fase. Su desviación estándar describe las tres
permutaciones, no un intervalo de confianza de población.

No se entrenó Location, Pitching, arsenal ni ambiente; no se ajustaron calibradores ni
normalizadores de scores. Si Stuff no vence B1, se conserva como candidato diagnóstico:
perder contra un baseline contextual no prueba que la física carezca de valor. Esa pregunta
se complementa con las comparaciones de F3, cuando se solicite.
