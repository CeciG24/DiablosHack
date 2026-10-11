# Fase 5: arsenal con historia real

Cierre: 11 de octubre de 2026.

**Implementación: verified. Decisión científica: `retain_reference` en protocolo C.**

## Qué se implementó

Se construyó una referencia fija de 2024 para evaluar si el repertorio histórico aporta información a Pitching. La fase entrena modelos propios de protocolo C, calibra sus probabilidades y compara el candidato con un control sobre los mismos pitches. No reemplaza el modelo aprobado del protocolo A: ambos protocolos tienen entrenamiento distinto.

- `modeling/arsenal.py`: referencia histórica, cinco variables de arsenal, modelo C y predicción de la política guardada.
- `modeling/phase5.py`: verificación de dependencias F0–F4, ejecución reproducible, cobertura, calibración, comparación y fallback.
- `scripts/check_phase5.py`: reconstruye la referencia desde los datos fijados y reproduce probabilidades, temperaturas, métricas y decisiones en otro proceso.
- `tests/modeling/test_arsenal.py`: once pruebas adicionales de antigüedad, muestras mínimas, empates, separación de ajuste, invariancia y rutas.
- CLI, lanzador PowerShell y contrato actualizados para F5. Todas las ejecuciones usan `.venv`.

## Por qué se implementó así

La referencia existente de 2026 combina 2024 y 2025. Reutilizarla habría cambiado el soporte histórico del experimento. F5 reconstruye y guarda una referencia exclusivamente de 2024; nunca rellena 2024 usando el futuro. Solo se leen campos físicos, tipo y pitcher del historial, sin outcomes. Se conserva el historial completo incluso en la muestra rápida.

Se elige Four-Seam o Sinker con al menos 30 observaciones completas de velocidad, IVB, HB y release. Gana el tipo más frecuente; el empate se resuelve alfabéticamente. Las medias y los diferenciales siguen el contrato de datos. La frecuencia histórica usa todos los pitches del pitcher en 2024; un tipo nuevo tiene frecuencia cero cuando existe historial. Las referencias insuficientes permanecen ausentes.

Las cinco variables añadidas son uso histórico del tipo, diferencia de velocidad, diferencia de IVB, diferencia de HB y distancia entre coordenadas de release. La distancia de release **no es tunneling**. El indicador de referencia controla la ruta; no se añade como predictor porque es constante en la cohorte pareada.

LightGBM 4.6.0, CPU, cuatro hilos, semilla 20260929. Una configuración predeclarada: 31 hojas, mínimo 200 observaciones por hoja, learning rate 0.05, L2=5 y 200 rondas (30 en smoke). No hay búsqueda ni parada temprana sobre calibración o revisión. Los vocabularios categóricos se aprenden únicamente en ajuste.

| Modelo | Datos de ajuste | Variables |
|---|---|---|
| Control C | Desarrollo 2025 con referencia | Pitching sin ambiente |
| Arsenal C | Exactamente los mismos pitches del control | Pitching sin ambiente más cinco variables históricas |
| Fallback C | Todo desarrollo 2025 elegible | Pitching sin ambiente |

Cada temperatura se ajusta solo en calibración 2025; revisión elige temperatura o identidad sin reajustar. Se conserva identidad si la temperatura aumenta log loss. El control y arsenal se calibran sobre la misma población con referencia.

La política control usa control con historia y fallback sin historia. La candidata cambia únicamente la rama con historia. Solo se publica esa rama candidata si satisface reducción relativa de log loss de al menos 1% y límite superior del intervalo pareado menor que cero. El bootstrap remuestrea partidos completos, 500 veces, con pérdida ponderada por pitch. La política completa se evalúa adicionalmente sobre todos los pitches elegibles, incluyendo el fallback.

## Datos y cobertura

Datos fijados: `c1c8ba48818dc878`. Referencia `fixed_2024_9709e7eacaa24cc9`: 243,254 pitches de 2024. La cohorte mantiene la elegibilidad común de las familias F0/F3, restringida a 2025; conserva también el filtro previo de disponibilidad ambiental.

| Partición 2025 | Pitches | Con referencia | Cobertura | Pitchers |
|---|---:|---:|---:|---:|
| calibration | 59,367 | 29,140 | 49.08% | 479 |
| development | 134,420 | 70,378 | 52.36% | 540 |
| phase_review | 58,182 | 30,443 | 52.32% | 492 |

Las particiones se asignan por hash de partido, no por cronología dentro de 2025. Los mismos pitchers pueden aparecer en distintas particiones. Este es un escenario de adaptación con historia, no un pitcher holdout frío. En el modo frío se fuerza fallback aunque exista una referencia almacenada.

Cobertura en revisión por categoría de altura:

| Categoría | Pitches | Con referencia | Cobertura |
|---|---:|---:|---:|
| Extreme Altitude | 15,400 | 8,598 | 55.83% |
| Medium Altitude | 14,922 | 7,793 | 52.22% |
| No Altitude | 27,860 | 14,052 | 50.44% |

Se guardan también CSV por tipo de lanzamiento, pitcher y estado de historia. Altura es metadato de cobertura; no participa en ninguna predicción F5 ni identifica un estadio.

## Métricas y decisión

| Política, revisión completa | n | Log loss | Brier multiclase |
|---|---:|---:|---:|
| full_base | 58,182 | 1.03032245 | 0.53306637 |
| control_policy | 58,182 | 1.03372214 | 0.53450581 |
| candidate_policy | 58,182 | 1.03280858 | 0.53415569 |
| selected_policy | 58,182 | 1.03372214 | 0.53450581 |

| Comparación | Pitches | Partidos | Mejora relativa | IC95% delta candidato − control |
|---|---:|---:|---:|---|
| Arsenal contra control, con historia | 30,443 | 191 | 0.1666% | [-0.00330898, -0.00018329] |
| Políticas completas con fallback | 58,182 | 192 | 0.0884% | [-0.00167186, -0.00013869] |

Decisión: **retain_reference**. Se conserva el modelo sin arsenal para la rama con historia; el candidato queda como análisis del repertorio, sin anunciar una mejora validada.

El modelo `full_base` obtiene menor pérdida que ambas políticas de dos ramas en esta revisión, pero se ajustó con más pitches. Esa comparación descriptiva no aísla el aporte de arsenal. La ablación válida es arsenal contra control sobre las mismas filas, y la referencia productiva del protocolo A permanece aprobada. No se seleccionó otra política a posteriori usando este resultado.

Calibración de cada candidato:

| Modelo | Temperatura | Ruta elegida | Log loss bruto revisión | Log loss con temperatura |
|---|---:|---|---:|---:|
| fallback | 0.982410 | temperature | 1.03053687 | 1.03032245 |
| control | 1.002220 | temperature | 1.04821319 | 1.04821256 |
| arsenal | 1.002619 | identity | 1.04646659 | 1.04646930 |

## Pruebas ejecutadas

- 86 pruebas unitarias aprobadas, incluidas las 11 nuevas de arsenal.
- El primer intento aislado encontró un bloqueo de permisos en la carpeta temporal de Windows; la repetición autorizada dentro del mismo `.venv` aprobó la suite completa.
- Smoke final: 13 controles, 28 hashes y 8,690 filas de predicción. La muestra no cumple los mínimos de clases para arsenal y verifica la ruta de muestra insuficiente/fallback.
- Completa: 22 controles, 48 hashes y 117,549 filas de predicción. Duración de entrenamiento y verificación interna: 3.18 minutos.
- Modelos reentrenados de forma determinista y recargados sin diferencias. El verificador independiente reconstruyó la referencia, reajustó las temperaturas únicamente en calibración y reprodujo las probabilidades exactamente: diferencia máxima 0.0.
- Se reprodujeron las ocho métricas de política y las comparaciones bootstrap; la API de política se comprobó sin outcomes y con cold-start forzado.
- Contrato/configuración coherentes. Ninguna etiqueta de 2026 fue utilizada.

La primera corrida smoke de desarrollo queda preservada en `f5-smoke-check`; la evidencia final usa `f5-smoke-final`, ejecutada después de añadir la recarga de la política. Los manifiestos conservan los hashes originales y la configuración `in_progress` del inicio; el estado final está en el manifiesto, y el contrato vigente se marca verified al cerrar.

## Cómo probarlo

Desde la raíz del proyecto:

```powershell
.\run_modeling.ps1 tests
.\run_modeling.ps1 contract
.\.venv\Scripts\python.exe scripts/check_phase5.py f5-smoke-final
.\.venv\Scripts\python.exe scripts/check_phase5.py f5-full-check
```

Para nuevas ejecuciones, con identificadores automáticos para no sobrescribir artefactos:

```powershell
.\run_modeling.ps1 f5-smoke
.\run_modeling.ps1 f5
```

Para predecir desde Python del entorno virtual:

```python
from modeling.arsenal import predict_policy
predicciones = predict_policy('artifacts/modeling/f5-full-check/F5', entradas)
sin_historia = predict_policy('artifacts/modeling/f5-full-check/F5', entradas, cold_start=True)
```

`entradas` es un DataFrame con `pitch_uid`, `year`, `pitcher_anon_id` y las variables de `modeling.datasets.PITCHING`. No requiere `y_event` ni otros outcomes. Acepta entradas observables de 2025/2026, pero no abre datasets ni labels de test. Conserva el orden y devuelve probabilidades, ruta y advertencia de historia insuficiente. Este helper requiere entradas válidas completas; el manejo por fila inválida y la API de release corresponden a F8.

## Artefactos

- `artifacts/modeling/f5-full-check/F5/`: manifiesto, referencia_2024, cohortes, modelos, calibradores, curvas SVG, predicciones, coberturas, métricas, política y decisión.
- `artifacts/modeling/f5-smoke-final/F5/`: evidencia rápida final.
- `docs/F5_FULL_VALIDATION.json`, `docs/F5_SMOKE_VALIDATION.json`, `docs/F5_VALIDATION.json`: evidencia agregada para versionar.
- Datos, IDs por pitch, binarios y modelos permanecen locales y excluidos de Git.

## Límites y siguiente fase

La revisión 2025 ya se usa para decisiones de fases y no es una prueba final independiente. La evidencia de C no demuestra superioridad frente a A, porque entrenan en poblaciones y años diferentes. La ausencia de historia afecta a casi la mitad de los pitches y debe acompañar cualquier interpretación del resultado. No hay xRunValue, scores, efecto causal de arsenal ni simulación física. La distancia de release no es túnel. No se atribuye Extreme Altitude a Harp Helú.

F6 queda habilitada para la ablación ambiental solicitada posteriormente. F6–F8 no se ejecutaron; 2026 permanece sellado.
