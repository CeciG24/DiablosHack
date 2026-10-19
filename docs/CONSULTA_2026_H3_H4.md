# Consulta exploratoria de 2026: H3 y H4

## Protocolo de acceso

- Solicitud explicita del usuario: "consulta registros del 2026".
- Protocolo: `exploratory_2026_H3_H4_20261019`.
- Registro previo a la consulta: `2026-10-19T04:01:22Z`.
- Version de datos: `e9e0b1114dc68eb2`, indicada en `data/CURRENT`.
- Alcance: cobertura, calidad y agregados descriptivos de 2026 para evaluar
  la viabilidad de H3 (rodados y dano ofensivo) y H4 (rpm y movimiento).
- Acceso SQL en modo de solo lectura, con filtro explicito `year = 2026`.
- No se entrenan modelos, seleccionan variables ni ajustan hiperparametros,
  calibraciones, reglas de limpieza o pesos del score a partir de 2026.
- No se calcula una nueva evaluacion de F8/F10 ni se modifica su release.
- El test ya fue expuesto en F8 el `2026-10-15T06:12:13.395546+00:00`.
  Esta consulta constituye exposicion exploratoria adicional autorizada:
  no es una validacion independiente de nuevas decisiones sobre H3/H4.
- Este informe registra un acceso separado; no se modifica ni se presenta
  como reproduccion el registro original de evaluacion final de F8.

## Integridad previa

SHA-256 de archivos que deben permanecer sin cambios:

| Archivo | SHA-256 |
|---|---|
| `artifacts/modeling/test_access.jsonl` | `df8511114ec6d36bed2b7b5b1d351df49774283b1e5c0e5db725e94d52545412` |
| `artifacts/modeling/test_exposure.json` | `96f8321757af99d59ecd20fd60b86ac9bc0c9c771cfa36fb6b5368696f5e0b25` |
| `artifacts/modeling/releases/f8-release-20261013/release_lock.json` | `202abc57c2a5da297f218750f4f5ecf95633d60e26828fa1f648eac96b92e684` |
| `artifacts/modeling/f10-full/F10/manifest.json` | `2d2c6a30b7c31c59942d3bb581c3911bf54a1c4d19e8131346d9933a7295ff84` |

## Resultados

Consulta ejecutada: `2026-10-19T04:02:19.562510+00:00`.
Fuente: `data/runs/e9e0b1114dc68eb2/diablos.duckdb`.

### Cobertura de 2026

| Medida | Registros |
|---|---:|
| Lanzamientos | 135,604 |
| Partidos distintos | 455 |
| Pitchers distintos | 550 |
| Bolas en juego canonicas (`y_event = 'in_play'`) | 24,500 |
| Etiquetas validas rodado/no rodado | 24,033 |
| Rodados positivos | 11,318 |
| Etiquetas validas HR/no HR | 24,499 |
| Jonrones positivos | 922 |
| Etiquetas validas hit/no hit | 24,499 |
| Hits positivos | 8,884 |
| Velocidad y angulo de salida disponibles, cada variable | 23,814 |
| Fisicas completas segun contrato (`eligible_physical_complete`) | 134,487 |
| Lanzamientos sin categoria de altitud | 2,073 |
| Conflictos simultaneos HR y rodado positivos | 0 |

Las etiquetas canonicas conservan nulos y reglas de cuarentena existentes.
No se imputaron resultados ni se reinterpretaron nulos como ceros.

### Agregados descriptivos por categoria de altitud

| Categoria | Pitches | BIP | HR | Etiquetas HR | HR/BIP etiquetado | GB/BIP etiquetado | Contacto duro/BIP medido |
|---|---:|---:|---:|---:|---:|---:|---:|
| No Altitude | 61,678 | 11,010 | 357 | 11,010 | 3.243% | 45.915% | 23.140% |
| Medium Altitude | 27,925 | 5,065 | 183 | 5,064 | 3.614% | 46.958% | 28.230% |
| Extreme Altitude | 43,928 | 8,069 | 367 | 8,069 | 4.548% | 48.571% | 28.060% |
| Categoria ausente | 2,073 | 356 | 15 | 356 | 4.213% | 51.989% | 25.641% |

Cada porcentaje usa su propio denominador no nulo: `avg(y_home_run_bip)`,
`avg(y_groundball_bip)` o `avg(y_hard_contact_bip)`, multiplicado por 100.
Contacto duro corresponde al umbral existente de velocidad de salida
de 95 mph, no a probabilidad de jonron.

El agregado HR/BIP es mayor en Extreme que en No Altitude. Esto no demuestra
que el GB% historico del pitcher modere el efecto de la altitud ni identifica
un efecto causal de la densidad. Tampoco permite interpretar la categoria
Extreme como un estadio concreto.

### Carreras y outs observados

`runs_scored` y `outs_on_play` tienen valor en los 135,604 pitches:

- Suma de `runs_scored`: 5,050; 3,847 pitches con valor positivo; rango 0 a 4.
- Suma de `outs_on_play`: 22,730; rango 0 a 3.
- El diccionario define ambos sobre el pitch y jugadas relacionadas antes
  del siguiente pitch. No son una etiqueta de run value por lanzamiento ni
  garantizan atribucion oficial de carreras limpias al pitcher.
- Faltan ocupacion de bases, orden/PA fiable y estadio identificado para
  reconstruir run expectancy estandar o una neutralizacion completa.

### Historia utilizable para H3

Se unieron pitchers de 2026 con conteos no nulos de `y_groundball_bip`
en 2024-2025, sin incorporar resultados de 2026 a esa historia.

| Medida | Pitchers |
|---|---:|
| Con alguna historia GB etiquetada en 2024-2025 | 301 |
| Con al menos 30 BIP historicos etiquetados | 271 |
| Sin historia GB utilizable en 2024-2025 | 249 |
| En al menos dos categorias de altitud durante 2026 | 390 |
| En las tres categorias durante 2026 | 198 |

La mediana de BIP etiquetados de 2026 por pitcher es 35.
El corte de 30 es descriptivo de cobertura, no un umbral elegido para
optimizar un modelo. Pitchers sin historia requieren prior o una politica
explicita de exclusiones; no se debe usar su GB% del mismo periodo objetivo
como si fuera una caracteristica historica conocida.

### Variables para H4

| Variable o conjunto | Pitches de 2026 |
|---|---:|
| `spin_rate` no nulo | 135,603 |
| `spin_axis` no nulo | 134,904 |
| IVB no nulo | 134,902 |
| HB no nulo | 134,904 |
| RPM, IVB y HB simultaneamente no nulos | 134,901 |
| `ax0`, `ay0`, `az0` disponibles, cada variable | 135,604 |
| Velocidades y aceleraciones 3D completas y spin positivo | 135,603 |
| VAA observado (`vert_appr_angle`) disponible | 135,604 |

No hay columnas de spin efficiency, active spin ni gyro identificadas en
el esquema de `pitches`. Las aceleraciones y el eje reportado no equivalen
por si solos a una medicion inequivoca de eficiencia de giro.
El VAA observado si existe; no debe confundirse con una proyeccion de VAA
al cambiar de ambiente.

## Interpretacion y limites

- H3: existe cobertura para investigar GB% historico por altitud frente a
  HR, hits y carreras observadas. Los agregados anteriores no prueban H3.
- H4: existe cobertura para comparar, con filas y controles equivalentes,
  modelos con/sin movimiento observado, manteniendo rpm y eje comunes.
  Esta consulta no ejecuta esa comparacion ni valida spin efficiency.
- 2026 no incorpora mediciones de densidad, clima o identificacion del Harp
  suficientes para convertir categorias en efectos fisicos del estadio.
- El periodo exacto cubierto por estos registros no queda establecido por
  la columna `year`; no se afirma que sean la temporada 2026 completa ni
  que coincidan con el corte temporal de `hipotesis.md`.
- Si los hallazgos de 2026 influyen en un nuevo modelo, su desarrollo debe
  declararse posterior a exposicion del test. La confirmacion independiente
  requiere datos no utilizados para esas decisiones.

## Consultas de referencia

Cobertura y tasas canonicas, sin cargar ni entrenar modelos:

```sql
SELECT altitude_category,
       count(*) AS n_pitches,
       count(*) FILTER (WHERE y_event = 'in_play') AS n_bip,
       count(y_home_run_bip) AS n_hr_labels,
       sum(y_home_run_bip) AS n_hr,
       100.0 * avg(y_home_run_bip) AS hr_pct,
       100.0 * avg(y_groundball_bip) AS gb_pct,
       100.0 * avg(y_hard_contact_bip) AS hard_contact_pct
FROM model_base
WHERE year = 2026
GROUP BY altitude_category;
```

El unico uso de otras temporadas durante esta consulta es el conteo
descriptivo de historia GB de 2024-2025 unido a pitchers de 2026.

## Integridad posterior

Verificados los cuatro SHA-256 previos: permanecen sin cambios.
El SHA-256 de `diablos.duckdb` coincide con el del manifest de preparacion.
No se modificaron los datos ni se escribieron artefactos de modelos.
El unico archivo creado por esta consulta es este informe.
