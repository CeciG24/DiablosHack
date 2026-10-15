# Ejecutar Fase 6 (macOS)

Guía operativa para ejecutar F6 (ambiente y simulación de asociaciones, protocolo A)
después de tener verificadas F0–F5. Los scripts `.ps1` son exclusivos de Windows;
en macOS/Linux se usa directamente el Python del entorno `.venv`.

> Reglas que no se pueden saltar: el test de 2026 sigue sellado (solo se abre en F8),
> cada ejecución crea un directorio nuevo en `artifacts/modeling/<experiment_id>/` y
> un ID existente se rechaza, nunca se sobrescribe. F6 **exige** IDs concretos en la
> corrida completa para habilitar la fase siguiente.

## 0. Prerrequisitos

- `.venv` creado con Python 3.12 y `requirements-modeling.txt` instalado
  (ver `docs/EJECUTAR_PIPELINE.md`, sección 0).
- Versión de datos publicada cuyo `<run_id>` coincide con `expected_data_run`
  en `config/modeling_contract.json`.
- Artefactos completos y verificados de las fases previas en `artifacts/modeling/`:
  - `f0-full-reproduction` (F0)
  - `f1-full-reproduction` (F1)
  - `f2-full-check` (F2)
  - `f3-full-check` (F3)
  - `f4-full-check` (F4)
  - `f5-full-check` (F5) — requerido por `F6.f5_reference_experiment`

```bash
cd DiablosHack

# Contrato coherente con los datos antes de empezar
.venv/bin/python scripts/check_modeling_contract.py
```

## Fase F6 — ambiente y simulación

Usa solo el protocolo A. Como F5 no promovió el arsenal, F6 continúa con el
Pitching aprobado de F4 y evalúa si `altitude_category` aporta información, en una
ablación pareada: un control (Pitching sin ambiente, que en la corrida completa
reproduce exactamente las probabilidades aprobadas de F4) y un candidato
(Pitching + categoría ambiental) entrenados sobre los mismos pitches de 2024, con
las mismas particiones de 2025 para desarrollo, calibración y revisión. Ambos se
calibran con temperatura escalar en calibración 2025 y se comparan con bootstrap
pareado por partido en revisión (500 remuestreos; la promoción exige ≥1% de
reducción relativa de log loss y límite superior del IC95% bajo cero). También
entrega un simulador de asociación que cambia únicamente `altitude_category`,
guarda deltas de las seis probabilidades y advierte entradas fuera del soporte de
entrenamiento. Stuff y Location no reciben ambiente. Requiere el run completo
verificado de F5.

```bash
# Prueba rápida (60 rondas máx.; sin validez científica)
.venv/bin/python -m modeling.cli train --phase F6 --smoke

# Ejecución completa — OBLIGATORIA con este ID para habilitar F7
.venv/bin/python -m modeling.cli train --phase F6 --experiment-id f6-full-check
```

Verificación independiente en otro proceso (reproduce modelos, calibración,
métricas pareadas, 61 subgrupos, deltas de escenario e intervalos; valida el
manifiesto y los hashes de F5 y F4). Ojo: el experimento es **argumento
posicional**, no `--experiment-id`:

```bash
.venv/bin/python scripts/check_phase6.py f6-full-check
```

Salida: `artifacts/modeling/f6-full-check/F6/` con `manifest.json`,
`cohort.parquet`, `cohort_manifest.json`, `environment_coverage.csv`, subcarpetas
`control/` y `environment/` (cada una con `model/`, `predictions.parquet`,
temperatura y curvas SVG de calibración), `predictions.parquet`, `metrics.json`,
`subgroup_metrics.json`, `environment_support.json`, `input_support.parquet`,
`simulation_deltas.parquet`, `simulation_intervals.json`, `policy.json`,
`checks.json` y `decision.md`. Estado esperado: `"status": "verified"`.

> F7 rechaza la referencia si el run de F6 no fue completo o si el ID no es
> `f6-full-check` (`F7.f6_reference_experiment` en el contrato).
> Duración de referencia: ~10.25 min de entrenamiento y controles internos con
> 4 hilos CPU.
> La evidencia rápida oficial quedó en `f6-smoke-check`
> (`scripts/check_phase6.py f6-smoke-check`).

## Simulador de escenarios ambientales

El simulador es de asociación con forma fija (`fixed_shape_environment_association`):
mantiene velocidad, movimiento, release, ubicación, conteo y manos; solo cambia
`altitude_category`. Los deltas son P(evento | destino) − P(evento | origen) con el
mismo modelo y calibrador; no son carreras, cambios físicos ni efectos causales, y
`recommendation_allowed` es siempre `False`. Categorías no vistas devuelven
`unsupported_environment`.

```python
import pandas as pd
from modeling.environment import EnvironmentSimulator
folder = 'artifacts/modeling/f6-full-check/F6'
inputs = pd.read_parquet(folder + '/cohort.parquet')
inputs = inputs.loc[inputs.partition.eq('phase_review')].head(10).drop(columns='y_event')
simulator = EnvironmentSimulator.load(folder)
comparison = simulator.simulate(inputs, 'Extreme Altitude')
print(comparison[['pitch_uid', 'delta_p_in_play', 'status', 'input_support_status', 'warnings']])
unknown = simulator.simulate(inputs, 'Harp Helu')
assert unknown.status.eq('unsupported_environment').all()
```

Para datos propios basta `pitch_uid`, las variables de `modeling.datasets.PITCHING`
y `altitude_category`; no se necesitan etiquetas ni pitcher conocido.
`simulator.predict(inputs)` entrega las probabilidades del candidato ambiental,
que sigue experimental: la rama aprobada queda en `policy.json` y en las columnas
`selected_*` de `predictions.parquet` (decisión documentada: `retain_reference`).

## Resumen de equivalencias

| Windows (.ps1) | macOS / Linux |
|---|---|
| `.\run_modeling.ps1 f6-smoke` | `.venv/bin/python -m modeling.cli train --phase F6 --smoke` |
| `.\run_modeling.ps1 f6` | `.venv/bin/python -m modeling.cli train --phase F6` |
| `.\run_modeling.ps1 contract` | `.venv/bin/python scripts/check_modeling_contract.py` |
| `.\run_modeling.ps1 tests` | `.venv/bin/python -m unittest discover -s tests -v` |

## Orden mínimo F6

```bash
.venv/bin/python scripts/check_modeling_contract.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m modeling.cli train --phase F6 --experiment-id f6-full-check
.venv/bin/python scripts/check_phase6.py f6-full-check
```

Si `check_phase6.py` no termina con `status: verified`, no continuar: la fase
valida manifiesto, hashes y cohortes de F5 y F4 antes de entrenar, y se bloquea
si algo cambió.

## Estado de las fases

| Fase | Contenido | Estado |
|---|---|---|
| F0 | Adaptador, cohorte común, registro de experimentos | verified |
| F1 | Baselines B0/B1/B2 | verified |
| F2 | Modelo físico Stuff (LightGBM) | verified |
| F3 | Location y Pitching sin ambiente (protocolos A y B) | verified |
| F4 | Calibración por temperatura y cabezas contact/groundball/chase | verified |
| F5 | Arsenal con historia real (protocolo C; `retain_reference`) | verified |
| F6 | Ambiente y simulación (protocolo A; `retain_reference`) | verified |
| F7 | Scores y agregación | verified |
| F8 | Evaluación final y entrega (abre test 2026) | not_started |

Detalles de implementación y resultados: `docs/FASE_6_IMPLEMENTACION.md` y el
contrato `docs/MODELING_SYSTEM_CONTRACT.md`. Evidencia estructurada:
`docs/F6_VALIDATION.json`, `docs/F6_FULL_VALIDATION.json` y
`docs/F6_SMOKE_VALIDATION.json`.
