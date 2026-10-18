# Fase 10: arsenal regularizado y movimiento condicionado por altura

Fecha: 17 de octubre de 2026. Rama: `fase-9`. Experimento: `f10-full`.

## Resultado ejecutivo

Se implementó una fase nueva dentro de la misma rama, conservando F8 y F9. La mejora más clara está en predecir el movimiento: la categoría de altura aporta información que el enfoque anterior, centrado en eventos con movimiento fijo, no medía directamente. Se entrenaron cinco modelos de eventos y cuatro de movimiento, con pruebas separadas de cada aportación.

| Movimiento | RMSE sin altura (pulgadas) | RMSE con altura | Reducción de RMSE |
|---|---:|---:|---:|
| induced_vert_break | 2.4057 | 2.0760 | 13.71% |
| horz_break | 2.4380 | 2.0917 | 14.20% |

**Esto mejora la predicción de IVB/HB; no significa una mejora equivalente en Stuff+, xRunValue o carreras.** El arsenal regularizado tiene un aporte pequeño e incierto al modelo de eventos; la geometría relativa al arsenal empeora frente al control con trayectoria propia. No se reemplaza el modelo publicado.

## Qué se hizo y por qué

| Implementación | Motivo |
|---|---|
| Auditoría de ejes, tiempos y extremos de trayectoria | Evitar usar coordenadas incorrectas o confundir aceleración con el coeficiente cuadrático. |
| Referencias 2024 para ocho tipos, con medias y dispersión regularizadas | Aprovechar historia escasa y medir relaciones con todo el repertorio, en lugar de depender sólo de una recta con 30 observaciones. |
| Uso y fiabilidad por tipo; identificación de prior sin historia | Dar una salida finita sin presentar promedios de grupo como historia real del pitcher. |
| Control de trayectoria propia y candidato de geometría relativa | Separar información de ubicación de la supuesta ventaja de parecerse a otro lanzamiento. |
| Modelos IVB/HB con y sin categoría de altura | Medir si el ambiente ayuda a explicar el movimiento antes de estimar sus consecuencias sobre eventos. |
| Simulador de cambio de movimiento con residuo conservado | Partir del pitch observado y modificar sólo la diferencia predicha entre categorías. |
| Cabezas de contacto ya congeladas de F8 | Mostrar un diagnóstico adicional sin reentrenar ni inventar resultados de contacto en escenarios. |
| Auditoría independiente, serialización y controles de soporte | Hacer reproducibles los resultados y rechazar escenarios no respaldados por la muestra. |

Todos los cambios están en archivos nuevos de `experiments/phase10*`, `experiments/check_phase10.py`, configuración, pruebas y comandos F10. No se editaron los modelos congelados ni la implementación de F9.

## Auditoría geométrica

La convención comprobada es `c0+c1·t+c2·t²`: x longitudinal hacia el plato, y vertical y −z lateral. El coeficiente c2 ya contiene el factor de la forma polinómica: no se multiplica otra vez por 1/2. La auditoría se hizo sobre 2024 antes del entrenamiento completo. Se usan planos longitudinales a 40, 20 y 8 pies; son puntos geométricos operativos, no tiempos cognitivos medidos del bateador.

| Comprobación | Error mediano (pies) | Percentil 95 (pies) |
|---|---:|---:|
| plate_height | 0.001182 | 0.007610 |
| plate_side | 0.001661 | 0.006062 |
| plate_longitudinal | 0.003906 | 0.009235 |
| release_height | 0.001880 | 0.007210 |
| release_side | 0.002830 | 0.006500 |
| release_longitudinal | 0.001470 | 0.004150 |

Pasaron los filtros por fila **241,243 de 243,254 trayectorias históricas (99.17%)**. Se exigió mediana ≤0.05 pies, p95 ≤0.25 pies y error por fila ≤0.25 pies. Las trayectorias inválidas se marcan; sus features geométricas se rellenan con cero acompañado de una bandera. Esto audita coherencia interna de las mediciones, no valida independientemente el dispositivo.

## Arsenal regularizado y cobertura

Para cada combinación pitcher–mano–tipo, la media histórica se mezcla con la media mano–tipo de 2024 mediante `w=n/(n+30)`. El segundo momento se regulariza de la misma forma para obtener dispersión no negativa. El uso del tipo también se suaviza. Los ocho tipos aportan diferencias de velocidad, IVB, HB y release, uso y fiabilidad; se añaden dispersiones del tipo actual y cantidad de historia.

Los grupos ausentes usan priors de entrenamiento. La geometría compara contra un pool histórico de rectas Four-Seam/Sinker regularizado. No se conoce la secuencia real, por lo que esto no demuestra tunneling entre dos lanzamientos consecutivos.

| Review común 2025 | Lanzamientos | Interpretación |
|---|---:|---|
| F9 C con referencia aprobada | 30,443 | Cohorte histórica con umbral de rectas. |
| F10 con historia individual válida | 32,125 | Referencia individual mezclada con el prior. |
| F10 sólo con prior de grupo | 26,057 | No hay repertorio individual observado utilizable. |
| F10 elegibles comunes evaluados | 58,182 | Cobertura del modelo ampliada a la cohorte común, no a todos los pitches crudos. |

La mejora de cobertura no es pasar de 52% a 100% de historia observada: se amplía la población que puede procesar el candidato de arsenal y se distingue su fallback. F9 ya tenía un modelo base para pitchers sin historia.

## Comparación de eventos: controles con las mismas filas

Los cinco modelos se ajustaron con 134,420 pitches development 2025, calibraron con 59,367 y evaluaron con 58,182 review, separados por partido. Todos tienen 200 rondas y los mismos hiperparámetros; no se seleccionaron por review.

| Variante | Log loss calibrado | Brier multiclase |
|---|---:|---:|
| base | 1.446522 | 0.731647 |
| regularized | 1.445426 | 0.730977 |
| trajectory | 1.037725 | 0.535532 |
| geometry | 1.043683 | 0.538187 |
| environment | 1.043714 | 0.538204 |

`base` usa las features contextuales/físicas de F9. `regularized` añade arsenal; `trajectory` añade los puntos propios; `geometry` añade diferencias contra la referencia geométrica; `environment` añade la categoría.

**La reducción de 28.21% al añadir trayectoria propia no es una mejora demostrada de Stuff físico ni de arsenal:** los puntos cercanos al plato aportan ubicación. El contraste de geometría relativa controla precisamente esa información y empeora 0.574% en log loss.

El Pitching publicado de F8, conservado también durante F9, obtiene **1.032353** sobre estas mismas filas 2025, mejor que el candidato F10 de trayectoria (1.037725). Por tanto, F10 tampoco demuestra una mejora del mejor modelo de eventos ya disponible.

### Comparación retrospectiva con los candidatos F9

Estas métricas usan exactamente las mismas 30,443 filas review cubiertas por F9 C, pero F10 se entrenó con una población mayor. No son una ablation controlada de una sola feature.

| Candidato | LL F9 | LL F10 | Reducción relativa |
|---|---:|---:|---:|
| base | 1.453850 | 1.450187 | 0.252% |
| regularized | 1.451866 | 1.448603 | 0.225% |
| environment | 1.451452 | 1.057931 | 27.112% |

La fila `environment` cambia también la disponibilidad de trayectoria/ubicación; no atribuir esa diferencia al ambiente. El cambio de arsenal por sí solo se evalúa en el contraste regularized–base de la cohorte completa.

## Movimiento y generalización

Los modelos de movimiento se ajustaron exclusivamente con 239,709 pitches train 2024. Sus predictores son tipo, mano, velocidad, spin/eje, altura/lado de release y extensión, con o sin categoría ambiental. No consumen IVB/HB observados como features, ubicación, outcomes ni ID del pitcher. Se evaluaron en 2025 sin reajuste.

| Movimiento | RMSE sin altura, pitchers no vistos | RMSE con altura, pitchers no vistos | N |
|---|---:|---:|---:|
| induced_vert_break | 2.5037 | 2.1749 | 26,057 |
| horz_break | 2.5671 | 2.2075 | 26,057 |

Este subgrupo sí excluye pitchers del entrenamiento de los modelos de movimiento. Para los modelos de eventos C, “sin historia 2024” no significa pitcher no visto durante el ajuste 2025: no se presenta como un nuevo pitcher holdout de eventos. La validación B de F9 permanece disponible, pero no valida automáticamente las nuevas variantes F10.

| Target | Categoría | N | RMSE control | RMSE ambiente |
|---|---|---:|---:|---:|
| induced_vert_break | Extreme Altitude | 15,400 | 2.3967 | 1.8605 |
| induced_vert_break | Medium Altitude | 14,922 | 2.0547 | 1.8895 |
| induced_vert_break | No Altitude | 27,860 | 2.5787 | 2.2748 |
| horz_break | Extreme Altitude | 15,400 | 2.2547 | 1.7778 |
| horz_break | Medium Altitude | 14,922 | 1.9864 | 1.8645 |
| horz_break | No Altitude | 27,860 | 2.7367 | 2.3513 |

### Incertidumbre de los seis contrastes

| Contraste | Reducción de pérdida | Delta candidato−control | Intervalo 99.1667% | Supera umbral |
|---|---:|---:|---|---|
| regularized_vs_base | 0.076% | -0.001096 | [-0.002308, 0.000293] | No |
| trajectory_vs_regularized | 28.206% | -0.407701 | [-0.416261, -0.398165] | Sí |
| geometry_vs_trajectory | -0.574% | 0.005958 | [0.003279, 0.008602] | No |
| environment_vs_geometry | -0.003% | 0.000032 | [-0.000657, 0.000800] | No |
| induced_vert_break_environment_vs_control | 25.533% | -1.477646 | [-1.805393, -1.163467] | Sí |
| horz_break_environment_vs_control | 26.389% | -1.568555 | [-1.884931, -1.286272] | Sí |

Pérdida = log loss en eventos y MSE en movimiento; las reducciones de MSE son distintas de las de RMSE. Umbral: ≥1% y extremo superior del intervalo <0. Se usan 2,000 remuestreos pareados por partido y corrección nominal de seis contrastes. Son intervalos de modelos fijos sobre datos de desarrollo reutilizados; no incluyen incertidumbre por reentrenamiento ni eliminan toda dependencia entre partidos del mismo pitcher.

## Cómo funciona el simulador

Para cada componente de movimiento se calcula `movimiento_destino = movimiento_observado + g(físicas, destino) − g(físicas, origen)`. Así se conserva el residuo particular del pitch. Se recalculan los features derivados y sus diferencias contra la historia fija 2024. No se traslada todo el arsenal ni se escala otra vez el movimiento observado por un porcentaje arbitrario de densidad.

La calidad se obtiene del candidato `regularized`, sin categoría directa ni coordenadas de trayectoria. Se integra sobre la misma distribución de conteo/mano del bateador aprendida por F9 en 2024, y se normaliza con media/desviación propias de calibración 2025. El score es `F10_regularized_context_standardized_utility_v1`, con utilidad `P(whiff)+P(called strike)−0.5·P(ball)−P(HBP)`. No es xRunValue ni una escala intercambiable con F9. La cabeza regularizada se usa como componente experimental, no porque haya superado el umbral de promoción.

El diagnóstico de contacto usa las cabezas congeladas F8/Pitching y conserva ubicación, conteo y mano observados. Si faltan esos inputs, el diagnóstico queda no disponible. Sus probabilidades de contacto duro/groundball están condicionadas a bola en juego; no son tasas de jonrón ni validación de escenarios contrafactuales.

Se exige soporte mínimo de 200 filas tipo/mano/categoría, cinco pitchers de entrenamiento con al menos 30 pitches del tipo en cada categoría, rangos marginales observados y movimientos proyectados dentro del contrato. Esta superposición se usa como filtro de soporte; no es un estimador dentro del pitcher ni garantiza control causal. Los rechazos tienen motivo y delta nulo; una categoría como “Harp Helu” se rechaza porque no existe ese mapping.

### Escenarios exploratorios guardados

Se tomaron los primeros 1,000 IDs ordenados de review, sin seleccionar por resultados. No es una muestra representativa garantizada. Las medias siguientes usan sólo los casos con soporte; los intervalos describen esa muestra y el modelo fijo, no la precisión de un cambio individual ni el efecto real de trasladar a un pitcher.

| Origen → destino | N soportado / solicitado | Delta medio del índice | Intervalo |
|---|---:|---:|---|
| Extreme Altitude → Medium Altitude | 217/247 | 0.471 | [0.236, 0.725] |
| Extreme Altitude → No Altitude | 244/247 | 2.737 | [2.196, 3.352] |
| Medium Altitude → Extreme Altitude | 231/260 | -0.519 | [-0.812, -0.217] |
| Medium Altitude → No Altitude | 254/260 | 3.034 | [2.275, 3.789] |
| No Altitude → Extreme Altitude | 490/493 | -3.171 | [-3.642, -2.724] |
| No Altitude → Medium Altitude | 478/493 | -2.697 | [-3.117, -2.272] |

Las filas inversas corresponden a distintos lanzamientos y soportes, por lo que sus medias no tienen por qué ser simétricas. Para el mismo pitch, origen=destino produce exactamente delta cero. **El −3.17 de No Altitude→Extreme Altitude no es una estimación Harp–mar ni una penalización aplicable a todos los pitchers.**

## Qué mejora frente a F9 y qué no

| Aspecto | Cambio real |
|---|---|
| Uso del ambiente | F9 añadía categoría con IVB/HB fijos; F10 demuestra aporte predictivo de la categoría al movimiento y permite propagar esa diferencia. |
| Arsenal | Más tipos y dispersión, referencias suaves y trazabilidad de prior. Aporte a log loss pequeño, no concluyente. |
| Geometría | Convención verificada y controles de ubicación. La relación geométrica añadida no mejora el control; queda descartada para promoción. |
| Simulación | Nuevo cambio de movimiento, score y contacto condicionado, con soporte explícito y rechazo de escenarios desconocidos. |
| Calidad del mejor modelo de eventos | No se demostró superar el Pitching publicado. |
| Validación | Evidencia temporal y pitchers no vistos para movimiento; falta nuevo holdout de eventos para los candidatos C y confirmación final independiente. |

## Qué sigue pendiente para el hackathon

La categoría puede representar también diferencias entre parques, instrumentos, selección de pitches y otros factores no medidos. Su mejora predictiva no identifica por sí sola el efecto físico de la densidad del aire. Faltan estadio/Harp, metros y atmósfera para park holdout y simulación específica; xRunValue oficial para RMSE de carreras; nueva muestra independiente y prueba con coaches. F10 fortalece la evidencia de arsenal/ambiente, pero no completa esos requisitos. No se abrió nuevamente 2026.

## Cómo probar y reproducir

Desde la raíz, con datos privados y artefactos F8/F9 restaurados:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\run_phase10.ps1 check
.\run_phase10.ps1 simulate -Target 'Extreme Altitude' -OutputFile output/f10-ejemplo-nuevo.json
.\run_phase10.ps1 smoke -Name f10-smoke-nuevo
.\run_phase10.ps1 train -Name f10-reproduccion
```

El wrapper utiliza `.venv`. Cada entrenamiento requiere nombre nuevo; el simulador no sobrescribe salidas existentes. `docs/F10_INPUT_EXAMPLE.json` es sintético; el pitcher es opcional y, si falta, se indica prior de grupo. Para score se necesitan features físicas y categoría de origen; ubicación/conteo/mano del bateador son opcionales para el diagnóstico de contacto.

Pruebas prácticas: origen=destino devuelve cero; velocidad negativa devuelve `invalid_input`; destino no reconocido devuelve `unsupported`; quitar outcomes no altera el resultado; cambiar un archivo de modelo provoca rechazo por hashes. Los rangos de soporte son deliberadamente conservadores, incluso en sus extremos.

## Verificación y archivos entregados

Pasaron **138 pruebas unitarias** (13 nuevas), **14 controles internos** y **14 comprobaciones de auditoría independiente**. Se recalcularon features, métricas y seis intervalos, se verificaron IDs de ajuste/calibración, se reprodujeron escenarios sin outcomes y se comprobaron los hashes F8/F9 y del registro de acceso al test.

- `config/phase10.json` y `docs/FASE_10_ESTRATEGIA.md`: protocolo y decisiones.
- `experiments/phase10_features.py`: auditoría y referencias.
- `experiments/phase10_models.py`: modelos de eventos y movimiento.
- `experiments/phase10.py`: entrenamiento/evaluación y escenarios.
- `experiments/phase10_simulator.py`: inferencia experimental.
- `experiments/check_phase10.py`: verificación independiente.
- `docs/F10_RESULTS.json`, `docs/F10_AUDIT.json`, `docs/F10_VALIDATION.json`: evidencia versionable.
- `artifacts/modeling/f10-full/F10`: artefactos locales privados, excluidos de Git.

## Fundamento bibliográfico

La separación entre condiciones del aire y movimiento se apoya en [Alan Nathan](https://baseball.physics.illinois.edu/Denver.html). La evidencia observacional de [SABR](https://sabr.org/journal/article/high-altitude-offense-an-empirical-examination-of-the-relationship-between-runs-scored-and-stadium-elevation/) motiva estudiar el ambiente, pero no valida el delta de nuestro simulador. La regularización por grupos se inspira metodológicamente en [Deshpande y Wyner](https://arxiv.org/abs/1704.00823); aquí se implementa suavizado explícito de momentos, no inferencia bayesiana de framing. Las referencias complementarias y sus límites figuran en la estrategia F10.
