# Fase 1: baselines de eventos, decisiones y pruebas

Fecha de entrega: 3 de octubre de 2026, zona America/Mexico_City.

## Resultado y decisión de continuidad

**F1 está implementada y verificada dentro de `.venv`.** Se entrenaron B0, B1 y B2
exclusivamente con 2024 y se evaluaron sobre las tres subparticiones de 2025 fijadas en F0.
No se consultaron etiquetas de 2026, no se ajustaron calibradores y no se avanzó a F2.

Pasaron **34 pruebas unitarias**: las 17 anteriores y 17 nuevas. La prueba rápida pasó
45 controles y cada ejecución completa pasó **46 controles**. Dos ejecuciones completas
produjeron los mismos 15 archivos de artefactos, incluidos modelos, probabilidades,
métricas, intervalos bootstrap, curvas y listas de pitches.

La decisión de fase es **`retain_reference`**: se conserva **B1** como referencia conceptual
del contrato. En la revisión de 2025, B1 mejoró 4.42% frente a B0. B2 mejoró 0.60% frente a
B1; aunque el intervalo de la diferencia quedó bajo cero, no alcanzó el mínimo operativo
de 1%. Esa comparación se etiqueta `inconclusive` para promoción. B2 queda disponible como
comparador adicional, sin sustituir silenciosamente a B1.

**F2 queda habilitada, pero sigue `not_started`.** No hay fallos técnicos pendientes observados
en F1. Estas probabilidades son estimaciones de eventos, no scores Stuff+/Location+/Pitching+
ni un baseline de xRunValue.

## Qué se implementó y por qué

| Componente | Implementación | Motivo |
|---|---|---|
| B0 global | Frecuencia de cada evento con pseudocuenta 1 por clase. | Evitar probabilidades cero, incluso si una clase falta en una muestra de entrenamiento. |
| B1 por conteo | Grupos definidos por `balls` y `strikes`, suavizados hacia B0 con concentración 20. | Representar la referencia contextual definida por el contrato sin añadir conteo a las variables físicas de Stuff. |
| B2 por conteo y tipo | Grupos por `balls`, `strikes` y `auto_pitch_type`, con el mismo suavizado. | Medir el aporte adicional del tipo de lanzamiento sobre una población idéntica. |
| Grupos desconocidos | B1 y B2 vuelven directamente a B0; cada fila registra `group`, `global` o `fallback_global`. | Dar una respuesta explícita y reproducible sin aprender de los resultados evaluados. |
| Guardado de modelos | JSON con conteos globales y por grupo, clases, variables, parámetros y hash de IDs de entrenamiento. | Permitir inspección y recarga sin pickle ni dependencias adicionales. |
| Evaluación | Log loss, Brier multiclase sumado sobre las seis clases y curvas de 10 bins de amplitud fija. | Cumplir las definiciones del contrato, sin sustituirlas por accuracy ni dividir Brier por seis. |
| Comparaciones | Bootstrap pareado por partido: 20 remuestreos en smoke, 500 en ejecución completa. | Mantener juntos los pitches de un partido y comparar las mismas observaciones y etiquetas. |
| Dependencia F0 | Verificación de manifiesto, checks, hashes de artefactos, versión de datos y parámetros de partición del experimento aprobado. | No asumir que la fase anterior está correcta solo porque la configuración dice `verified`. |
| Cohorte | Misma intersección de Stuff, Location y Pitching de F0; join uno a uno por `pitch_uid` para el conteo. | Comparaciones sobre el mismo denominador, preservando las exclusiones ya aprobadas. |
| Registro | Manifiesto con datos, código, configuración, intérprete, dependencias, tiempos, población y estado. | Reproducibilidad y separación entre fallo técnico y resultado científico. |

No se añadieron bibliotecas a `requirements.txt`: bastan pandas, NumPy, PyArrow y DuckDB,
con las versiones ya fijadas. Los gráficos son SVG autónomos y los modelos son tablas de
frecuencias; la selección de un backend de gradient boosting corresponde a F2.

### Fórmulas y restricciones

Para clase `k`, B0 calcula:

```text
p_global(k) = (n_k + 1) / (N + 6)
```

Para un grupo conocido `g`, B1 y B2 calculan:

```text
p(k | g) = (n_gk + 20 × p_global(k)) / (n_g + 20)
```

Todos los conteos proceden exclusivamente de `year=2024` y `partition=train`.
`fit()` rechaza filas de desarrollo, calibración, revisión o test, además de targets
desconocidos/nulos e IDs duplicados. `predict()` no requiere outcomes y no modifica conteos.
No se seleccionaron concentraciones ni pseudocuentas con los resultados de 2025.

El fallback de B2 va directamente a B0, no a B1. Esta decisión está explícita en
`config/modeling_contract.json`, en el modelo guardado y en las rutas por pitch. Contexto
faltante también produce fallback; conteos numéricos fuera de rango se rechazan. Las cohortes
de esta evaluación son completas, por lo que sus fallbacks corresponden a grupos no vistos.

## Datos y denominadores

- Versión de datos: `c1c8ba48818dc878`.
- Target y orden de clases: `y_event`; ball, called_strike, whiff, foul, in_play, hit_by_pitch.
- Protocolo: A; semilla `20260929`; particiones de partido heredadas de F0.
- Política de población: `f0_common_v1`, sin ampliar ni cambiar los filtros.
- Referencia de infraestructura: `artifacts/modeling/f0-full-reproduction/F0/`.

| Partición | Año | Pitches | Partidos | Uso en F1 |
|---|---:|---:|---:|---|
| train | 2024 | 239,709 | 833 | Estimar las tres tablas de frecuencias. |
| development | 2025 | 134,420 | 447 | Diagnóstico, sin ajuste de parámetros. |
| calibration | 2025 | 59,367 | 197 | Diagnóstico, sin ajustar calibradores. |
| phase_review | 2025 | 58,182 | 192 | Comparación de los baselines predefinidos. |
| Total común | 2024–2025 | 491,678 | 1,669 | Misma cohorte que F0. |

Los tres modelos predicen los mismos **251,969 pitches de 2025**. `predictions.parquet`
contiene **755,907 filas**, una por combinación `(pitch_uid, model)`. La duplicación de un
pitch entre modelos es intencional; la clave compuesta es única. Las predicciones de
entrenamiento no se incluyen ni se mezclan con las métricas de evaluación.

B1 aprendió 12 grupos y B2 aprendió 91. B1 no necesitó fallback en 2025. B2 lo utilizó
337 veces: 187 en desarrollo, 41 en calibración y 109 en revisión. Estos pitches permanecen
en las métricas y el denominador común; no se retiran para mejorar resultados.

El hash de IDs de cohorte completa sigue siendo:

```text
655d826b2a1ede2e153bd4461d74b208dcb18041f698f50b6a000dfed8270d92
```

La prueba rápida usó 19,681 pitches comunes: 10,360 de entrenamiento y 9,321 de evaluación.
Sus métricas solo prueban el flujo y no justifican decisiones científicas.

## Métricas obtenidas

Menor valor es mejor en ambas métricas. Brier es la suma sobre las seis clases, promediada
por pitch. No se divide nuevamente por el número de clases.

| Partición | Modelo | Log loss | Brier |
|---|---|---:|---:|
| Desarrollo | B0 | 1.533553 | 0.759431 |
| Desarrollo | B1 | 1.467188 | 0.737938 |
| Desarrollo | B2 | 1.459127 | 0.735783 |
| Calibración | B0 | 1.529024 | 0.757031 |
| Calibración | B1 | 1.462729 | 0.735876 |
| Calibración | B2 | 1.454042 | 0.733494 |
| Revisión | B0 | 1.531096 | 0.758257 |
| Revisión | B1 | 1.463495 | 0.736558 |
| Revisión | B2 | 1.454644 | 0.733993 |

Comparaciones predefinidas sobre los 58,182 pitches y 192 partidos de revisión:

| Candidato / referencia | Reducción relativa | Delta log loss | IC bootstrap 95% del delta | Resultado de la regla |
|---|---:|---:|---|---|
| B1 / B0 | 4.4152% | −0.067601 | [−0.070456, −0.064679] | `promote` frente a B0 |
| B2 / B0 | 4.9933% | −0.076452 | [−0.079470, −0.073396] | `promote` frente a B0 |
| B2 / B1 | 0.6048% | −0.008851 | [−0.010059, −0.007625] | `inconclusive` para promoción |

El bootstrap remuestrea partidos completos con reemplazo. En cada réplica divide la suma
de diferencias de pérdida por el número de pitches remuestreados; no promedia partidos
con igual peso cuando tienen tamaños diferentes. El intervalo es percentil y pareado.

Los resultados `promote` de comparaciones indican que pasan la regla estadística configurada;
no sustituyen la decisión de fase de conservar B1 como referencia. El umbral de 1% es una
regla operativa del equipo, no un requisito oficial. La revisión de 2025 se reutilizará en
otras fases y **no es una estimación final independiente**.

## Archivos y artefactos

| Archivo de código | Responsabilidad |
|---|---|
| `modeling/baselines.py` | B0/B1/B2, suavizado, validación, fallback, guardado y recarga. |
| `modeling/metrics.py` | Métricas multiclase, bins de calibración, bootstrap pareado y gráficos SVG. |
| `modeling/phase1.py` | Verificar F0, construir la cohorte, entrenar, evaluar y registrar F1. |
| `modeling/cli.py` | Comando `train --phase F1`, conservando `smoke` de F0. |
| `tests/modeling/test_baselines.py` | 17 nuevas pruebas de baselines y métricas. |
| `tests/test_modeling.py` | Incluye las pruebas nuevas en el descubrimiento existente. |
| `run_modeling.ps1` | Nuevas acciones `f1-smoke` y `f1`, siempre con `.venv`. |
| `config/modeling_contract.json` | Dependencia F0 explícita, política de cohorte/fallback/referencia y estado F1. |

Experimentos preservados:

- `artifacts/modeling/f1-smoke-check/F1/`: prueba rápida.
- `artifacts/modeling/f1-full-check/F1/`: evaluación completa.
- `artifacts/modeling/f1-full-reproduction/F1/`: reproducción completa.

Cada carpeta contiene `manifest.json`, `config.json`, `cohort_manifest.json`, `cohort.parquet`,
`assignments.parquet`, `predictions.parquet`, `metrics.json`, `checks.json`, `decision.md`,
`models/B0.json`, `models/B1.json`, `models/B2.json`, `calibration.csv` y tres curvas SVG:
`calibration_development.svg`, `calibration_calibration.svg`, `calibration_phase_review.svg`.

Los 15 archivos distintos del manifiesto coincidieron byte por byte entre las dos
ejecuciones completas. Los manifiestos difieren normalmente en ID, hora y duración.
La evidencia compacta se guarda en `docs/F1_VALIDATION.json`.

`calibration.csv` contiene 540 filas: 3 modelos × 3 particiones × 6 clases × 10 bins.
Incluye límites, número de observaciones, positivos, probabilidad media y frecuencia
observada. El extremo 1 se incluye en el último bin; los bins vacíos conservan recuento
cero y medias nulas. Los SVG muestran las curvas por clase; al pasar sobre un punto se
ven los recuentos. Los bins escasos no demuestran por sí solos mala calibración.

Las configuraciones históricas guardadas conservan F1 en `in_progress`, que era su estado
al iniciar las ejecuciones. Solo después de aprobar pruebas y reproducción se cambió la
configuración principal a `verified` y se actualizó el texto de estado del contrato.

## Cómo probarlo

Desde la raíz del proyecto, sin necesidad de activar el entorno:

```powershell
.\run_modeling.ps1 contract
.\run_modeling.ps1 tests
.\run_modeling.ps1 f1-smoke
.\run_modeling.ps1 f1
```

Esperado: contrato coherente; 34 pruebas con `OK`; salida `verified`. La ejecución rápida
declara `inconclusive`, mientras que la completa declara `retain_reference`. Cada llamada
genera una carpeta nueva e imprime su ruta; no modifica datos preparados ni resultados anteriores.

Si PowerShell bloquea scripts, ejecutar directamente el Python de `.venv`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m modeling.cli train --phase F1 --smoke
.\.venv\Scripts\python.exe -m modeling.cli train --phase F1
```

Para comprobar reproducción con IDs nuevos:

```powershell
.\.venv\Scripts\python.exe -m modeling.cli train --phase F1 --experiment-id mi-f1-a
.\.venv\Scripts\python.exe -m modeling.cli train --phase F1 --experiment-id mi-f1-b
$a = Get-Content artifacts/modeling/mi-f1-a/F1/manifest.json -Raw | ConvertFrom-Json
$b = Get-Content artifacts/modeling/mi-f1-b/F1/manifest.json -Raw | ConvertFrom-Json
$a.cohort.common_ids_sha256 -eq $b.cohort.common_ids_sha256
$a.artifact_hashes.'predictions.parquet' -eq $b.artifact_hashes.'predictions.parquet'
$a.artifact_hashes.'metrics.json' -eq $b.artifact_hashes.'metrics.json'
$a.artifact_hashes.'models/B2.json' -eq $b.artifact_hashes.'models/B2.json'
```

Las comparaciones deben devolver `True`. Un ID existente debe fallar sin sobrescribir.
La copia autorizada del proyecto necesita conservar también los artefactos de F0 referenciados,
además de los datos preparados; no basta copiar solo los modelos de F1 para reentrenar.

Para recargar un modelo y predecir sin outcomes, usar Python de `.venv`:

```python
import pandas as pd
from modeling.baselines import EventBaseline

model = EventBaseline.load("artifacts/modeling/f1-full-check/F1/models/B2.json")
inputs = pd.DataFrame({
    "balls": [0, 0], "strikes": [0, 0],
    "auto_pitch_type": ["Four-Seam", "tipo_nuevo"],
})
probabilities, routes = model.predict(inputs)
print(model.classes)
print(probabilities)
print(routes)  # La segunda fila debe indicar fallback_global.
```

La interfaz final del dashboard sigue reservada a fases posteriores. Esta es la API del
baseline; no devuelve scores ni evalúa escenarios físicos.

## Alcance de las verificaciones y límites

Las pruebas nuevas comprueban las fórmulas con conteos conocidos, clases ausentes,
fallbacks, orden de filas, independencia de outcomes al predecir, rechazo de datos fuera
de 2024/train, validación de entradas, recarga exacta y detección de conteos corruptos.
También contrastan log loss y Brier contra resultados analíticos, fronteras de bins,
bootstrap agrupado con tamaños desiguales, emparejamiento de IDs/targets, criterios de
promoción, falta de partidos y estructura de los SVG.

La fase usa la cohorte completa común, por lo que sus métricas no representan todos los
pitches brutos. Conserva las etiquetas provisionales y filtros de calidad existentes,
incluida la exigencia de ambiente disponible en el filtro de Pitching, aunque no se use
altitud como predictor. El perfilado previo de 2026 permanece declarado; F1 no lo reabrió.

No se hizo optimización de hiperparámetros, calibración posterior, modelado físico,
arsenal, ambiente, xRunValue, normalización de scores ni selección con test. El siguiente
paso, cuando se solicite, es **F2: modelo físico Stuff y comparación contra B0/B1**.
