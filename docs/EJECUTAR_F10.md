# Ejecutar Fase 10 (macOS)

Guía operativa de F10: Stuff v3 con features relativas al arsenal del pitcher, evaluado
con los targets propios de Stuff. Es desarrollo posterior al release y con el test 2026
ya expuesto: el código vive en `postrelease/`, no consulta 2026 y no modifica el release.

> Reglas que no se pueden saltar: `dataset.load` rechaza `test` fuera de F8; el manifiesto
> declara la exposición previa; cada corrida crea `artifacts/modeling/<experiment_id>/` nuevo
> (un ID existente se rechaza). La decisión no reabre ni modifica el release F8.

## Qué prueba

Tres variantes por cabeza, mismo protocolo A y misma cohorte común F0:

| Variante | Matriz | Referencia del pitcher |
|---|---|---|
| `base` | 11 físicas (F2) | ninguna |
| `refA` | base + 4 relativas (Δvelo, ΔIVB, ΔHB, distancia de release) | misma temporada, solo covariables físicas (**transductiva**) |
| `refB` | misma matriz que refA | entrenamiento: su propia temporada 2024; evaluación: **año previo** (desplegable) |

Referencia = Four-Seam o Sinker más frecuente con al menos 30 lanzamientos por pitcher-año
(`F10.reference_min_fastballs`). Nunca lee outcomes.

Cabezas binarias (contra prevalencia suavizada de entrenamiento): `whiff_given_swing`,
`groundball_bip`, `hard_contact_bip`. Modelos de evento `Stuff+conteo` (con y sin relativas)
contra B1, para medir el valor físico incremental. `chase` ya no se exige a Stuff.

Regla de decisión predeclarada (`F10.ablation_rule`): `adopt_refB_deployable` si refB mejora
a base en whiff|swing con IC95% bajo cero; `refA_diagnostic_only` si solo mejora refA;
`retain_base` en otro caso. El índice (`P(whiff|swing)`, escala fija sobre calibration 2025,
global y por tipo) se publica como diagnóstico provisional, no como valor de carreras.

## Ejecución

```bash
.venv/bin/python scripts/check_modeling_contract.py
.venv/bin/python -m unittest tests.modeling.test_stuff_v3 -v
.venv/bin/python -m postrelease.phase10 --experiment-id f10-smoke-check --smoke   # sin validez científica
.venv/bin/python -m postrelease.phase10 --experiment-id f10-stuff-v3
.venv/bin/python scripts/check_phase10.py f10-stuff-v3
.venv/bin/python scripts/generar_reporte_f10.py f10-stuff-v3
```

`check_phase10.py` recalcula métricas desde las predicciones, re-ejecuta los bootstrap
pareados, verifica argmin de selección, reconstruye las referencias desde los datos
fijados y re-predice una muestra con los modelos guardados. Estado esperado: `verified`.

Evidencia: `artifacts/modeling/f10-stuff-v3/F10/` — `manifest.json`, `checks.json`,
`selection.json`, `metrics.json`, `head_predictions.parquet`, `event_predictions.parquet`,
`reference_profiles.parquet`, `reference_coverage.json`, `index_scales.json`,
`index_diagnostics.json`, `stuff_v3_index.parquet`, `reproducibility.json`, `decision.md`.

> El lock del release F8 sigue válido: F10 no modifica `modeling/` ni
> `requirements-modeling.txt` (`scripts/check_phase8.py` debe seguir en `verified`).

## Advertencias

- `refA` usa covariables del conjunto evaluado (sin outcomes): sirve para medir el techo, no
  para desplegar a pitchers nuevos. La conclusión operativa se toma con `refB`.
- `phase_review` 2025 ya informó decisiones F2–F6: no es un test independiente.
- Sin conclusiones causales ni valor de carreras.
