# Ejecutar el pipeline fase a fase (macOS)

Guía operativa para preparar los datos y ejecutar las fases de modelado F0–F2.
Los scripts `.ps1` son exclusivos de Windows; en macOS/Linux se usa directamente el
Python del entorno `.venv`. F3–F8 están definidas en
`config/modeling_contract.json` pero **no implementadas**: no hay comandos para ellas.

> Reglas que no se pueden saltar: el test de 2026 está sellado (solo se abre en F8 con
> `release_lock.json`), cada ejecución crea un directorio nuevo en
> `artifacts/modeling/<experiment_id>/` y un ID existente se rechaza, nunca se sobrescribe.

## 0. Prerrequisitos (una sola vez)

```bash
cd DiablosHack

# Entorno con Python 3.12 (el README lo exige; python3 del sistema no sirve)
/usr/local/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements-modeling.txt   # incluye requirements.txt + lightgbm + scipy
```

`requirements.txt` basta para preparación, F0 y F1. F2 requiere además
`lightgbm==4.6.0` y `scipy==1.16.3` de `requirements-modeling.txt`.

## Fase de datos — preparación de la base

El dataset no está en Git. `scripts/prepare_data.py` espera el ZIP autorizado del
hackathon (por defecto `Diablos - Hackathon 2026 (1).zip` en la raíz, o `--source`).
Debe contener exactamente un `.parquet` (`stuff_model_df.parquet`) y un `.csv`
(`stuff_plus_data_dictionary.csv`).

```bash
# 1. Construir la versión de datos (idempotente: reutiliza el run si nada cambió)
.venv/bin/python scripts/prepare_data.py
#    o con otra ruta:  .venv/bin/python scripts/prepare_data.py --source /ruta/al.zip

# 2. Verificar la versión publicada en data/CURRENT
.venv/bin/python scripts/check_data.py

# 3. Probar la API de lectura
.venv/bin/python examples/load_training_data.py
```

Produce `data/runs/<run_id>/` con `diablos.duckdb`, tablas parquet, catálogo,
perfiles de calidad y `manifest.json`. El `<run_id>` resultante debe coincidir con
`expected_data_run` en `config/modeling_contract.json`; si el ZIP difiere del original,
el run_id cambia y hay que actualizar ese campo (el contenido se valida igual).

```bash
# Contrato de modelado coherente con los datos (sin entrenar nada)
.venv/bin/python scripts/check_modeling_contract.py

# Pruebas unitarias (ejemplos sintéticos; no necesitan el dataset real)
.venv/bin/python -m unittest discover -s tests -v
```

## Fase F0 — infraestructura y cohorte común

Carga la cohorte, verifica particiones 2024/2025 (train / development / calibration /
phase_review) y escribe predicciones **ficticias** uniformes (1/6 por clase). No entrena
modelos ni produce métricas.

```bash
# Prueba rápida: hasta 20,000 pitches por partidos completos
.venv/bin/python -m modeling.cli smoke

# Verificación completa 2024–2025 — OBLIGATORIA con este ID para habilitar F1
.venv/bin/python -m modeling.cli smoke --full --experiment-id f0-full-reproduction
```

Salida: `artifacts/modeling/<experiment_id>/F0/` con `manifest.json`,
`cohort_manifest.json`, `assignments.parquet`, `predictions.parquet`, `checks.json`,
`decision.md`. Estado esperado: `"status": "verified"`.

> F1 rechaza la referencia si el run de F0 no fue `--full` o si el ID no es
> `f0-full-reproduction` (`F1.f0_reference_experiment` en el contrato).

## Fase F1 — baselines de eventos B0/B1/B2

Entrena tres baselines con 2024 únicamente y los evalúa en las tres subparticiones de
2025: B0 global, B1 por conteo (referencia del contrato), B2 por conteo + tipo de pitch.
Requiere el run completo de F0 anterior.

```bash
# Prueba rápida (20 remuestreos bootstrap por partido)
.venv/bin/python -m modeling.cli train --phase F1 --smoke

# Ejecución completa (500 remuestreos) — OBLIGATORIA con este ID para habilitar F2
.venv/bin/python -m modeling.cli train --phase F1 --experiment-id f1-full-reproduction
```

Salida: `artifacts/modeling/<experiment_id>/F1/` con `models/{B0,B1,B2}.json`,
`predictions.parquet`, `metrics.json`, curvas SVG, `checks.json`, `decision.md`.

> F2 requiere un run F1 completo verificado con ID `f1-full-reproduction`
> (`F2.f1_reference_experiment`).

## Fase F2 — modelo físico Stuff (LightGBM)

Clasificador multiclase de `y_event` con las 11 variables físicas permitidas. Selecciona
entre las 3 configuraciones predeclaradas por log loss de desarrollo, con parada
temprana, importancia por permutación y comparación bootstrap contra B0 y B1 sobre la
misma cohorte de F1.

```bash
# Prueba rápida (reentrena baselines en muestra; 60 rondas máx.)
.venv/bin/python -m modeling.cli train --phase F2 --smoke

# Ejecución completa (reutiliza los modelos JSON aprobados de F1)
.venv/bin/python -m modeling.cli train --phase F2 --experiment-id f2-full-check
```

Verificación independiente en otro proceso (recarga el modelo, reproduce
probabilidades, métricas y bootstrap):

```bash
.venv/bin/python scripts/check_phase2.py --experiment-id f2-full-check
```

Salida: `artifacts/modeling/<experiment_id>/F2/` con `stuff/` (modelo nativo +
metadatos), `selection.json`, `permutation_importance`, `predictions.parquet`,
`metrics.json`, `checks.json`, `decision.md`.

## Resumen de equivalencias

| Windows (.ps1) | macOS / Linux |
|---|---|
| `.\run_data.ps1 prepare` | `.venv/bin/python scripts/prepare_data.py` |
| `.\run_data.ps1 check` | `.venv/bin/python scripts/check_data.py` |
| `.\run_data.ps1 example` | `.venv/bin/python examples/load_training_data.py` |
| `.\run_data.ps1 tests` | `.venv/bin/python -m unittest discover -s tests -v` |
| `.\run_modeling.ps1 smoke` | `.venv/bin/python -m modeling.cli smoke` |
| `.\run_modeling.ps1 full` | `.venv/bin/python -m modeling.cli smoke --full` |
| `.\run_modeling.ps1 f1-smoke` | `.venv/bin/python -m modeling.cli train --phase F1 --smoke` |
| `.\run_modeling.ps1 f1` | `.venv/bin/python -m modeling.cli train --phase F1` |
| `.\run_modeling.ps1 f2-smoke` | `.venv/bin/python -m modeling.cli train --phase F2 --smoke` |
| `.\run_modeling.ps1 f2` | `.venv/bin/python -m modeling.cli train --phase F2` |
| `.\run_modeling.ps1 contract` | `.venv/bin/python scripts/check_modeling_contract.py` |

## Orden mínimo para el pipeline completo

```bash
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/check_data.py
.venv/bin/python scripts/check_modeling_contract.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m modeling.cli smoke --full --experiment-id f0-full-reproduction
.venv/bin/python -m modeling.cli train --phase F1 --experiment-id f1-full-reproduction
.venv/bin/python -m modeling.cli train --phase F2 --experiment-id f2-full-check
.venv/bin/python scripts/check_phase2.py --experiment-id f2-full-check
```

Las ejecuciones completas tardan más que las de prueba (F1: 500 remuestreos bootstrap;
F2: entrenamiento LightGBM sobre ~250k pitches de evaluación). Cada fase valida el
manifiesto, hashes y cohorte de la fase aprobada anterior antes de entrenar; si algo
cambió, se bloquea en vez de continuar.

## Estado de las fases y referencia

| Fase | Contenido | Estado |
|---|---|---|
| F0 | Adaptador, cohorte común, registro de experimentos | verified |
| F1 | Baselines B0/B1/B2 | verified |
| F2 | Modelo físico Stuff (LightGBM) | verified |
| F3 | Location y Pitching sin ambiente | not_started |
| F4 | Calibración y contacto | not_started |
| F5 | Arsenal con historia real | not_started |
| F6 | Ambiente y simulación | not_started |
| F7 | Scores y agregación | not_started |
| F8 | Evaluación final y entrega (abre test 2026) | not_started |

Detalles de implementación y decisiones: `docs/FASE_0_IMPLEMENTACION.md`,
`docs/FASE_1_IMPLEMENTACION.md`, `docs/FASE_2_IMPLEMENTACION.md` y el contrato
`docs/MODELING_SYSTEM_CONTRACT.md`.
