# Fase 9: implementación, resultados y evaluación frente al hackathon

Fecha: 16 de octubre de 2026. Rama: `fase-9`. Experimento: `f9-full`.

## Resultado principal

Se implementó y ejecutó una estrategia de mejora con once modelos y seis comparaciones predefinidas. El modelo de eventos con contexto y física reduce el log loss frente al baseline por conteo en **1.208%** sobre review temporal 2025. Esta comparación descriptiva no demuestra que el Stuff físico haya mejorado: el modelo contextual conoce el conteo y la mano del bateador, y el índice estandarizado tiene una semántica nueva.

**Ninguno de los seis contrastes incrementales alcanzó la mejora mínima de 1%.** Se fortalecieron la evaluación y las herramientas de análisis, pero no se demostró una mejora suficiente para reemplazar el Stuff publicado.

El release F8 conserva sus modelos, scores y servidor. F9 queda disponible como experimento reproducible e inferencia local separada. No se consultaron registros de 2026 para entrenar o evaluar F9. Como los resultados de F8 ya eran conocidos y 2024–2025 se han reutilizado en fases anteriores, estas evidencias son exploratorias; hace falta una muestra nueva para confirmación independiente.

## Qué se implementó y por qué

| Implementación | Justificación |
|---|---|
| Módulo independiente `experiments/`, configuración y estrategia F9 | Preservar el código y los artefactos congelados de F8; fijar variantes antes de observar sus resultados. |
| Seis variables físicas derivadas | Facilitar interacciones de velocidad, movimiento, spin, release y extensión sin introducir resultados del lanzamiento. Se prueba su utilidad en lugar de asumirla. |
| Control contextual y contexto+física sin ubicación | Aislar la contribución incremental de la física, evitando atribuirle una mejora debida sólo al conteo. |
| Protocolos A temporal y B por pitcher | Separar el rendimiento en otra temporada del rendimiento en identidades excluidas de todo ajuste. |
| Arsenal histórico y altura en protocolo C | Evaluar ambas aportaciones sobre las mismas filas y con referencias exclusivamente de 2024. |
| Temperatura, Brier, bins y diagnósticos por clase/tipo/mano/altura | Detectar mejoras globales que oculten mala calibración o debilidad en grupos concretos. |
| Bootstrap pareado y corrección de seis comparaciones | Cuantificar incertidumbre y limitar conclusiones por probar varios candidatos. |
| Índice con contexto estandarizado, CLI y agregados de scouting | Comparar perfiles bajo una distribución común de conteos y mano del bateador, con referencia fija y soporte visible. |
| Verificador independiente y pruebas | Recalcular resultados, comprobar ausencia de cruces entre particiones, detectar corrupción y conservar F8. |

Las variables nuevas son `hand_hb`, `hand_release_side`, `movement_magnitude`, `spin_per_mph`, `speed_x_ivb` y `extension_x_speed`. Son transformaciones de las mediciones existentes; spin/velocidad no se presenta como eficiencia de spin. Se mantienen las unidades del contrato original.

## Diseño y poblaciones

| Protocolo | Ajuste | Development | Calibración | Review |
|---|---:|---:|---:|---:|
| A | 239,709 | 134,420 | 59,367 | 58,182 |
| B | 360,035 | 33,081 | 16,117 | 64,513 |
| C | 70,378 | 70,378 | 29,140 | 30,443 |

A ajusta con 2024 y separa 2025 por partido. B usa 2024–2025, separa por pitcher y calibra sólo con 2025; development y calibración pertenecen al mismo grupo de pitchers de validación pero a partidos distintos. Los pitchers de review B no aparecen en entrenamiento, development ni calibración. B permite partidos compartidos entre grupos de pitchers: no es park holdout ni holdout temporal.

C ajusta en development 2025 con 200 rondas fijas, sin early stopping. Su columna de ajuste y development representa las mismas filas, no dos muestras independientes. Usa sólo pitchers con referencia histórica válida: mínimo 30 rectas del tipo de referencia en 2024. Los contrastes C no se comparan directamente con A o B por usar distinta población y protocolo.

| Partición C | Elegibles comunes 2025 | Con historia válida | Cobertura |
|---|---:|---:|---:|
| calibration | 59,367 | 29,140 | 49.08% |
| development | 134,420 | 70,378 | 52.36% |
| phase_review | 58,182 | 30,443 | 52.32% |

Para inputs sin historia, el predictor experimental publicado usa la variante A de contexto+física, que no necesita identidad ni arsenal. Los candidatos C son resultados de investigación, no una ruta de producción aprobada; no se atribuye su rendimiento a la población sin historia.

## Métricas observadas

Menor log loss y Brier es mejor. Brier es la suma multiclase, no RMSE de carreras. Las variantes aprendidas se muestran después de temperatura; los baselines conservan sus probabilidades suavizadas. Las métricas raw y las temperaturas también están en `F9_RESULTS.json`.

### Protocolo A

| Modelo | Log loss | Brier |
|---|---:|---:|
| physical | 1.514487 | 0.753704 |
| engineered | 1.514450 | 0.753743 |
| context | 1.452508 | 0.733289 |
| context_physics | 1.445809 | 0.731360 |
| B0 | 1.531096 | 0.758257 |
| B1 | 1.463495 | 0.736558 |
| B2 | 1.454644 | 0.733993 |

### Protocolo B

| Modelo | Log loss | Brier |
|---|---:|---:|
| physical | 1.524049 | 0.758369 |
| engineered | 1.523697 | 0.758205 |
| context | 1.461447 | 0.737376 |
| context_physics | 1.455508 | 0.735744 |
| B0 | 1.537860 | 0.761940 |
| B1 | 1.470613 | 0.740018 |
| B2 | 1.462576 | 0.737592 |

### Protocolo C

| Modelo | Log loss | Brier |
|---|---:|---:|
| context_physics | 1.453850 | 0.734075 |
| arsenal | 1.451866 | 0.733521 |
| environment | 1.451452 | 0.733232 |

El Stuff congelado de F8, recalculado únicamente sobre las mismas 58,182 filas review 2025, tiene log loss **1.514729**. La variante `physical` F9 es un control reentrenado con el presupuesto común, no el modelo idéntico de F8. El ajuste de temperatura de F8 ya usó review para su política histórica; esta comparación retrospectiva es descriptiva.

### Contrastes predeclarados

| Comparación | Reducción relativa LL | Delta candidato−control | Intervalo nominal 99.1667% | Supera umbral |
|---|---:|---:|---|---|
| A:engineered_vs_physical | 0.0024% | -0.000037 | [-0.000623, 0.000550] | No |
| A:context_physics_vs_context | 0.4612% | -0.006698 | [-0.008113, -0.005184] | No |
| B:engineered_vs_physical | 0.0231% | -0.000352 | [-0.000843, 0.000167] | No |
| B:context_physics_vs_context | 0.4063% | -0.005938 | [-0.007409, -0.004623] | No |
| C:arsenal_vs_context_physics | 0.1365% | -0.001984 | [-0.004139, -0.000179] | No |
| C:environment_vs_arsenal | 0.0285% | -0.000413 | [-0.001432, 0.000614] | No |

### Clasificación de altura

Se conservaron `No Altitude`, `Medium Altitude` y `Extreme Altitude`. Esta tabla describe el rendimiento de los candidatos C en cada categoría observada; no simula mover el mismo lanzamiento a otro estadio ni estima delta Stuff+ Harp–mar.

| Categoría | Lanzamientos | Partidos | LL arsenal | LL arsenal+altura |
|---|---:|---:|---:|---:|
| No Altitude | 14,052 | 93 | 1.453800 | 1.453020 |
| Medium Altitude | 7,793 | 48 | 1.444451 | 1.444544 |
| Extreme Altitude | 8,598 | 50 | 1.455426 | 1.455152 |

Umbral fijado: reducción relativa ≥1% y extremo superior del intervalo <0. Los intervalos usan 1,000 remuestreos por partido, ponderados por cantidad de lanzamientos, con corrección Bonferroni para seis comparaciones. No incluyen incertidumbre por reentrenamiento ni resuelven toda la dependencia entre partidos del mismo pitcher. La repetición de análisis sobre los mismos años impide interpretar estos intervalos como validación final independiente.

Una reducción pequeña con intervalo negativo puede ser señal incremental sin alcanzar el umbral operativo. Una reducción negativa significa empeoramiento. Ninguna decisión del experimento sustituye automáticamente F8; el campo heredado `decision=promote`, si aparece, significa que superó el umbral estadístico local, mientras `production_promotion=false` conserva la política publicada.

## Índice experimental y uso por scouting

El modelo `A/context_physics` estima eventos con conteo y mano del bateador. Para puntuar se promedian sus predicciones calibradas sobre la distribución conjunta de esos contextos aprendida exclusivamente en train 2024. Cada lanzamiento utiliza los mismos pesos. Se calcula la utilidad provisional `P(whiff)+P(called_strike)−0.5·P(ball)−P(hit_by_pitch)` y se normaliza con media y desviación fijas de calibración 2025: `100 + 10·(utilidad−media)/desviación`.

**100 representa la media de esa referencia, no 100% de precisión.** El nombre es `context_standardized_event_utility_F9_v1`. No es xRunValue, carreras evitadas ni el Stuff+ físico original. El índice estandarizado no hereda automáticamente la calibración frente a eventos observados bajo otros conteos; las métricas anteriores evalúan predicciones en el contexto observado, no demuestran la calidad de un ranking por este índice.

La inferencia requiere sólo los once inputs físicos originales y opcionalmente `pitch_uid`. No requiere resultado, pitcher conocido ni ubicación final. Conserva orden y duplicados; filas inválidas devuelven score nulo y motivo; tipos desconocidos generan advertencia. Los inputs deben seguir el esquema canónico, incluyendo seno/coseno del eje de giro. Los contextos sintéticos pueden tener poco soporte para ciertos perfiles: no constituyen cambios causales demostrados.

`scouting.csv` contiene medias por pitcher/tipo y número de lanzamientos/partidos en review 2025. Marca provisional si hay menos de 200 lanzamientos o cinco partidos. Ese umbral es operativo, no un intervalo de confianza. El CSV contiene sólo lanzamientos elegibles comunes; no representa cobertura de toda la población ni normaliza la mezcla de tipos de cada pitcher.

## Evaluación frente al hackathon

| Criterio (peso) | Evidencia implementada | Estado y brecha real |
|---|---|---|
| Calidad Stuff+ (25%) | Comparaciones con B0/B1/B2, calibración, control contextual, transformaciones físicas y score reproducible. | Parcial. El modelo contextual mejora al baseline de eventos por conteo, pero no demuestra mejora suficiente del Stuff físico. Falta target oficial xRunValue y RMSE/calibración en carreras. |
| Robustez fuera de muestra (25%) | Holdout de pitchers explícito para las cuatro variantes y evaluación temporal, con métricas e intervalos. | Parcial. El holdout por pitcher está implementado; no hay identificadores de estadio para park holdout. Falta confirmación en datos nuevos no utilizados. |
| Arsenal + altitud (25%) | Cinco variables relacionales de historia 2024, ablation de arsenal y altura en idéntica cohorte, cobertura y desgloses por categoría. | Parcial. Incorporación técnica demostrada; beneficio depende de los resultados anteriores. No hay delta Stuff+ Harp Helú–nivel del mar ni evidencia causal: faltan mapping de parques y condiciones físicas. |
| Aplicabilidad real (25%) | API F8 conservada, CLI experimental sin outcomes, score fijo y agregados con soporte visible. | Parcial. Hay herramienta para explorar perfiles; falta entrevista de 10 minutos con coach/director y evidencia de decisiones de reclutamiento o táctica. |

No se asigna una calificación total inventada. Tener las fases implementadas no equivale a satisfacer los cuatro criterios. El avance de F9 es medible en experimentación controlada, diagnóstico e inferencia; la brecha decisiva sigue siendo validación de carreras, transferencia entre estadios y utilidad comprobada con usuarios.

La categoría `Extreme Altitude` no identifica por sí sola Harp Helú y `No Altitude` no establece una medición exacta a nivel del mar. El modelo de categoría mide asociaciones condicionadas a las features disponibles. La literatura puede motivar hipótesis, pero no sustituye la estimación empírica requerida en la LMB.

## Cómo probarlo

Desde la raíz del repositorio, con datos privados y release F8 disponibles:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\run_phase9.ps1 check
.\run_phase9.ps1 predict -OutputFile output/f9-ejemplo-nuevo.json
.\run_phase9.ps1 smoke -Name f9-smoke-nuevo
.\run_phase9.ps1 train -Name f9-reproduccion
```

Todos los comandos de ejecución usan `.venv`. El ejemplo JSON es sintético. El predictor no sobrescribe una salida existente; cada entrenamiento exige un nombre nuevo. El modo smoke verifica funcionamiento, no proporciona evidencia científica. El entrenamiento completo no utiliza datos 2026. Los modelos y el dataset no se incluyen en Git: una copia nueva del repositorio requiere restaurarlos desde almacenamiento autorizado.

Pruebas funcionales útiles: cambiar el conteo o quitar outcomes no debe cambiar el score estandarizado; enviar velocidad negativa produce `invalid_input`; cambiar el archivo del modelo provoca rechazo por integridad; repetir la auditoría debe recalcular las mismas métricas y comparaciones. El verificador comprueba ejemplos sin outcomes y filas inválidas, además de las pruebas unitarias.

## Verificación y archivos

Pasaron **125 pruebas unitarias**, incluidos siete casos nuevos F9. La corrida completa verificó **15 controles internos** y la auditoría independiente **16 comprobaciones**. El release F8 mantiene su identidad `4df11fbf516455a6c90c45bea2f780a3e2441a64f1c6f15a6e637c84c619ef64`. El registro de exposición del test permanece sin cambios.

- `config/phase9.json`: presupuesto, variantes y criterios.
- `experiments/phase9.py`: entrenamiento, evaluación, score y agregados.
- `experiments/phase9_predict.py`: inferencia experimental.
- `experiments/check_phase9.py`: auditoría independiente.
- `tests/test_phase9.py`: pruebas de fuga, invariancias, serialización e integridad.
- `docs/F9_RESULTS.json`, `docs/F9_AUDIT.json` y `docs/F9_VALIDATION.json`: evidencia resumida versionable.
- `artifacts/modeling/f9-full/F9`: modelos, predicciones, referencias, diagnósticos y manifiesto locales.

## Siguientes pasos de mayor impacto

1. Obtener definición oficial del target de carreras y construir el baseline xRunValue por conteo; evaluar RMSE sin confundirlo con métricas de eventos.
2. Obtener IDs de estadio, identificación del Harp y altitud/atmósfera; diseñar park holdout y simulación respaldada por datos físicos.
3. Reservar una nueva muestra independiente antes de confirmar cualquier candidato F9. No convertir 2026 ya expuesto en un nuevo test limpio.
4. Probar tres casos de uso con coach/director y registrar si el output cambia una decisión, cuál y con qué evidencia.

## Referencias

[FanGraphs: Stuff+, Location+ y Pitching+](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/) y [PitchingBot](https://library.fangraphs.com/pitching/pitchingbot-pitch-modeling-primer/) distinguen atributos físicos, contexto y ubicación. Esa separación motiva los controles de F9; sus resultados no se transfieren automáticamente a la LMB. La estrategia y las limitaciones están documentadas antes del entrenamiento en `FASE_9_ESTRATEGIA.md`.
