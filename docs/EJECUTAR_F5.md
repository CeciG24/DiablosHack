# Ejecutar Fase 5 (macOS)

Guía operativa para ejecutar F5 (arsenal con historia real, protocolo C) después de
tener verificadas F0–F4. Los scripts `.ps1` son exclusivos de Windows; en macOS/Linux
se usa directamente el Python del entorno `.venv`.

> Reglas que no se pueden saltar: el test de 2026 sigue sellado (solo se abre en F8),
> cada ejecución crea un directorio nuevo en `artifacts/modeling/<experiment_id>/` y
> un ID existente se rechaza, nunca se sobrescribe.

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
  - `f4-full-check` (F4) — requerido por `F5.f4_reference_experiment`

```bash
cd DiablosHack

# Contrato coherente con los datos antes de empezar
.venv/bin/python scripts/check_modeling_contract.py
```

## Fase F5 — arsenal con historia real

Evalúa si el repertorio histórico aporta información a Pitching, usando solo el
protocolo C. Reconstruye una referencia fija de 2024 (sin usar datos del futuro),
entrena un control (Pitching sin ambiente) y un candidato (Pitching + cinco
variables de arsenal) sobre los mismos pitches de desarrollo 2025, calibra ambos
con temperatura escalar en calibración 2025 y los compara con bootstrap pareado
por partido en revisión. Los pitches sin historia usan un fallback. No reemplaza
la referencia predictiva del protocolo A. Requiere el run completo verificado de F4.

```bash
# Prueba rápida (30 rondas fijas; sin validez científica)
.venv/bin/python -m modeling.cli train --phase F5 --smoke

# Ejecución completa (200 rondas fijas, sin búsqueda)
.venv/bin/python -m modeling.cli train --phase F5 --experiment-id f5-full-check
```

Verificación independiente en otro proceso (reconstruye la referencia 2024 desde
los datos fijados, reajusta temperaturas solo en calibración y reproduce
probabilidades, métricas y decisiones). Ojo: el experimento es **argumento
posicional**, no `--experiment-id`:

```bash
.venv/bin/python scripts/check_phase5.py f5-full-check
```

Salida: `artifacts/modeling/f5-full-check/F5/` con `manifest.json`, `referencia_2024`,
cohortes, modelos, calibradores, curvas SVG, `predictions.parquet`, coberturas por
partición/altura/tipo de pitch, `metrics.json`, política y `decision.md`.
Estado esperado: `"status": "verified"`.

> Duración de referencia: ~3.2 min con 4 hilos CPU.
> El ID `f5-full-check` es el usado en la corrida de referencia documentada; F6 aún
> no está implementada, así que ninguna fase posterior lo exige por ahora. La
> evidencia rápida oficial quedó en `f5-smoke-final`
> (`scripts/check_phase5.py f5-smoke-final`).

## Predecir con la política F5

```python
from modeling.arsenal import predict_policy
predicciones = predict_policy('artifacts/modeling/f5-full-check/F5', entradas)
sin_historia = predict_policy('artifacts/modeling/f5-full-check/F5', entradas, cold_start=True)
```

`entradas` es un DataFrame con `pitch_uid`, `year`, `pitcher_anon_id` y las
variables de `modeling.datasets.PITCHING`. No requiere `y_event` ni outcomes.
Devuelve probabilidades, ruta (modelo/fallback) y advertencia de historia
insuficiente.

## Resumen de equivalencias

| Windows (.ps1) | macOS / Linux |
|---|---|
| `.\run_modeling.ps1 f5-smoke` | `.venv/bin/python -m modeling.cli train --phase F5 --smoke` |
| `.\run_modeling.ps1 f5` | `.venv/bin/python -m modeling.cli train --phase F5` |
| `.\run_modeling.ps1 contract` | `.venv/bin/python scripts/check_modeling_contract.py` |
| `.\run_modeling.ps1 tests` | `.venv/bin/python -m unittest discover -s tests -v` |

## Orden mínimo F5

```bash
.venv/bin/python scripts/check_modeling_contract.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m modeling.cli train --phase F5 --experiment-id f5-full-check
.venv/bin/python scripts/check_phase5.py f5-full-check
```

Si `check_phase5.py` no termina con `status: verified`, no continuar: la fase
valida manifiesto, hashes y cohorte de F4 antes de entrenar, y se bloquea si algo
cambió.

## Estado de las fases

| Fase | Contenido | Estado |
|---|---|---|
| F0 | Adaptador, cohorte común, registro de experimentos | verified |
| F1 | Baselines B0/B1/B2 | verified |
| F2 | Modelo físico Stuff (LightGBM) | verified |
| F3 | Location y Pitching sin ambiente (protocolos A y B) | verified |
| F4 | Calibración por temperatura y cabezas contact/groundball/chase | verified |
| F5 | Arsenal con historia real (protocolo C; `retain_reference`) | verified |
| F6 | Ambiente y simulación | not_started |
| F7 | Scores y agregación | not_started |
| F8 | Evaluación final y entrega (abre test 2026) | not_started |

Detalles de implementación y resultados: `docs/FASE_5_IMPLEMENTACION.md` y el
contrato `docs/MODELING_SYSTEM_CONTRACT.md`. Evidencia estructurada:
`docs/F5_VALIDATION.json`, `docs/F5_FULL_VALIDATION.json` y
`docs/F5_SMOKE_VALIDATION.json`.
