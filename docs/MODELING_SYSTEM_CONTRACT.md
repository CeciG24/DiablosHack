# System contract para el desarrollo del modelado

Versión 1.0.0 · 29 de septiembre de 2026 · Proyecto Diablos Hackathon

## 1 Propósito y autoridad

Este contrato dirige la implementación incremental de los modelos sobre la base preparada.
Cada fase debe producir un resultado ejecutable, evidencia de pruebas y una decisión de
continuidad. No autoriza presentar un modelo como superior antes de evaluarlo.

**Rol del implementador:** ingeniero de machine learning responsable de reproducibilidad,
prevención de fugas de información, evaluación y una interfaz consumible por el dashboard.
Implementar una fase por vez cuando se solicite; ejecutar sus pruebas, registrar resultados
y detener el avance si falla una condición técnica necesaria. No entrenar todas las fases
ni abrir el test final como consecuencia de leer este documento.

**Prioridad:** instrucciones explícitas del equipo y reglas oficiales del reto; contrato de
datos vigente; este contrato; configuración de cada experimento. Si una modificación afecta
targets, población, score o evaluación, versionarla y explicar su impacto. No cambiar reglas
silenciosamente para obtener mejores métricas.

La infraestructura de **F0 está implementada** en `modeling/`, con comando `smoke` y pruebas.
El cierre y la evidencia están en `docs/FASE_0_IMPLEMENTACION.md`. **F1 está implementada y
verificada**, con baselines B0/B1/B2 en `modeling/baselines.py`; su cierre se documenta
en `docs/FASE_1_IMPLEMENTACION.md`. **F2 está implementada y verificada** con LightGBM
4.6.0 en CPU; dependencias en `requirements-modeling.txt`. **F3 está implementada y
verificada**, con Location/Pitching sin ambiente y protocolos A/B. **F4–F8 siguen pendientes**;
no hay scores reales. Los cierres están en `docs/FASE_2_IMPLEMENTACION.md` y
`docs/FASE_3_IMPLEMENTACION.md`. F3 promueve Location y Pitching en ambos protocolos;
Pitching pasa a ser la referencia predictiva y Stuff se conserva como diagnóstico.
La preparación de datos sí está implementada.
`config/modeling_contract.json` contiene los parámetros operativos iniciales. En caso de
divergencia, detener la fase y reconciliar ambos documentos antes de ejecutarla.

## 2 Punto de partida comprobado

| Componente existente | Estado y uso |
|---|---|
| `data/CURRENT` | Apunta a `c1c8ba48818dc878` al redactar este contrato |
| `diablos_data.py` | `current_run`, `connect`, `load_model_data`, `load_arsenal` |
| `config/data_contract.json` | Reglas de limpieza, temporadas y umbrales de contacto |
| `docs/DATA_CONTRACT.md` | Semántica de datos, targets y restricciones |
| Base preparada | 635,002 pitches; 84 columnas fuente; 8 tablas preparadas |
| Matriz Stuff con `y_event` | 242,426 train; 254,580 validation; 133,579 test |
| Verificación previa | 22 controles de publicación y 7 pruebas de preparación aprobados |

Una ejecución de modelado debe fijar el identificador de datos y los hashes del manifiesto.
No depender de que `data/CURRENT` siga apuntando a la misma versión durante el experimento.
Si cambia, abortar o leer explícitamente la versión fijada; no combinar versiones.

La API actual usa casos completos y diferentes filtros por familia. **Igualar índices de
DataFrames no iguala pitches.** Todas las comparaciones deben hacer join uno a uno por
`pitch_uid` y registrar la población común. El loader no incluye conteo en los metadatos de
Stuff: el baseline por conteo debe obtenerlo mediante un join controlado, sin añadirlo a X
del modelo físico. La familia `pitching` actual ya incluye altitud: para la ablación sin
ambiente se debe excluir explícitamente `altitude_category`.

## 3 Reglas obligatorias

1. Usar listas explícitas de predictores. No entrenar con `SELECT *`, IDs, outcomes, año,
   `source_row_number`, `event_candidate` ni banderas de calidad como predictores por defecto.
2. Mantener la definición de Stuff físico separada de ubicación, conteo, bateador y ambiente.
   Location es una predicción condicionada por ubicación y contexto; no una estimación causal
   de comando ni una medida de distancia al objetivo del catcher.
3. Ajustar codificadores, imputación, escalado, selección y modelos solo en el conjunto
   autorizado para ajuste. Las reglas de calidad existentes se respetan; no optimizarlas en test.
4. Respetar targets nulos y sus poblaciones. Whiff por pitch y whiff dado swing son distintos.
   P(contacto duro por pitch) = P(in_play) × P(contacto duro | in_play), con modelos compatibles.
5. No construir xRunValue, barrel, out dentro de PA, secuencia previa, spin efficiency o
   tunneling real sin información y definiciones suficientes. `RunsScored` no es run value.
6. No llamar Harp Helú a Extreme Altitude, ni nivel del mar exacto a No Altitude. No llamar
   park holdout a un holdout de categorías. Cambiar una categoría no identifica causalidad.
7. No completar arsenal de 2024 con 2025. No usar la tabla histórica directamente en el
   holdout de pitchers sin definir qué historia tendrá disponible un pitcher nuevo.
8. No descargar ni subir los datos a servicios externos para implementar este contrato.
   Mantener versiones y registros locales; compartir solo dentro del alcance autorizado.
9. Cada resultado debe registrar población, denominador, semilla, modelo, datos y estado.
   Un score sin predicción válida debe ser nulo con motivo, nunca 100 por defecto.
10. Mantener el último modelo aprobado cuando una nueva variante no mejora. Una ablación
    negativa es un resultado válido y no justifica añadir complejidad al producto.

## 4 Protocolos de evaluación

### Protocolo temporal principal A

- **2024:** entrenamiento de modelos base. Usar los folds de partido existentes para
  verificaciones internas; nunca dividir pitches del mismo partido entre folds internos.
- **2025:** dividir por `game_anon_id` mediante SHA256 con semilla fijada en configuración:
  50% esperado de partidos para desarrollo, 25% para calibración y 25% para revisión de fase.
  Los porcentajes son por hash de partido, no cuotas exactas por pitch.
- **2026:** prueba final sellada hasta F8. El perfilado de calidad previo se declara; no se
  ha entrenado un modelo con 2026. No usar métricas de 2026 para decidir fases anteriores.

El hash se calcula como los primeros 16 caracteres hexadecimales de
SHA256(`seed + "|" + game_anon_id`), convertido a entero y módulo 10000. Valores 0–4999
son desarrollo, 5000–7499 calibración y 7500–9999 revisión. Guardar la asignación por pitch.

Desarrollo selecciona hiperparámetros; calibración ajusta calibradores de candidatos ya
seleccionados; revisión compara variantes. Como la revisión se utiliza repetidamente para
decidir fases, **no es una estimación final independiente**. Solo 2026 mide el resultado
final sin selección posterior. Un calibrador descartado no se reajusta sobre revisión.

### Generalización a pitchers B

Durante el desarrollo, intersectar `pitcher_split` con años 2024–2025; **no usar directamente
el loader de protocolo pitcher sin filtrar años**, pues sus grupos actuales abarcan 2026.
Entrenar en pitchers train, desarrollar/calibrar en pitchers validation con separación de
partidos y revisar en pitchers test, siempre excluyendo 2026. En F3 la separación de validation usa SHA256 con la semilla
`diablos-modeling-pitcher-validation-v1`, primeros 16 caracteres hexadecimales módulo 10000:
0–4999 desarrollo, 5000–9999 calibración. Conservar los años originales. Informar que el protocolo no
es temporal y que un partido puede contener pitchers de grupos distintos.

En F8 evaluar también el subconjunto temporal de pitchers no vistos en 2026: 249 IDs y
42,162 pitches antes de filtros. Confirmar estabilidad de IDs con los organizadores. Estas
dos evaluaciones responden preguntas distintas y sus métricas se reportan por separado.

### Reglas estadísticas comunes

- Primaria para `y_event`: log loss multiclase; orden de clases fijo en configuración.
- Secundaria: Brier multiclase = media por pitch de la suma sobre las seis clases de
  `(p_k - 1[y=k])²`. No dividir además por número de clases sin cambiar nombre y versión.
- Binarios: log loss, Brier y curvas de calibración; PR-AUC como diagnóstico de clases raras.
  AUC o accuracy no sustituyen calibración. No exigir que cada bin contenga la misma muestra.
- Curvas: 10 bins de amplitud fija en [0,1], mostrando cantidad de observaciones y positivos.
  No interpretar bins escasos como prueba concluyente de mala calibración.
- Comparaciones sobre los **mismos pitches y target**, con bootstrap pareado por partido,
  500 remuestreos para revisión completa y 20 solo para verificar el flujo. Semilla fija.
- Promoción predictiva por defecto: reducción relativa de log loss de al menos 1% y límite
  superior del intervalo bootstrap del 95% de `loss_candidato - loss_referencia` menor que 0.
  Este 1% es una regla del equipo propuesta, no una regla oficial ni un resultado observado.
- Si mejora menos, el intervalo cruza cero o falta muestra: `inconclusive` y conservar la
  referencia. Un componente puede existir para interpretación, pero no anunciarse como mejora.
- Para objetivos auxiliares, exigir al menos 200 ejemplos y 20 por clase en entrenamiento
  y en la revisión evaluada; en caso contrario reportar `insufficient_data`, sin métricas
  inferenciales ni ranking. Umbrales operativos, no garantía de potencia estadística.

## 5 Artefactos y estados de cada fase

Estructura propuesta para implementar desde F0:

```text
modeling/
  cli.py              # interfaz train, evaluate, predict, smoke y release
  datasets.py         # versión fija, cohortes y acceso restringido por etapa
  baselines.py
  models.py
  calibration.py
  arsenal.py
  environment.py
  scoring.py
  metrics.py
tests/modeling/
artifacts/modeling/<experiment_id>/<phase_id>/
  manifest.json
  config.json
  metrics.json
  predictions.parquet
  checks.json
  decision.md
```

Los modelos entrenados y transformadores se guardan además cuando proceda. El manifiesto
contiene hashes de datos/código/configuración, versiones, semillas, protocolo, tiempos y
cohortes. `predictions.parquet` identifica exactamente cada pitch y partición. No versionar
grandes artefactos binarios en Git; ampliar `.gitignore` en F0.

Estados de implementación: `not_started`, `in_progress`, `verified`, `blocked`.
Decisión científica separada: `promote`, `retain_reference`, `inconclusive`, `not_applicable`.
Una fase puede estar verificada aunque su candidato pierda. Una prueba técnica fallida no
permite declarar `verified`. Si falta un campo externo, completar la parte independiente,
registrar la limitación y no marcar satisfecho el requisito oficial afectado.

## 6 Fases de implementación

### F0 Adaptador de modelado y pruebas de infraestructura

**Objetivo tangible:** cargar una cohorte reproducible y producir predicciones ficticias
claramente etiquetadas para comprobar el flujo, sin entrenar ni leer labels de 2026.

**Implementar:** fijación de versión; subparticiones de 2025; selección de columnas y
cohortes comunes; registro de experimentos; acceso al test deshabilitado salvo modo F8.
Las probabilidades ficticias solo prueban formatos y jamás se exportan como scores reales.

**Entregar:** manifiesto de cohorte con hashes de IDs, asignación de subparticiones,
resumen de exclusiones y comando `smoke`. Puede muestrear hasta 20,000 pitches por hash de
partido, sin garantizar tamaño exacto; la muestra rápida no sustenta conclusiones científicas.

**Pruebas:** IDs únicos; mismo resultado al barajar filas; ningún partido cruza subparticiones
de 2025; ausencia de 2026; joins uno a uno; conjuntos físicos/contextuales exactos; error
explícito ante versión cambiante, target desconocido o intento de abrir test sin autorización F8.

**Criterio para avanzar:** todos los controles pasan y se reproduce el mismo hash de cohorte.

### F1 Baselines evaluables

**Objetivo tangible:** primera tabla de probabilidades reales y métricas reproducibles.

**Implementar:** B0 distribución global; B1 distribución por conteo; B2 por conteo y tipo
de pitch. Estimar en entrenamiento con suavizado hacia la distribución global y retroceso
explícito cuando el grupo no existe. Concentración inicial 20 observaciones equivalentes;
no ajustar con revisión ni test. B0 también debe evitar ceros con pseudocuenta 1 por clase.

**Entregar:** probabilidades de seis clases, log loss, Brier y curvas en 2025. B1 es la
referencia conceptual del reto, pero aún no representa su baseline de xRunValue: el target
de carreras no está disponible. B2 es una comparación adicional, no un reemplazo oculto.

**Pruebas:** probabilidades finitas en [0,1], suma 1 con tolerancia 1e-6; todas las clases
presentes; grupo no visto usa fallback; reproducción tras guardar/cargar; conteos calculados
solo en entrenamiento. Alinear metadatos por `pitch_uid` para obtener conteo.

**Criterio para avanzar:** flujo completo y métricas válidas. Si B1 pierde contra B0,
reportarlo; no bloquear el proyecto ni modificar datos para forzar superioridad.

### F2 Modelo físico Stuff

**Objetivo tangible:** predecir `y_event` con las 11 variables físicas permitidas.

**Implementar:** un único backend inicial de gradient boosting tabular. Elegir y fijar su
versión en un archivo separado de dependencias de modelado. Usar el mismo backend en las
capas siguientes salvo necesidad documentada. Presupuesto máximo inicial: 12 configuraciones,
semilla fija y parada temprana sobre desarrollo de 2025, cuando el backend la soporte.

**Entregar:** modelo guardado, importancia de variables mediante permutación en desarrollo,
predicciones y comparación pareada contra B0 y B1 sobre la misma cohorte elegible.
El conteo puede ayudar al baseline, pero nunca se incorpora a X del modelo físico.

**Pruebas:** cambiar conteo, ubicación, bateador, altitud o ID no cambia la predicción física;
faltantes/categorías desconocidas generan el comportamiento definido; no hay outcomes en X;
guardar y recargar conserva predicciones con tolerancia 1e-8 en CPU y mismo entorno.

**Criterio de decisión:** regla de promoción frente a B1. Si no se cumple, conservar el
modelo como candidato diagnóstico, registrar `retain_reference` y continuar con otras capas.
La incapacidad de Stuff puro para vencer un baseline contextual no demuestra por sí sola
que las variables físicas carezcan de valor: analizar también su aporte en F3.

### F3 Location y Pitching sin ambiente

**Objetivo tangible:** tres familias diferenciadas y una primera ablación física/contexto.

**Implementar:** Location con su lista existente; Pitching con la lista existente menos
`altitude_category`. No promediar Stuff y Location para construir Pitching: entrenar el
modelo combinado. Comparar sobre la intersección explícita de pitches válidos para todos.

**Entregar:** tabla B1/Stuff/Location/Pitching sobre igual población, tamaños por partición
y evaluación B de pitchers no vistos en años de desarrollo. Reportar además cobertura propia
de cada familia, sin confundirla con la comparación pareada.

**Pruebas:** conteo y ubicación no entran en Stuff; física no entra en Location salvo tipo y
mano permitidos; ambiente todavía no entra en Pitching; joins no duplican ni desplazan etiquetas.

**Criterio de decisión:** Pitching debe evaluarse frente a Location y B1. Promover solo el
aporte que tenga evidencia; mantener artefactos distintos para las tres preguntas del reto.

### F4 Calibración y calidad del contacto

**Objetivo tangible:** probabilidades interpretables, con objetivos de contacto bien definidos.

**Implementar:** calibración posterior de los candidatos elegidos, ajustada solo en el
subconjunto de calibración de 2025. Para eventos multiclase, comenzar con temperature scaling
escalar sobre logits o log-probabilidades; no calibrar seis binarios y asumir que suman uno.
Comparar calibrado/no calibrado en revisión; si el calibrador perjudica, conservar identidad.

Añadir predicciones para `y_hard_contact_bip`, `y_weak_contact_proxy_bip` y
`y_groundball_bip`, con las variables permitidas de cada familia. Para débil/duro, preferir
una cabeza conjunta de tres clases (salida menor de 75, desde 75 hasta menos de 95, y al
menos 95 mph), que asegure categorías excluyentes. Groundball usa una cabeza binaria
independiente. No publicar probabilidades débil y duro cuya suma supere 1. Reportar falta de mediciones
y población elegible; la selección de batazos medidos puede introducir sesgo. Chase es un
objetivo secundario explícitamente condicionado a estar fuera de la zona suministrada.

**Entregar:** curvas antes/después; métricas de cada cabeza contra prevalencia suavizada;
probabilidades condicionales y por pitch en columnas diferentes. Groundball se reporta
como diagnóstico, no como recompensa automática de prevención de carreras.

**Pruebas:** calibradores no ven labels de revisión/test; no convertir nulos a negativos;
productos condicionales en [0,1]; evento sigue sumando uno; fallbacks y tamaños mínimos.

**Criterio de decisión:** aceptar solo calibraciones que no aumenten log loss de revisión
más de 0.5% relativo; es una tolerancia operativa, no significancia estadística. Cabezas
auxiliares sin mejora o sin muestra se marcan experimentales/no disponibles, sin ocultarlo.

### F5 Experimento de arsenal con historia real

**Objetivo tangible:** medir el aporte del repertorio sin rellenar el pasado con el futuro.

**Implementar un protocolo C separado:** usar exclusivamente 2024 como referencia fija
de arsenal para todos los pitches a evaluar de 2025 y, finalmente, 2026. Construir esta
referencia anclada con las mismas reglas de recta del contrato de datos. **No reutilizar sin
cambios las features históricas de 2026 existentes**, pues incorporan 2025.

En C, el subconjunto desarrollo de 2025 se usa para ajustar modelos con/sin arsenal; el
subconjunto calibración para sus calibradores, y revisión para compararlos. Mantener 2024
solo como soporte histórico. Declarar que la separación interna de 2025 es por partido,
no cronología. Comparar ambos candidatos sobre exactamente la misma población con referencia.
El protocolo C no se compara con A como si tuviesen iguales datos de entrenamiento.

**Entregar:** ablation con/sin arsenal, cobertura de referencia por categoría y pitcher,
política de fallback al modelo combinado sin arsenal para pitches sin historia, y referencia
2024 versionada. El modelo sin arsenal usado como control de C se entrena en las mismas
filas que el modelo con arsenal. Evaluar además la política completa con fallback sobre
toda la población elegible, mostrando qué rama atendió cada caso.

**Pruebas:** ninguna referencia contiene pitches de 2025/2026; modificar un outcome del
pitch evaluado no modifica features; pitcher sin historia usa fallback, no medias de test;
no llamar túnel a la distancia de release. En generalización fría a pitchers, usar fallback;
si se proporciona historia, etiquetar el escenario como adaptación con historia.

**Criterio de decisión:** promover arsenal solo con evidencia pareada y cobertura explícita.
Si no mejora o no hay muestra, dejarlo como análisis del repertorio y conservar el modelo base.

### F6 Ambiente y simulación honesta

**Objetivo tangible:** comparación de categorías ambientales con límites visibles.

**Implementar:** añadir `altitude_category` al mejor candidato sin ambiente dentro de su
mismo protocolo A o C. Reentrenar su control sin ambiente con las mismas filas, calibrar
en la partición autorizada y comparar. Medir desempeño por categoría, tipo y mano cuando
hay muestra suficiente. Guardar cobertura y categorías vistas en ajuste.

**Simulador inicial:** mantener física, ubicación y arsenal constantes y cambiar únicamente
la categoría. Etiqueta obligatoria: `fixed_shape_environment_association`. Es una comparación
condicional del modelo, no una transformación física de la trayectoria ni un efecto causal.
Stuff puro y Location sin ambiente deben permanecer invariantes al cambiar solo la categoría.
El delta ambiental pertenece a Pitching, aunque se muestre junto a Stuff físico.

**Entregar:** deltas de probabilidad antes del score, intervalos por remuestreo agrupado
con el alcance declarado y explicación de restricciones. El bootstrap de partidos de una
evaluación mide incertidumbre de desempeño o del promedio de una cohorte; no es por sí solo
un intervalo de incertidumbre para un pitch individual ni para una causalidad ambiental.

**Pruebas:** categoría desconocida devuelve `unsupported_environment`; el sistema no produce
un supuesto Harp sin mapeo; no reduce nuevamente IVB observado al cambiar solo categoría;
entradas fuera del soporte de entrenamiento muestran advertencia y no una recomendación firme.

**Criterio de decisión:** promoción predictiva mediante ablación. Park holdout y simulación
física del mismo release permanecen pendientes de estadio/datos/supuestos adicionales.
Retirar una categoría puede servir como estrés exploratorio, pero una categoría no vista
por sí sola no permite extrapolación física defendible.

### F7 Scores y agregación interpretables

**Objetivo tangible:** convertir probabilidades en índices trazables, sin inventar run value.

**Implementar score provisional S0:**

```text
S0 = P(whiff) + P(called_strike) - 0.5*P(ball) - P(hit_by_pitch)
plus = 100 + 10*(S0 - mu_referencia)/sigma_referencia
```

Los pesos son una utilidad exploratoria fijada antes de abrir test; no carreras esperadas.
El foul tiene peso 0 por convención provisional. Mostrar siempre las probabilidades junto al
score y etiquetar `score_semantics=event_utility_proxy_v1`. No optimizar pesos con 2026.

Si las cabezas de contacto están verificadas, experimentar por separado con S1:

```text
S1 = S0 + 0.5*P(in_play)*P(weak_contact_proxy | in_play)
        - P(in_play)*P(hard_contact | in_play)
```

Registrar otra versión, justificar los pesos y estudiar sensibilidad en desarrollo, por
ejemplo variaciones relativas de ±25% manteniendo signos. No mezclar S0 y S1 en un ranking
ni sustituir una cabeza ausente por cero. Fijar una única versión de score para cada release.

Para cada familia, fijar mu y sigma sobre una cohorte de referencia común de 2025-calibración
con IDs guardados, usando las predicciones de la política final y desviación estándar
poblacional (`ddof=0`). Nunca renormalizar por estadio, tipo, pitcher, test o solicitud.
La cohorte de calibración puede fijar esta escala, pero no se reporta como validación independiente.
100 significa media de **esa referencia elegible**, no promedio demostrado de toda la LMB.
No afirmar que 120 es percentil 97 sin comprobar distribución ni que 80 sea reemplazo.

**Entregar:** Stuff+, Location+ y Pitching+ provisionales separados; mu/sigma, versión de
utilidad y población de referencia; agregados por pitcher/tipo con n y cobertura. Promediar
scores de pitches válidos para el agregado observado; cualquier arsenal con mezcla estándar
es otro estimando y debe identificar sus pesos. No mezclar escalas entre ramas de fallback:
normalizar la política completa con una única referencia por familia y versión.

**Pruebas:** media 100 y desviación 10 en referencia con tolerancia 1e-6; sigma>1e-12;
no hay infinitos; cambiar el conjunto de consulta no cambia el score de un pitch;
las comparaciones ambientales usan la misma mu/sigma; valores altos de utilidad implican
scores altos. Ante ausencia de cobertura, emitir nulo y motivo.

**Criterio para avanzar:** escala reproducible y advertencias visibles. No presentar S0/S1
como xRunValue ni como Stuff+ validado de FanGraphs. La entrega oficial de carreras sigue pendiente.

### F8 Evaluación final y entrega al producto

**Objetivo tangible:** release congelado, evaluación de 2026 y contrato de inferencia usable.

**Prerequisito:** hashes de modelos, calibradores, cohortes, score, normalizadores y configuración
congelados en `release_lock.json`. El modo de test requiere el ID de ese release y registra
su apertura. No reajustar modelos con 2025 después de congelar sin recalibrar y redefinir
el protocolo completo antes de abrir test.

**Implementar:** evaluación del release completo en 2026, incluyendo subgrupo de pitchers
no vistos, categorías ambientales y cobertura. Contrastar candidatos/control predeclarados
solo como informe final; no elegir al ganador usando test. Si el resultado decepciona, se
reporta. Cualquier cambio posterior se etiqueta como desarrollo con test ya expuesto.

**Entregar:** modelo y política final, ficha del modelo, probabilidades/scores por pitch,
agregados por pitcher y arsenal, tres casos de scouting con evidencia, contribución al
documento técnico de 6–10 páginas e interfaz local para el dashboard.

**Pruebas:** ciclo completo guardar/cargar/predecir; lote con entradas válidas e inválidas;
categoría no vista; pitcher sin historia; referencia de datos fijada; suma de probabilidades;
coherencia del score y fallback. Benchmark local con hardware, tamaño de lote y tiempo
reportados; no prometer una latencia universal antes de medirla.

**Criterio de cierre:** release reproducible, evaluación transparente y casos revisables.
La ausencia de estadio, PA o run value debe aparecer en la matriz de cumplimiento, no
ocultarse detrás del dashboard. Haber implementado F8 no garantiza haber satisfecho todos
los requisitos oficiales que dependen de campos aún ausentes.

## 7 Interfaz de inferencia que debe implementarse

Una petición acepta features observables en unidades del diccionario y una familia/política
versionada. No requiere outcomes ni un pitcher conocido para física/ubicación. Puede recibir
una referencia histórica autorizada para arsenal. Definir esquema y validar rangos/tipos.

Respuesta mínima por registro:

```text
request_id / pitch_uid
model_version, data_version, score_version, reference_id, protocol_id
family, route (base | arsenal | fallback), status, warnings
probabilities {ball, called_strike, whiff, foul, in_play, hit_by_pitch}
conditional_probabilities {hard_contact_bip, weak_contact_proxy_bip, groundball_bip}
stuff_plus / location_plus / pitching_plus (según familia; nulo si no disponible)
environment_mode, reference_pitch_count, input_support_status
```

Estados: `ok`, `invalid_input`, `insufficient_history`, `unsupported_environment`,
`unsupported_model`. Con fallback válido puede emitirse `ok` y advertencia de historia
insuficiente; registrar la ruta. No inventar intervalos individuales: devolverlos solo si
hay método implementado, validado y descrito. Scoring batch conserva una fila de salida por
entrada; las inválidas llevan scores nulos y motivo. La API actual de entrenamiento no
sustituye esta nueva interfaz de inferencia.

## 8 Trazabilidad frente al reto

| Requisito | Fases | Situación esperada |
|---|---|---|
| Stuff, Location y Pitching por pitch | F2–F4, F7 | Probabilidades y escala provisional explícita |
| Scores por pitcher y arsenal | F5, F7 | Agregados con muestra, referencia y mezcla definidas |
| Arsenal más ambiente | F5–F6 | Ablaciones con controles y cohortes iguales |
| Pitcher y season holdout | F3, F8 | Protocolos separados y test final temporal |
| Park holdout | F6, F8 | Pendiente de identificar estadios |
| Harp frente a nivel del mar | F6 | Categorías como escenario inicial; especificidad Harp pendiente |
| Perfil físico ideal y recomendaciones | F6–F8 | Casos dentro del soporte de datos; no optimización hacia extremos irreales |
| Simulador y mapa de movimiento | F6–F8 | Interfaz de predicción y datos para visualización |
| xRunValue y RMSE correspondiente | Rama futura | Pendiente de target y estados adecuados; no sustituir por S0 |
| Documento técnico y entrevista | F8 | Métricas, decisiones, tres casos y fronteras del sistema |

Si llegan los campos faltantes, abrir una versión del contrato: nuevo target/datos y baseline
de carreras, evaluación por estadio, y validación del simulador físico. No cambiar targets
en medio de una comparación ni atribuir al nuevo sistema los resultados del antiguo.

## 9 Distribución sugerida y secuencia de trabajo

| Responsable | Fases principales | Revisión cruzada |
|---|---|---|
| Datos y evaluación | F0, cohortes y métricas de F1–F8 | Revisa fugas y particiones de todos |
| Modelado | F1–F4, score F7 | Revisa controles con/sin arsenal y ambiente |
| Arsenal y ambiente | F5–F6 | Revisa interpretación de scores y escenarios |
| Producto y comunicación | Esquema F0, integración F7–F8 | Verifica que cada salida responda una decisión |

Secuencia sugerida para 14 días efectivos: F0–F1 días 1–2; F2–F3 días 3–5; F4 días 6–7;
F5 días 8–9; F6 día 10; F7 día 11; F8 y documento días 12–14. Es una planificación, no una
garantía. Priorizar fases verificables; si una mejora no se sostiene, entregar la referencia.

## 10 Instrucción reutilizable para ejecutar una fase

```text
Implementa únicamente la fase F<N> de docs/MODELING_SYSTEM_CONTRACT.md.
Lee también config/modeling_contract.json y docs/DATA_CONTRACT.md.
Verifica los artefactos aprobados de sus dependencias. No asumas que están implementados.
Preserva datos y resultados anteriores. No uses labels de 2026 salvo F8 con release congelado.
Implementa, ejecuta la prueba rápida y luego las verificaciones completas que correspondan.
Entrega archivos, métricas con población y protocolo, pruebas ejecutadas y fallos pendientes.
Separa estado de implementación de decisión científica; no avances automáticamente de fase.
```

Formato obligatorio del cierre de fase: qué se implementó; rutas de artefactos; datos y
cohortes; pruebas rápidas/completas; métricas y comparación cuando corresponda; decisión
`promote/retain_reference/inconclusive`; limitaciones; siguiente fase habilitada.
