# Ejecutar Fase 7 (macOS)

Guía operativa para ejecutar F7 (índices provisionales y agregación, protocolo A)
después de tener verificadas F0–F6. Los scripts `.ps1` son exclusivos de Windows;
en macOS/Linux se usa directamente el Python del entorno `.venv`.

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
  - `f4-full-check` (F4)
  - `f5-full-check` (F5)
  - `f6-full-check` (F6) — requerido por `F7.f6_reference_experiment`

```bash
cd DiablosHack

# Contrato coherente con los datos antes de empezar
.venv/bin/python scripts/check_modeling_contract.py
```

## Fase F7 — scores y agregación

No entrena modelos: convierte las probabilidades calibradas ya aprobadas del
protocolo A (Pitching verificado contra la rama seleccionada de F6) en índices
provisionales **Stuff+ / Location+ / Pitching+** con escala fija — `100 + 10·(S − μ)/σ`,
donde μ y σ se calculan una sola vez sobre los 59,367 pitches elegibles de
calibración 2025 y se congelan. La versión publicada es `event_utility_proxy_v1`
(S0 = whiff + called_strike − 0.5·ball − hit_by_pitch); la experimental
`event_contact_utility_proxy_v1` (S1, con premio a contacto débil y castigo al
fuerte) aplica solo a Location y Pitching —en Stuff devuelve nulo con motivo— y
sus resultados se guardan separados, con 24 variantes de sensibilidad ±25%.
También agrega por pitcher y por pitcher/tipo como media de la mezcla observada,
con cobertura explícita (los nulos conservan motivo, nunca se imputan a 100) y
traduce los deltas ambientales de F6 a la misma escala S0 de Pitching, como
resultados experimentales. Requiere el run completo verificado de F6.

```bash
# Prueba rápida (selecciona partidos hasta ~20k registros; la referencia de
# normalización sigue siendo la calibración completa; sin validez científica)
.venv/bin/python -m modeling.cli train --phase F7 --smoke

# Ejecución completa — ID de referencia documentado
.venv/bin/python -m modeling.cli train --phase F7 --experiment-id f7-full-check
```

Verificación independiente en otro proceso (reproduce las fórmulas sin usar
`FixedScale`, compara probabilidades con las fuentes, valida IDs de referencia,
recontar de agregados, sensibilidad y escenarios ambientales). Ojo: el
experimento es **argumento posicional**, no `--experiment-id`:

```bash
.venv/bin/python scripts/check_phase7.py f7-full-check
```

Salida: `artifacts/modeling/f7-full-check/F7/` con `scores.parquet` (S0 por
lanzamiento con probabilidades y procedencia), `scores_pitcher.parquet` y
`scores_pitcher_type.parquet` (agregados), `experimental_contact_scores*.parquet`
(S1 separado), `<familia>_<versión>.json` (μ, σ, pesos y referencia),
`reference_ids.parquet`, `population.parquet`, `contact_sensitivity.json`,
`environment_score_deltas.parquet`, `policy.json`, `checks.json` y
`manifest.json`. Estado esperado: `"status": "verified"`.

> El ID `f7-full-check` es el usado en la corrida de referencia documentada; F8
> aún no está implementada, así que ninguna fase posterior lo exige por ahora.
> La evidencia rápida oficial quedó en `f7-smoke-final`
> (`scripts/check_phase7.py f7-smoke-final`).
> Duración de referencia: ~5.6 min (incluye verificación de dependencias,
> agregación y escritura; no es un benchmark de inferencia).

## Puntuar un lote con la escala fija

```python
from modeling.scoring import FixedScale

scale = FixedScale.load(
    'artifacts/modeling/f7-full-check/F7/pitching_event_utility_proxy_v1.json'
)
resultado = scale.score(lote_de_probabilidades)
```

El lote requiere IDs únicos y las seis columnas `p_ball`, `p_called_strike`,
`p_whiff`, `p_foul`, `p_in_play`, `p_hit_by_pitch`. Si declara familia o versión
de datos, deben coincidir con el normalizador. No se llama a `fit` con la
consulta: la escala quedó fijada con calibración 2025, así que `100` siempre
significa lo mismo entre consultas.

## Resumen de equivalencias

| Windows (.ps1) | macOS / Linux |
|---|---|
| `.\run_modeling.ps1 f7-smoke` | `.venv/bin/python -m modeling.cli train --phase F7 --smoke` |
| `.\run_modeling.ps1 f7` | `.venv/bin/python -m modeling.cli train --phase F7` |
| `.\run_modeling.ps1 contract` | `.venv/bin/python scripts/check_modeling_contract.py` |
| `.\run_modeling.ps1 tests` | `.venv/bin/python -m unittest discover -s tests -v` |

## Orden mínimo F7

```bash
.venv/bin/python scripts/check_modeling_contract.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m modeling.cli train --phase F7 --experiment-id f7-full-check
.venv/bin/python scripts/check_phase7.py f7-full-check
```

Si `check_phase7.py` no termina con `status: verified`, no continuar: la fase
verifica la integridad de los artefactos de F6 y sus dependencias F5/F4 antes
de construir los índices, y se bloquea si algo cambió.

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
| F7 | Scores y agregación (S0 publicada, S1 experimental) | verified |
| F8 | Evaluación final y entrega (abre test 2026) | not_started |

Detalles de implementación y resultados: `docs/FASE_7_IMPLEMENTACION.md` y el
contrato `docs/MODELING_SYSTEM_CONTRACT.md`. Evidencia estructurada:
`docs/F7_VALIDATION.json`, `docs/F7_FULL_VALIDATION.json` y
`docs/F7_SMOKE_VALIDATION.json`.
