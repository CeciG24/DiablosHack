# Ejecutar Fase 9 (macOS)

Guía operativa para ejecutar F9 (mejora de Stuff+ post-release con físicas
derivadas) después de tener F8 verificado **y el test 2026 ya expuesto**. Es
desarrollo posterior al release: el código vive en `postrelease/` para que
`release_lock.json` siga verificando el paquete congelado, y la decisión se toma
solo con datos 2024/2025.

> Reglas que no se pueden saltar: F9 **no puede consultar 2026**
> (`dataset.load` rechaza `test` para cualquier fase que no sea F8), declara la
> exposición previa en su manifiesto, y aunque el candidato promueva, **no
> reabre ni modifica el release** — la evidencia sirve para una futura versión.
> Cada ejecución crea un directorio nuevo en `artifacts/modeling/<experiment_id>/`;
> un ID existente se rechaza, nunca se sobrescribe.

## 0. Prerrequisitos

- `.venv` con `requirements-modeling.txt` (mismas dependencias; no se agregan).
- Artefactos verificados de F1 (`f1-full-reproduction`), F2 (`f2-full-check`) y
  el release F8 (`artifacts/modeling/releases/f8-release-20261014`) intacto —
  `verify_release` lo comprueba contra los hashes del código en `modeling/`.
- `artifacts/modeling/test_exposure.json` presente y su `release_id` igual al
  del release referenciado en `F9.release_reference` del contrato.
- Contrato coherente:

```bash
cd DiablosHack
.venv/bin/python scripts/check_modeling_contract.py   # 10 fases
```

## Fase F9 — Stuff v2 con físicas derivadas

Mismo protocolo A y misma cohorte común de F2. El candidato usa las 11 columnas
físicas originales más **10 derivadas deterministas**: 6 del mismo lanzamiento
(`bauer_units` = spin/velocidad, `break_magnitude`, `break_angle`, `axis_angle`,
`release_slope_v`, `release_slope_h`) y 4 z-scores por `auto_pitch_type`
(`z_rel_speed`, `z_spin_rate`, `z_induced_vert_break`, `z_horz_break`) cuyas
medias/desviaciones se ajustan **solo con train 2024** (tipo no visto →
estadísticos globales). Nada de conteo, ubicación, pitcher ni ambiente.

Búsqueda completa de **12 configuraciones** predeclaradas en `F9.candidates`
(F2 solo probó 3), hasta 800 rondas con parada temprana en development.
Se evalúa contra B0, B1 y el Stuff original congelado de F2; la comparación
decisiva es `StuffV2` vs `B1` en phase_review con bootstrap pareado por partido
(500 remuestreos, regla de promoción: ≥1% relativo e IC95% bajo cero).

```bash
# Prueba rápida (1 candidato, 60 rondas, 20 remuestreos; sin validez científica)
.venv/bin/python -m postrelease.phase9 --experiment-id f9-smoke-check --smoke

# Ejecución completa — ID de referencia documentado
.venv/bin/python -m postrelease.phase9 --experiment-id f9-stuff-v2
```

Ojo: el módulo es `postrelease.phase9`, **no** `modeling.cli` — F9 no está en
`--phase` del CLI porque tocar `modeling/*.py` invalidaría el lock del release.

Verificación independiente (recontar de métricas desde `predictions.parquet`,
re-ejecuta el bootstrap pareado con la misma semilla, verifica que el candidato
seleccionado es el argmin en development, re-predice una muestra con el modelo
guardado y con el Stuff de F2, audita hashes y la exposición declarada).
Argumento posicional:

```bash
.venv/bin/python scripts/check_phase9.py f9-stuff-v2
```

Salida: `artifacts/modeling/f9-stuff-v2/F9/` con `candidates/` (12 modelos),
`stuff_v2/` (seleccionado), `selection.json`, `predictions.parquet` (4 modelos ×
3 particiones de 2025), `metrics.json`, `calibration_*.svg`,
`permutation_importance.*`, `reproducibility.json`, `checks.json`,
`manifest.json` y `decision.md`. Estado esperado: `"status": "verified"` y
`scientific_decision` `promote` o `retain_reference`.

> El lock del release F8 sigue validando porque F9 no modifica `modeling/` ni
> `requirements-modeling.txt`: `scripts/check_phase8.py` y la interfaz local del
> release siguen funcionando después de F9.

## Orden mínimo F9

```bash
.venv/bin/python scripts/check_modeling_contract.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m postrelease.phase9 --experiment-id f9-stuff-v2
.venv/bin/python scripts/check_phase9.py f9-stuff-v2
```

Si `check_phase9.py` no termina con `status: verified`, no continuar. Si la
decisión es `promote`, el siguiente paso no es re-entrenar el release: es
definir una fase posterior con su propio protocolo (o esperar el mapeo de
estadios/xRunValue pendientes).

## Estado de las fases

| Fase | Contenido | Estado |
|---|---|---|
| F0–F7 | Pipeline de desarrollo y scores | verified |
| F8 | Release congelado, evaluación 2026 e interfaz local | verified |
| F9 | StuffV2 post-release (físicas derivadas; `retain_reference`) | verified |

Detalles: `docs/MODELING_SYSTEM_CONTRACT.md` sección F9, código en
`postrelease/stuff_v2.py` y `postrelease/phase9.py`, pruebas en
`tests/modeling/test_stuff_v2.py`.
