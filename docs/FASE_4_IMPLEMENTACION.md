# Fase 4: calibración y calidad del contacto

Fecha de entrega: 10 de octubre de 2026, America/Mexico_City.

**Implementada y verificada dentro de `.venv`.** 75 pruebas automatizadas y 84 controles completos aprobados. Las predicciones se reprodujeron sin diferencias. El detalle de qué cabezas se promueven y cuáles conservan la referencia se encuentra en «Resultados verificados».

## Qué se implementó y por qué

F4 agrega calibración de probabilidades y objetivos auxiliares a las tres familias,
conservando las listas de variables de F3 y LightGBM 4.6.0 en CPU. Todas las ejecuciones
utilizan el Python de `.venv`. No se modificaron datos preparados ni modelos aprobados de F3.

| Componente | Implementación | Motivo |
|---|---|---|
| Eventos | Modelos Stuff, Location y Pitching de F3 congelados. | Aislar el efecto de la calibración sin volver a seleccionar modelos base. |
| Calibrador | Una temperatura escalar sobre log-probabilidades; softmax conserva la suma uno. | Mantener una distribución conjunta de seis clases, sin calibrar seis binarios incompatibles. |
| Ajuste del calibrador | Solo 2025/calibration; temperatura entre 0.05 y 20; identidad disponible. | Reservar revisión para la decisión y evitar ajustar con etiquetas de revisión o test. |
| Aceptación | Conservar la temperatura solo si no aumenta la log loss de revisión. | Aplicar de forma conservadora el contrato: el máximo permitido es 0.5%, pero aquí se exige aumento de 0%. Si perjudica, se conserva identidad. |
| Contacto débil/duro | Una cabeza de tres clases: weak (<75 mph), medium (75 a <95), hard (>=95). | Las tres clases son excluyentes; débil y duro no pueden sumar más de uno. |
| Groundball | Cabeza de dos clases, condicionada a bola en juego con tipo de batazo conocido. | Separar la forma del contacto de su velocidad. Se entrega como diagnóstico, sin recompensa automática por prevenir carreras. |
| Chase | Cabeza de dos clases: take/swing, condicionada a estar fuera de la zona suministrada. | Respetar el denominador original. No se confunde con swing por pitch ni se reconstruye una zona nueva. |
| Baselines auxiliares | Prevalencia de entrenamiento con pseudocuenta 1 por clase. | Comparar cada cabeza contra una referencia estimada sobre las mismas etiquetas disponibles. |
| Fallback | Cabeza no promovida: prevalencia de entrenamiento. Sin muestra suficiente: nulo y motivo. | No presentar una variante sin evidencia como mejora ni inventar predicciones cuando faltan datos suficientes. |

Aceptar una temperatura no promueve por sí solo Stuff frente a B1 ni modifica las
decisiones físicas/contextuales de F3. Pitching conserva la referencia predictiva de eventos;
Stuff sigue disponible como familia física diagnóstica.

Se reutiliza la transformación de variables de F3: vocabularios aprendidos solo en ajuste,
categorías desconocidas con advertencia y rama de categoría faltante, entradas requeridas
nulas o no finitas rechazadas. No se incorporan IDs, outcomes, velocidad de salida ni tipo
del batazo como predictores. La velocidad y el tipo del batazo solo definen etiquetas.

## Alcance temporal y población

La fase usa el **protocolo A** y los datos fijados `c1c8ba48818dc878`. Se mantiene la
cohorte común elegible de F3 para alinear familias, eventos y productos condicionales.
La población etiquetada de cada objetivo auxiliar es un subconjunto explícito de esa cohorte.

- **2024/train:** modelos auxiliares, vocabularios y prevalencias.
- **2025/development:** parada temprana de los modelos auxiliares.
- **2025/calibration:** temperaturas de eventos y cabezas auxiliares.
- **2025/phase_review:** elección entre temperatura/identidad y comparación contra prevalencia.
- **2026:** permanece sellado.

El protocolo B aprobado en F3 se conserva. No se mezclan sus particiones 2024–2025 con
la calibración de F4, que el contrato restringe expresamente a calibración de 2025.
Esta entrega no presenta una nueva evaluación calibrada por pitcher; los resultados de B
siguen siendo los de F3. La altura permanece excluida de los predictores, según la secuencia
del contrato; su incorporación corresponde a F6.

Las etiquetas de contacto se derivan de los indicadores preparados, con nulos preservados:
si no hay velocidad de salida, no se asigna arbitrariamente medium, weak ni hard. Una bola
en juego sin tipo conocido tampoco pasa a ser un ejemplo negativo de groundball.
La función rechaza indicadores débil/duro contradictorios y etiquetas de contacto fuera de
`in_play`. Los joins uno a uno por `pitch_uid` preservan la correspondencia de etiquetas.

Cada cabeza guarda cobertura por partición: total de eventos elegibles, etiquetas
disponibles, faltantes y conteos por clase. Para contacto y groundball se registra además
cuántas bolas en juego carecen de la medición necesaria. La selección de batazos medidos
puede introducir sesgo: las métricas condicionales no demuestran rendimiento sobre los
batazos sin medición. En chase, los nulos también incluyen pitches fuera de su población
condicional; no se describen todos como mediciones faltantes.

## Entrenamiento, métricas y decisiones

Se predeclara una única configuración auxiliar para todas las familias y cabezas:
15 hojas, mínimo 100 filas por hoja, learning rate 0.05 y L2=5. Hasta 200 rondas en completo,
40 en smoke, paciencia de 25 y cuatro hilos CPU. La semilla es `20260929`. No se amplía
la búsqueda después de conocer revisión. Un segundo ajuste del modelo ya elegido comprueba
reproducibilidad; no es una búsqueda adicional.

Se exigen al menos **200 etiquetas y 20 por clase** en entrenamiento y revisión. También
se exige ese soporte en desarrollo para usar parada temprana y en calibración para ajustar
una temperatura. Si calibración no alcanza el soporte, se usa identidad. Si falta soporte
para entrenar/evaluar una cabeza, se marca `insufficient_data`, no se calculan comparaciones
inferenciales ni rankings y sus probabilidades públicas quedan nulas.

La métrica primaria es log loss. Se conserva Brier multiclase como suma sobre clases;
para cada evento binario se entrega también su **Brier binario** sin duplicarlo, log loss
y PR-AUC como average precision con empates agrupados. Para la cabeza de contacto se
reportan métricas de la distribución conjunta y métricas uno contra el resto por clase.
No se sustituyen estos diagnósticos por accuracy.

Las comparaciones usan bootstrap pareado por partido: 500 remuestreos completos, 20 en
smoke, intervalo percentil del 95%. Promover una cabeza exige al menos 1% de reducción
relativa de log loss y límite superior de diferencia candidato menos referencia menor
que cero. La temperatura usa la regla operativa de no empeoramiento, no esa regla de
promoción predictiva. También se guarda su comparación pareada, sin atribuir causalidad.

Las cabezas tienen estados separados de la implementación: `validated`, `experimental`
o `insufficient_data`. Se conservan predicciones candidatas para auditoría aunque la salida
pública use la prevalencia de entrenamiento. Las curvas antes/después se guardan en CSV
y SVG, con diez intervalos fijos y cantidades por intervalo. Los intervalos escasos no
permiten conclusiones firmes de calibración. Revisión se utiliza repetidamente y no es
una prueba final independiente.

## Probabilidades que se entregan

`predictions.parquet` conserva una fila por `(pitch_uid, family)` en la cohorte de evaluación.
Incluye partición, datos, protocolo, estado, advertencias y ruta de cada cabeza.

| Columnas | Semántica |
|---|---|
| `p_ball` … `p_hit_by_pitch` | Distribución de seis eventos con la política temperatura/identidad elegida. |
| `p_weak_given_in_play`, `p_medium_given_in_play`, `p_hard_given_in_play` | Probabilidades condicionales de velocidad de salida entre bolas en juego. |
| `p_weak_per_pitch`, `p_medium_per_pitch`, `p_hard_per_pitch` | Producto de la probabilidad condicional por `p_in_play` de la misma familia. |
| `p_groundball_given_in_play`, `p_groundball_per_pitch` | Probabilidad condicional y su producto por `p_in_play`. |
| `p_chase_given_outside` | Probabilidad de swing condicionada a estar fuera de la zona suministrada. No es chase por pitch. |
| `contact_status/route`, `groundball_status/route`, `chase_status/route` | Evidencia y ruta usada: modelo, prevalencia suavizada o no disponible. |

Los productos no usan el resultado observado del pitch. Se comprueba que estén en [0,1],
que débil+duro no exceda uno y que las tres categorías conjuntas sumen `p_in_play`.
La calibración de eventos y las cabezas corresponden a la misma familia y protocolo.
La extrapolación a batazos no medidos mantiene la limitación de selección descrita antes.

## Archivos y cómo probarlo

| Ruta | Contenido |
|---|---|
| `modeling/calibration.py` | Temperatura escalar, persistencia y elección temperatura/identidad. |
| `modeling/contact.py` | Etiquetas condicionales, soporte mínimo, modelos auxiliares, prevalencias y métricas binarias. |
| `modeling/phase4.py` | Verificación de F3, ejecución y registro completo de F4. |
| `tests/modeling/test_contact.py` | Pruebas de fuga, nulos, exclusividad, fallback, guardado y métricas. |
| `scripts/check_phase4.py` | Verificador independiente de cohortes, temperaturas, predicciones, métricas y decisiones. |
| `artifacts/modeling/f4-smoke-check/F4/` | Prueba rápida; sin conclusiones científicas. |
| `artifacts/modeling/f4-full-check/F4/` | Ejecución completa con modelos, curvas y decisiones por familia/cabeza. |

Cada ejecución guarda manifiesto, configuración, hashes, versiones, tiempos, cohorte,
controles, métricas y decisión. Cada familia guarda `event/`, `contact/`, `groundball/` y
`chase/`. Los modelos nativos y sus metadatos se conservan en `model/`; el calibrador en
`temperature.json` cuando hay soporte; su decisión siempre en `calibration_policy.json`.
Los artefactos y datos permanecen locales, excluidos de Git.

Desde la raíz del proyecto:

```powershell
# Pruebas automatizadas dentro del entorno virtual.
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Comprobar contrato y reproducir la ejecución guardada en otro proceso.
.\.venv\Scripts\python.exe scripts/check_modeling_contract.py
.\.venv\Scripts\python.exe scripts/check_phase4.py --experiment-id f4-full-check

# Nuevas ejecuciones con identificador automático, sin sobrescribir las anteriores.
.\run_modeling.ps1 f4-smoke
.\run_modeling.ps1 f4

# Equivalentes si la política de PowerShell impide ejecutar el lanzador.
.\.venv\Scripts\python.exe -m modeling.cli train --phase F4 --smoke
.\.venv\Scripts\python.exe -m modeling.cli train --phase F4
```

En otra computadora se necesita crear `.venv`, instalar `requirements-modeling.txt` y
disponer de la versión autorizada de datos y los artefactos aprobados F0–F3. La ejecución
no descarga datos del reto. Los IDs de experimento existentes se rechazan para proteger
los resultados previos. El verificador debe terminar con `status: verified`; los errores
de permisos de carpetas temporales del sistema se resuelven ejecutando las pruebas con
acceso a esas carpetas, sin cambiar el entorno virtual ni las reglas de evaluación.

F5 no se inicia automáticamente. Esta fase no entrega scores, xRunValue ni simulación
ambiental. Groundball sigue siendo un diagnóstico y weak contact un proxy provisional.

## Resultados verificados

**F4 verificada.** Pasaron 75 pruebas automatizadas, 83 controles rápidos y 84 completos. El verificador independiente reprodujo 755,907 filas públicas de probabilidades, 135 grupos de métricas y 21 comparaciones bootstrap de la ejecución completa. Las predicciones recargadas no presentaron diferencias. Las temperaturas se reajustaron en el verificador exclusivamente con calibración 2025 y también se reprodujeron.

Las pruebas iniciales de archivos temporales fueron bloqueadas por permisos del sandbox de Windows; la repetición autorizada, con el mismo Python de `.venv`, pasó las 75 pruebas sin modificar la lógica. No quedan fallos técnicos observados.

Tiempo local del entrenamiento y evaluación completos: **7.97 minutos**, cuatro hilos CPU; incluye los reajustes de comprobación. No es una promesa de rendimiento en otro equipo.

### Cohorte

| Partición | Pitches | Partidos |
|---|---:|---:|
| train | 239,709 | 833 |
| development | 134,420 | 447 |
| calibration | 59,367 | 197 |
| phase_review | 58,182 | 192 |

### Calibración de eventos

| Familia | Temperatura ajustada | Log loss original en revisión | Con temperatura | Ruta aceptada |
|---|---:|---:|---:|---|
| stuff | 0.929978 | 1.515176368 | 1.514729481 | temperature |
| location | 0.991236 | 1.049467005 | 1.049397380 | temperature |
| pitching | 0.986942 | 1.032505818 | 1.032353004 | temperature |

La ruta `identity` mantiene las probabilidades originales. La aceptación de temperaturas obedece a no empeorar, incluso si su mejora no llega al 1% exigido para promover una cabeza predictiva nueva.

### Cabezas auxiliares frente a prevalencia

| Familia | Cabeza | Log loss referencia | Log loss candidato seleccionado | Reducción relativa | IC 95% de diferencia | Estado/ruta |
|---|---|---:|---:|---:|---|---|
| stuff | contact | 1.052348 | 1.042356 | 0.949% | [-0.012231, -0.007767] | experimental/smoothed_training_prevalence |
| stuff | groundball | 0.694989 | 0.671953 | 3.315% | [-0.026151, -0.019731] | validated/model |
| stuff | chase | 0.641577 | 0.639810 | 0.275% | [-0.002726, -0.000760] | experimental/smoothed_training_prevalence |
| location | contact | 1.052348 | 0.982183 | 6.667% | [-0.077025, -0.063639] | validated/model |
| location | groundball | 0.694989 | 0.668789 | 3.770% | [-0.029183, -0.023486] | validated/model |
| location | chase | 0.641577 | 0.467870 | 27.075% | [-0.178374, -0.169007] | validated/model |
| pitching | contact | 1.052348 | 0.982694 | 6.619% | [-0.076163, -0.063191] | validated/model |
| pitching | groundball | 0.694989 | 0.654327 | 5.851% | [-0.045514, -0.036190] | validated/model |
| pitching | chase | 0.641577 | 0.456382 | 28.866% | [-0.190102, -0.180265] | validated/model |

Las métricas de la tabla son del candidato para evaluar su aporte. Si el estado es experimental, la salida pública conserva la prevalencia suavizada; las probabilidades del candidato permanecen como diagnóstico. Las métricas binarias de hard/weak/groundball/chase y PR-AUC están en los archivos de cada cabeza.

### Cobertura de etiquetas

Las tres familias usan el mismo subconjunto común; los siguientes recuentos no se suman entre familias.

| Partición | Contacto con velocidad disponible | In-play sin velocidad | Groundball con tipo conocido | In-play sin tipo | Chase con etiqueta condicional |
|---|---:|---:|---:|---:|---:|
| train | 38,977 | 5,555 | 39,520 | 5,012 | 154,819 |
| development | 24,207 | 794 | 24,454 | 547 | 85,571 |
| calibration | 10,525 | 342 | 10,622 | 245 | 38,366 |
| phase_review | 10,346 | 336 | 10,446 | 236 | 37,157 |

### Temperaturas y rondas auxiliares

| Familia/cabeza | Rondas elegidas | Temperatura ajustada | Calibración aceptada |
|---|---:|---:|---|
| stuff/contact | 41 | 1.212526 | temperature |
| stuff/groundball | 189 | 1.317756 | temperature |
| stuff/chase | 111 | 0.915340 | temperature |
| location/contact | 186 | 1.164197 | temperature |
| location/groundball | 147 | 1.294581 | temperature |
| location/chase | 200 | 0.927894 | temperature |
| pitching/contact | 180 | 1.127721 | temperature |
| pitching/groundball | 198 | 1.140255 | temperature |
| pitching/chase | 200 | 0.908152 | temperature |

### Cierre

Decisión científica de fase: **`promote`**, con decisiones por cabeza preservadas. **F5 queda habilitada y no se inicia automáticamente.** La referencia de eventos sigue siendo Pitching; no se convierte la promoción de una cabeza auxiliar en una afirmación de carreras prevenidas.

Evidencia: `docs/F4_VALIDATION.json`, `docs/F4_FULL_VALIDATION.json` y `docs/F4_SMOKE_VALIDATION.json`. Los hashes de los módulos ejecutados coinciden con los archivos entregados. Los manifiestos de experimentos certifican `verified`; sus configuraciones conservan el estado inicial `in_progress`. El contrato actual se actualiza después de cerrar la verificación. 2026 sigue sellado.
