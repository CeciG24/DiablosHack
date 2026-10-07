# Auditoría del dataset y plan para cuatro integrantes

Fecha: 27 de septiembre de 2026. Fuente: `Diablos - Hackathon 2026 (1).zip`, representación `stuff_model_df.parquet` y diccionario incluido. Se revisó la tabla completa; no se entrenó un modelo ni se modificaron los datos fuente. Los formatos RDS y pickle no se compararon con Parquet.

## Inventario y cobertura

- 635,002 lanzamientos, 84 columnas y 635,002 PitchUID distintos.
- 2,127 partidos, 1,134 pitchers y 864 bateadores identificados.
- 2024: 243,254 lanzamientos / 833 partidos.
- 2025: 256,144 lanzamientos / 839 partidos.
- 2026: 135,604 lanzamientos / 455 partidos. Sin fechas no se puede establecer el periodo exacto ni afirmar que sea una temporada completa.
- Altitud: No Altitude 293,875; Medium Altitude 154,840; Extreme Altitude 183,267; faltante 3,020.
- 865 pitchers aparecen en más de una categoría de altitud. Ningún partido con categoría conocida aparece en varias categorías.
- 633,447 filas (99.76%) tienen completos RelSpeed, SpinRate, SpinAxis, RelHeight, RelSide, Extension, InducedVertBreak y HorzBreak. Completitud no equivale a validez física.

## Limitaciones para cumplir el reto

No hay identificador de estadio ni indicador de Harp Helú, altitud numérica, temperatura, presión o humedad. No se debe equiparar Extreme Altitude con Harp Helú, ni asumir que No Altitude significa exactamente nivel del mar. El holdout por categoría de altitud no equivale a park holdout.

No hay fecha, timestamp, número de lanzamiento ni identificador de aparición al plato. El orden de las filas no está documentado como cronológico. No es defendible construir prev_pitch_type ni historial acumulado por fecha sin aclaración. Los promedios de arsenal deben obtenerse dentro de cada partición de entrenamiento o de una muestra de adaptación separada, declarando cualquier uso transductivo.

Hay conteo y outs, pero no ocupación de bases ni target de run value proporcionado. RunsScored no sustituye al valor de carreras de un pitch. No puede reconstruirse directamente el run expectancy estándar de 24 estados ni P(out within PA) con agrupación fiable de apariciones al plato. Se pueden predecir resultados observables; un score compuesto sería un proxy que debe explicitar sus pesos y analizar sensibilidad.

## Calidad y coherencia

| Hallazgo | Cantidad | Acción recomendada |
|---|---:|---|
| is_hit_by_pitch siempre cero | 635,002 filas | Contrastar con 2,280 HitByPitch en PitchCall y 2,258 en play_result; acordar etiqueta canónica |
| Swing fallido marcado también como contacto | 450 | Auditar etiquetas antes de entrenar |
| is_ball_in_play contradice PitchCall | 2 | Revisar y documentar regla |
| Pitcher anónimo faltante | 3,272 | Excluir de evaluación agrupada y arsenal; 3,122 son de 2026 |
| Altitud faltante | 3,020 | Excluir del contraste de ambiente o tratar como desconocida |
| Extension negativa | 99 | Poner en cuarentena para modelado físico |
| Extension mayor de 10 pies | 28 | Revisar valores extremos, sin eliminarlos automáticamente |
| PlateLocHeight igual a cero | 6,669 | Comprobar posible truncamiento/codificación antes de Location+ |
| Outs igual a 3 antes del pitch | 8 | Revisar estado de juego |
| EffectiveVelo almacenada como texto | Toda la columna | Todos los valores se convierten a número sin pérdida por coerción |

Los conteos Balls/Strikes coinciden con count tras normalizar tipos. is_whiff coincide con is_swinging_strike; no hay whiffs sin swing. Las banderas dentro/fuera de zona son complementarias y chase coincide con swing fuera de zona. Estas comprobaciones internas no validan la definición geométrica de la zona.

ExitSpeed falta en 71.21% de todas las filas, pero solo en 6.70% de las filas marcadas como bola en juego. Angle falta en 6.70%, hit_type en 5.65% y Distance en 11.34% de esas bolas en juego. La falta global es mayormente estructural; no imputar cero en lanzamientos sin contacto. Existen mediciones de contacto en fouls: definir la población de cada target explícitamente.

Hay categorías de pitch con una sola observación (OneSeamFastBall, TwoSeamFastBall, Knuckleball). Sweeper tiene 588 y Splitter 7,289. Definir agrupación o abstención para categorías pequeñas, sin asumir etiquetas erróneas por su baja frecuencia.

## Señal inicial de altitud

Tasas descriptivas, sin ajuste por composición:

| Categoría | Whiffs / swings | Home runs / filas is_ball_in_play=1 |
|---|---:|---:|
| No Altitude | 24.80% | 3.65% |
| Medium Altitude | 24.01% | 4.25% |
| Extreme Altitude | 23.13% | 4.26% |

Estas cifras no identifican causalidad ni el efecto específico del Harp Helú. La segunda tasa usa la bandera suministrada, incluidas sus dos discrepancias; no es HR por elevado ni por aparición al plato.

Comparación más específica: agrupar por pitcher, año y AutoPitchType; exigir al menos 30 pitches en cada una de las categorías Extreme Altitude y No Altitude; calcular media de IVB por grupo/categoría; tomar mediana entre grupos de la diferencia Extreme menos No. Cada grupo pesa igual. Se obtuvieron 1,096 pares:

| Pitch | Grupos | Diferencia mediana IVB (pulgadas) |
|---|---:|---:|
| Four-Seam | 450 | -3.84 |
| Sinker | 178 | -2.46 |
| Changeup | 101 | -2.19 |
| Cutter | 28 | -2.05 |
| Slider | 271 | -0.74 |
| Curveball | 64 | +2.02 |
| Splitter | 4 | +0.35 |

El signo positivo en curvas representa un desplazamiento del IVB hacia valores más positivos, no una mejora de calidad. La comparación mantiene pitcher/año/tipo, pero no controla spin, velocidad, release, selección, fecha ni calibración de sensores. Son hipótesis para el modelo, no coeficientes de corrección ni deltas Stuff+ demostrados. Los cuatro grupos de splitter no sostienen conclusiones generales.

## Modelado recomendado

1. Definir targets a partir de PitchCall y contrastarlos con banderas antes de elegir una fuente canónica. Comenzar con resultado por pitch y probabilidades derivadas. Distinguir P(whiff por pitch) de P(whiff dado swing), y chase condicionado a estar fuera de zona.
2. Baseline por conteo, aprendido únicamente en entrenamiento. Añadir tipo de pitch en un segundo baseline.
3. Stuff físico compacto: velocidad, movimiento, spin circular (seno/coseno), release, extensión y mano del pitcher. Reservar ubicación, conteo y lado del bateador para capas contextuales. Documentar discrepancia entre el brief y el diccionario sobre BatterSide. No incorporar outcomes como entradas; revisar variables de trayectoria que puedan reconstruir ubicación.
4. Location+: ubicación, conteo, tipo de pitch y lado del bateador. Pitching+: combinar física, ubicación, arsenal y categoría de altitud. No llamar a esta última un modelo específico de Harp sin mapeo de estadio.
5. Arsenal: diferenciales contra recta de referencia calculados solo con información permitida por la partición. Para pitchers nuevos, distinguir escenario sin historial de escenario con una muestra inicial de adaptación. No usar el repertorio completo de test sin declararlo.
6. Usar 2024 para entrenar, 2025 para selección/calibración y 2026 para prueba final. Separar también una prueba de pitchers no vistos. En 2026 hay 249 IDs no presentes en 2024/2025, con 42,162 lanzamientos: subconjunto útil, sin asegurar que sean debutantes reales ni que los IDs sean estables entre temporadas.
7. Validar por categoría de altitud como diagnóstico provisional; solicitar estadio para cumplir park holdout. Para extrapolar a una categoría no vista, una variable categórica por sí sola no aporta una escala física transferible.
8. Comparar modelo base, +arsenal y +ambiente sobre las mismas particiones. Medir calibración y log loss/Brier para probabilidades. No reportar RMSE de un xRunValue inexistente.
9. Mantener una normalización de scores de referencia común, aprendida en entrenamiento, para no borrar diferencias ambientales. Reportar incertidumbre agrupando por pitcher o partido, no tratando cada pitch como observación independiente.

## Reparto propuesto entre cuatro integrantes

| Responsable | Perfil preferible | Responsabilidad | Entrega al día 3 |
|---|---|---|---|
| 1. Datos y evaluación | Orden, pandas/SQL, atención al detalle | Limpieza, diccionario, targets y particiones; controla fugas de información | Tabla preparada, reglas y splits reproducibles |
| 2. Modelos | Mayor experiencia estadística/ML | Baselines, tres capas, probabilidades y calibración | Primer modelo comparado contra baseline |
| 3. Arsenal y ambiente | Interés en física/estadística/béisbol | Comparaciones dentro de pitcher, arsenal, incertidumbre y limitaciones | Análisis de diferencias de movimiento y diseño de features |
| 4. Producto y comunicación | Visualización, frontend y explicación | Dashboard, integración, documento técnico y demo | Prototipo que recibe predicciones de ejemplo claramente identificadas |

Cada persona escribe la sección técnica de su área; la persona 4 integra. Revisión cruzada: 1 revisa splits de 2, 2 revisa estimación de 3, 3 revisa interpretación de 4 y 4 comprueba que resultados de 1 sean utilizables.

Hitos: días 1–3 limpieza/splits/baseline; 4–6 modelos y arsenal; 7–9 ambiente/validación; 10–11 demo integrada; 12 documento; 13 ensayo; 14 correcciones. No bloquear el trabajo esperando campos adicionales: avanzar con categorías de altitud y límites explícitos.

## Preguntas prioritarias para organizadores

1. ¿Pueden entregar un mapeo game_anon_id a estadio anonimizado, indicador Harp Helú y altitud en metros, y definir los umbrales de altitude_category?
2. ¿Pueden proporcionar fecha, orden del pitch e ID de aparición al plato? ¿El orden actual es cronológico y los IDs de pitcher estables entre temporadas?
3. ¿Hay ocupación de bases o run_value oficial y definición de xRunValue esperada para evaluación?
4. ¿Qué fuente es canónica ante contradicciones entre PitchCall, play_result y banderas? Reportar is_hit_by_pitch y los 450 casos de swing/contacto.
5. ¿Cuál es la definición exacta de zona y el tratamiento de PlateLocHeight=0? ¿Qué periodo cubre 2026?

## Reproducibilidad

El script audit_dataset.py produce perfiles de columnas, estadísticos numéricos, agregaciones por año/altitud/tipo, chequeos de coherencia y pares pitcher/año/tipo. Solo extrae Parquet y diccionario en analysis; preserva el ZIP. Los resultados descriptivos no son una validación predictiva ni una recomendación individual de contratación.
