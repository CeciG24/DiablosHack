# Holdout por categoría de altitud (leave-one-category-out)

Fecha: 18 de octubre de 2026. Rama: `fase-9`. Experimento: `ah-full`. Datos: run `e9e0b1114dc68eb2`, sólo 2024–2025.

## Qué es (y qué no es)

Es una prueba de **transferencia entre ambientes**: se entrena un modelo de movimiento físico (IVB y HB) con dos categorías de altitud y se evalúa en la tercera, que el modelo nunca vio. Las categorías son los buckets `altitude_category` del dataset (`No`, `Medium`, `Extreme Altitude`).

**No es un park holdout.** El dataset no tiene `stadium_id`; una categoría agrupa varios parques. Tampoco identifica el Harp Helú ni estima su efecto causal. Es lo más cercano a un holdout por estadio que permiten los datos, y así debe nombrarse en el informe técnico.

## Diseño

| Elemento | Decisión |
|---|---|
| Folds | Tres: se retiene `Extreme`, `Medium` o `No Altitude`, uno por vez. `Extreme` (entrenar con `No`+`Medium`) es el resultado titular. |
| Ajuste | 2024, sólo las dos categorías de entrenamiento. Nunca 2025 ni 2026. |
| Evaluación | 2025, categoría retenida («shifted»). Como referencia, 2025 de las categorías de entrenamiento («indomain»). |
| Targets | `induced_vert_break` y `horz_break`, en pulgadas. |
| Modelos | `control`: sólo física, sin altitud. `ordinal`: añade `altitude_ord` (No=0, Medium=1, Extreme=2). `ordinal_linear`: igual pero con `linear_tree` de LightGBM. |
| Presupuesto | Idéntico a F10: 31 hojas, 200 rondas, sin selección sobre evaluación. |
| Incertidumbre | Bootstrap pareado por partido (2,000 remuestreos), error cuadrático, IC Bonferroni para 12 comparaciones (99.58%). |
| Cohorte | `eligible_pitching_default`, igual que F10. Ningún partido cruza categorías (verificado). |

El código está en `experiments/altitude_holdout.py` y la configuración en `config/altitude_holdout.json`. Las predicciones y modelos por fold se guardan en `artifacts/modeling/ah-full/AH/` (no versionado). El resumen versionable es `docs/ALTITUDE_HOLDOUT_RESULTS.json`.

## Resultados

RMSE en pulgadas sobre la categoría retenida de 2025. «Indomain» es el RMSE del mismo modelo sobre 2025 de las categorías con las que se entrenó.

### induced_vert_break

| Retenida | N | Control | Ordinal | Ordinal lineal | Control indomain |
|---|---:|---:|---:|---:|---:|
| Extreme (entrena No+Medium) | 71,755 | 2.8243 | **2.0073** | 1.9990 | 2.3446 |
| Medium (entrena No+Extreme) | 65,116 | 2.2319 | **1.9993** | 2.0058 | 2.5233 |
| No (entrena Medium+Extreme) | 115,098 | 3.3946 | **3.2269** | 3.2521 | 1.9192 |

### horz_break

| Retenida | N | Control | Ordinal | Ordinal lineal | Control indomain |
|---|---:|---:|---:|---:|---:|
| Extreme | 71,755 | 2.6109 | **1.8841** | 1.8840 | 2.3958 |
| Medium | 65,116 | 2.1138 | **1.9903** | 1.9826 | 2.5362 |
| No | 115,098 | 3.6358 | **3.4511** | 3.4226 | 1.8291 |

### Sesgo del control (predicho menos observado, en pulgadas; HB orientado por mano)

| Retenida | IVB | HB |
|---|---:|---:|
| No Altitude | **−1.78** | **−1.48** |
| Medium Altitude | +0.84 | +0.63 |
| Extreme Altitude | **+1.59** | **+1.09** |

Sin ninguna información de altitud, el modelo físico predice **más** movimiento del observado en `Extreme` y **menos** en `No`, con un sesgo que crece monótonamente con la altitud. Dentro de su dominio el sesgo es casi cero (como máximo 0.15 pulgadas en valor absoluto). Es consistente con la hipótesis H1 del reto (menos densidad, menos movimiento inducido), aunque no la demuestra por sí solo (ver limitaciones).

### Contrastes frente al control (MSE, IC Bonferroni 99.58%)

| Retenida | Target | Ordinal vs control | Ordinal lineal vs control |
|---|---|---:|---:|
| Extreme | IVB | −49.5% [−4.29, −3.62] | −49.9% [−4.31, −3.65] |
| Extreme | HB | −47.9% [−3.52, −3.01] | −47.9% [−3.53, −3.01] |
| Medium | IVB | −19.8% [−1.31, −0.67] | −19.2% [−1.30, −0.63] |
| Medium | HB | −11.4% [−0.78, −0.26] | −12.0% [−0.80, −0.29] |
| No | IVB | −9.6% [−1.19, −1.04] | −8.2% [−1.08, −0.82] |
| No | HB | −9.9% [−1.40, −1.23] | −11.4% [−1.61, −1.40] |

Los intervalos son del delta de MSE (candidato menos control); los 12 quedan bajo cero y superan el umbral predeclarado de 1%. En RMSE, la mejora en `Extreme` es de 28.9% (IVB) y 27.8% (HB).

### Sesgo por tipo de lanzamiento (`Extreme` retenida, IVB, pulgadas)

| Tipo | N | IVB observado | Sesgo control | Sesgo ordinal |
|---|---:|---:|---:|---:|
| Four-Seam | 24,990 | +13.00 | +2.89 | +1.04 |
| Sinker | 12,980 | +7.76 | +1.74 | +0.57 |
| Cutter | 4,102 | +7.57 | +1.97 | +1.17 |
| Changeup | 7,387 | +4.85 | +1.22 | +0.36 |
| Slider | 15,802 | +2.06 | +0.46 | +0.36 |
| Curveball | 5,213 | −6.28 | −1.15 | −0.50 |

El error del control es mayor en las rectas, que dependen más del efecto Magnus. Los tipos con menos de 200 lanzamientos (`OneSeamFastBall`, `Other`, `TwoSeamFastBall`) están marcados como provisionales en el JSON y no deben interpretarse.

## Limitaciones

1. **El feature ordinal no extrapola.** Con `Extreme` o `No` retenidas, el modelo ve sólo dos valores de `altitude_ord` y los árboles tratan el tercero como el valor extremo más cercano. La ganancia se debe a que `Medium` se parece más a `Extreme` que `No`, no a una pendiente de altitud aprendida. `ordinal_linear` no extrapola mejor (resultados prácticamente idénticos), y queda un sesgo residual de +0.60 (IVB) y +0.31 (HB) en `Extreme`. Sólo el fold `Medium` es una interpolación genuina.
2. **Categoría no es estadio.** La mejora puede reflejar también diferencias de parque, calibración del Trackman, selección de pitchers y equipos, no sólo densidad del aire. No se controla por esos factores.
3. **No es el Harp Helú.** `Extreme Altitude` agrupa todos los parques de ese bucket; no hay metros, clima ni identificación del parque.
4. **Datos reutilizados.** 2025 ya informó decisiones de fases anteriores; los intervalos son de modelos fijos, no incluyen incertidumbre por reentrenamiento y no eliminan la dependencia entre partidos del mismo pitcher.
5. **Sólo movimiento.** No se evaluó el efecto sobre eventos, Stuff+ ni carreras.

## Cómo reproducir

Desde la raíz del repositorio, con los datos locales (el `.venv` y `data/` no están en Git):

```bash
python -m unittest tests.test_altitude_holdout -v
python -m experiments.altitude_holdout --name ah-smoke --smoke --data-run data/runs/<id>
python -m experiments.altitude_holdout --name ah-reproduccion --data-run data/runs/<id>
```

Cada corrida exige un nombre nuevo. Si `--data-run` se omite, usa `data/CURRENT`.

## Verificación

Pasaron 8 pruebas unitarias nuevas (`tests/test_altitude_holdout.py`): la categoría retenida nunca entra al ajuste, el ajuste se limita a 2024, se rechazan 2026, categorías desconocidas y partidos que cruzan categorías, los modelos son deterministas y el control no puede usar altitud. La corrida completa verificó que no hay fuga de categoría y que sólo se usaron 2024–2025.
