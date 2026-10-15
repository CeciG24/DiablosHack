# Ejecutar Fase 3 y Fase 4 (macOS)

Guía operativa para ejecutar las fases F3 (Location y Pitching sin ambiente) y
F4 (calibración y cabezas de contacto) después de tener verificadas F0–F2.
Los scripts `.ps1` son exclusivos de Windows; en macOS/Linux se usa directamente el
Python del entorno `.venv`.

> Reglas que no se pueden saltar: el test de 2026 sigue sellado (solo se abre en F8),
> cada ejecución crea un directorio nuevo en `artifacts/modeling/<experiment_id>/` y
> un ID existente se rechaza, nunca se sobrescribe. F3 y F4 **exigen** IDs concretos
> en las corridas completas para habilitar la fase siguiente.

## 0. Prerrequisitos

- `.venv` creado con Python 3.12 y `requirements-modeling.txt` instalado
  (ver `docs/EJECUTAR_PIPELINE.md`, sección 0).
- Versión de datos publicada cuyo `<run_id>` coincide con `expected_data_run`
  en `config/modeling_contract.json`.
- Artefactos completos y verificados de las fases previas en `artifacts/modeling/`:
  - `f0-full-reproduction` (F0)
  - `f1-full-reproduction` (F1)
  - `f2-full-check` (F2) — requerido por `F3.f2_reference_experiment`

```bash
cd DiablosHack

# Contrato coherente con los datos antes de empezar
.venv/bin/python scripts/check_modeling_contract.py
```

## Fase F3 — Location y Pitching sin ambiente

Compara B1, Stuff, Location y Pitching sobre la intersección de lanzamientos
válidos de las tres familias, en dos protocolos: A (temporal 2024→2025, reutiliza
B1 y Stuff congelados de F2) y B (partición por pitcher, reentrena todo).
Requiere el run completo verificado de F2.

```bash
# Prueba rápida (60 rondas máx., 20 remuestreos bootstrap; sin validez científica)
.venv/bin/python -m modeling.cli train --phase F3 --smoke

# Ejecución completa — OBLIGATORIA con este ID para habilitar F4
.venv/bin/python -m modeling.cli train --phase F3 --experiment-id f3-full-check
```

Verificación independiente en otro proceso (recarga los cuatro modelos, reproduce
predicciones, métricas y las ocho comparaciones bootstrap de ambos protocolos):

```bash
.venv/bin/python scripts/check_phase3.py --experiment-id f3-full-check
```

Salida: `artifacts/modeling/f3-full-check/F3/` con subcarpetas `A/` y `B/`, cada
una con `cohort_manifest.json`, `coverage.json`, `selection.json`,
`predictions.parquet`, `metrics.json`, `comparison_table.csv` y los modelos
`stuff/`, `location/`, `pitching/` y `B1.json`. En la raíz: `manifest.json`,
`checks.json`, `decision.md`. Estado esperado: `"status": "verified"`.

> F4 rechaza la referencia si el run de F3 no fue completo o si el ID no es
> `f3-full-check` (`F4.f3_reference_experiment` en el contrato).
> Duración de referencia: ~14.5 min con 4 hilos CPU.

## Fase F4 — calibración y cabezas de contacto

Usa solo el protocolo A. Congela los modelos de eventos de F3, ajusta una
temperatura escalar por familia con 2025/calibration (se acepta solo si no empeora
la log loss de revisión) y entrena tres cabezas auxiliares por familia: contacto
débil/medio/duro, groundball y chase. Cada cabeza se compara contra la prevalencia
de entrenamiento; las no promovidas entregan prevalencia suavizada como salida
pública. Requiere el run completo verificado de F3.

```bash
# Prueba rápida (40 rondas máx., 20 remuestreos bootstrap; sin validez científica)
.venv/bin/python -m modeling.cli train --phase F4 --smoke

# Ejecución completa — OBLIGATORIA con este ID para habilitar F5
.venv/bin/python -m modeling.cli train --phase F4 --experiment-id f4-full-check
```

Verificación independiente (cohortes, temperaturas, 755k+ filas de predicciones
públicas, métricas y 21 comparaciones bootstrap):

```bash
.venv/bin/python scripts/check_phase4.py --experiment-id f4-full-check
```

Salida: `artifacts/modeling/f4-full-check/F4/` con una carpeta por familia
(`stuff/`, `location/`, `pitching/`), cada una con `event/`, `contact/`,
`groundball/` y `chase/` (modelos nativos en `model/`, `temperature.json`,
`calibration_policy.json`), más `predictions.parquet`, `metrics.json`,
`checks.json` y `decision.md`. Estado esperado: `"status": "verified"`.

> F5 rechaza la referencia si el run de F4 no fue completo o si el ID no es
> `f4-full-check` (`F5.f4_reference_experiment` en el contrato).
> Duración de referencia: ~8 min con 4 hilos CPU.
> F5 (arsenal con historia real, protocolo C) ya está implementada: se ejecuta con
> `train --phase F5` y se verifica con `scripts/check_phase5.py`.

## Resumen de equivalencias

| Windows (.ps1) | macOS / Linux |
|---|---|
| `.\run_modeling.ps1 f3-smoke` | `.venv/bin/python -m modeling.cli train --phase F3 --smoke` |
| `.\run_modeling.ps1 f3` | `.venv/bin/python -m modeling.cli train --phase F3` |
| `.\run_modeling.ps1 f4-smoke` | `.venv/bin/python -m modeling.cli train --phase F4 --smoke` |
| `.\run_modeling.ps1 f4` | `.venv/bin/python -m modeling.cli train --phase F4` |
| `.\run_modeling.ps1 f5-smoke` | `.venv/bin/python -m modeling.cli train --phase F5 --smoke` |
| `.\run_modeling.ps1 f5` | `.venv/bin/python -m modeling.cli train --phase F5` |
| `.\run_modeling.ps1 contract` | `.venv/bin/python scripts/check_modeling_contract.py` |
| `.\run_modeling.ps1 tests` | `.venv/bin/python -m unittest discover -s tests -v` |

## Orden mínimo F3 → F4

```bash
.venv/bin/python scripts/check_modeling_contract.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m modeling.cli train --phase F3 --experiment-id f3-full-check
.venv/bin/python scripts/check_phase3.py --experiment-id f3-full-check
.venv/bin/python -m modeling.cli train --phase F4 --experiment-id f4-full-check
.venv/bin/python scripts/check_phase4.py --experiment-id f4-full-check
```

Si un `check_phase*.py` no termina con `status: verified`, no continuar a la fase
siguiente: cada fase valida manifiesto, hashes y cohorte de la fase aprobada
anterior antes de entrenar, y se bloquea si algo cambió.

## Estado de las fases

| Fase | Contenido | Estado |
|---|---|---|
| F0 | Adaptador, cohorte común, registro de experimentos | verified |
| F1 | Baselines B0/B1/B2 | verified |
| F2 | Modelo físico Stuff (LightGBM) | verified |
| F3 | Location y Pitching sin ambiente (protocolos A y B) | verified |
| F4 | Calibración por temperatura y cabezas contact/groundball/chase | verified |
| F5 | Arsenal con historia real (protocolo C) | verified |
| F6 | Ambiente y simulación | not_started |
| F7 | Scores y agregación | not_started |
| F8 | Evaluación final y entrega (abre test 2026) | not_started |

Detalles de implementación y resultados: `docs/FASE_3_IMPLEMENTACION.md`,
`docs/FASE_4_IMPLEMENTACION.md` y el contrato `docs/MODELING_SYSTEM_CONTRACT.md`.
Evidencia estructurada: `docs/F3_VALIDATION.json` y `docs/F4_VALIDATION.json`.
