# Pitch Value+ con arsenal (F11)

## Que cambia

Se agrega un modelo combinado nuevo, sin editar la release congelada F8 ni sus
scores. La etiqueta de producto es **Pitch Value+ - experimental**.
Antes se mostraba como "Stuff+ final". Se cambia el nombre porque incluye
ubicacion y conteo; los campos `stuff_final`, modelos y escalas no cambian.

- F8 `stuff`: fisica pura, permanece como diagnostico.
- F8 `pitching`: fisica, ubicacion y contexto, sin arsenal; permanece aprobado.
- F11: fisica + ubicacion + arsenal historico regularizado + conteo/lado.

F9/F10 no bastaban para este requisito: sus modelos de eventos con arsenal
excluyen `plate_loc_height` y `plate_loc_side`. F11 incorpora explicitamente
`PITCHING + REGULARIZED`: 16 entradas del pitch y 54 variables de arsenal.
No hay IDs, outcomes, anio ni categoria de altitud como predictores.

El arsenal compara el pitch con ocho familias historicas: diferencias de
velocidad, IVB, HB y liberacion, uso, confiabilidad y dispersion. Se obtiene de
la referencia fija de 2024 ya verificada de F10. No se completa con lanzamientos
de 2025/2026. Sin historia propia, se informa `group_prior_only` y `history_n=0`:
el score usa un prior del grupo, no un arsenal individual inventado.

## Entrenamiento y evidencia

Configuracion fija en `config/final_score.json`, guardada antes de entrenar:

| Papel | Temporada/particion | Pitches | Juegos |
|---|---|---:|---:|
| Ajuste | 2025/development | 134420 | 447 |
| Temperatura y escala | 2025/calibration | 59367 | 197 |
| Revision | 2025/phase_review | 58182 | 192 |

LightGBM 4.6.0, 200 rondas, semilla 20260929, sin busqueda en review. Se comparan
dos modelos ajustados en los mismos registros y con el mismo presupuesto:

| Modelo | Log loss (menor es mejor) | Brier multiclase |
|---|---:|---:|
| Sin arsenal | 1.0303224471 | 0.5330663688 |
| Con arsenal | 1.0308166407 | 0.5331192834 |

Diferencia de log loss: +0.00049419; IC bootstrap por partido del 95%:
[-0.00067250, +0.00161973], 500 remuestreos. Resultado **no concluyente**:
no demuestra una mejora global, y no se promueve sobre F8.
Los arboles si usan variables de arsenal (ganancia no nula).

La revision de 2025 ya se utilizo en fases previas y el test de F8 ya se expuso.
Este desarrollo es exploratorio posterior; no es confirmacion independiente.
El entrenamiento no lee ni evalua 2026. Los hashes de F8 y del registro de
exposicion al test permanecen iguales. La app puede hacer inferencia sobre los
pitches 2026 que ya visualizaba, sin ajustar ni seleccionar el modelo con ellos.

## Score y limites

El modelo predice seis clases mutuamente excluyentes por pitch: bola, strike
cantado, swing en blanco, foul, bola en juego y golpe al bateador.
Whiff NO incluye foul.

```text
u = P(whiff) + P(called_strike) - 0.5 * P(ball) - P(hit_by_pitch)
Pitch Value+ = 100 + 10 * (u - mu_calibracion) / sigma_calibracion
```

La referencia es fija: 59367 pitches de calibracion 2025, con su contexto
observado. No se reemplazan conteo, bateador ni ubicacion por promedios.
Se comprueba media 100 y desviacion 10 sobre esa referencia. No es un
porcentaje, no se renormaliza por pitcher ni se resta de F8/F10.

**Esto agrega el componente arsenal al modelo combinado, no implementa todos
los targets del brief.** Chase, contacto y rodados siguen siendo cabezas
auxiliares F8, etiquetadas aparte; no entran a este score ni se presentan como
probabilidades de F11. No se fabrican xRunValue, barrels ni out dentro de PA.
El score es utilidad de eventos provisional, no carreras esperadas ni Out+.

## API y frontend

- `POST /api/v1/final-score`, cuerpo `{"records": [pitch]}`. Requiere las
  entradas completas de `pitching`; `pitcher_anon_id` recupera la historia.
- Respuesta por registro: `score`, seis `probabilities`, `score_version`,
  `model_id`, `history_status`, `history_n`, `warnings`, `experimental`.
- Entradas invalidas: score nulo y motivo; contexto incompleto via HTTP: 422.
  Artefacto ausente/no verificado: 503. Nunca se sustituye por un score F8.
- Los bundles incluyen `stuff_final`, `final_history_n` y
  `final_history_status` por pitch, cacheados sin alterar las columnas F8.
- Analisis de lanzamientos muestra la columna ordenable y el detalle en el
  modal, separado de los indicadores/probabilidades F8. Los demas modulos
  conservan sus scores F8/F10 anteriores.
- En esa vista, Pitch Value+ encabeza el resumen y el modal; la tabla lo
  destaca como primera columna de score y ordena inicialmente de mayor a menor.
  La media usa solo scores finales finitos y muestra su cobertura y los casos
  con prior de grupo. Es prioridad visual para exploracion, no promocion
  estadistica del modelo experimental. Los scores F8 quedan como diagnosticos.
- El modal usa una sola lista de ocho targets: whiff, chase, strike cantado,
  contacto debil, rodado, contacto duro, xRunValue y out dentro de PA. Whiff y
  strike cantado toman una unica estimacion del modelo final cuando responde;
  si no esta disponible, se identifica la referencia base. Los otros cuatro
  targets implementados son auxiliares sin arsenal, con su procedencia y
  denominador propios. xRunValue y out dentro de PA quedan como no disponibles.
  No se promedian modelos ni se cambia la formula del score al unificar la UI.
  Bola, foul, in_play y golpe siguen en la respuesta del modelo, sin otro bloque
  principal de probabilidades que duplique whiff o strike cantado.

## Reproducir

Desde la raiz, con las dependencias locales y artefactos privados F10:

```sh
python -m experiments.final_score --output artifacts/modeling/final-score-v1
python -m unittest tests.test_final_score tests.test_backend
```

El directorio de salida debe ser nuevo: no se sobrescriben experimentos.
Incluye modelos base/combinado, temperaturas, referencia de arsenal, escala,
ganancias, calibracion, resumen y manifiesto SHA256. Los artefactos privados
permanecen excluidos de Git. Para otra salida, fijar `DIABLOS_FINAL_SCORE` antes
de iniciar el backend. Si faltan, F8 sigue funcionando y el score final queda
no disponible.
