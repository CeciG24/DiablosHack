# Ejecutar Fase 8 (macOS)

Guía operativa para ejecutar F8 (release congelado, evaluación final sobre 2026 e
interfaz local) después de tener verificadas F0–F7. Los scripts `.ps1`
(`run_release.ps1`, `run_modeling.ps1`) son exclusivos de Windows; en macOS/Linux
se usa directamente el Python del entorno `.venv`.

> Reglas que no se pueden saltar: **F8 abre el test sellado de 2026 una sola
> vez**. La apertura queda registrada en `artifacts/modeling/test_exposure.json`
> y `test_access.jsonl` (registro local, irreversible). Después de esa apertura,
> `freeze` rechaza crear otro release y una segunda evaluación exige el mismo
> `release_id` con `--reproduce`. Ninguna comparación de F8 selecciona modelos:
> todas quedan `report_only_no_selection`.

## 0. Prerrequisitos

- `.venv` creado con Python 3.12 y `requirements-modeling.txt` instalado
  (ver `docs/EJECUTAR_PIPELINE.md`, sección 0).
- Versión de datos publicada cuyo `<run_id>` coincide con `expected_data_run`
  en `config/modeling_contract.json`.
- Artefactos completos y verificados de las fases previas en `artifacts/modeling/`:
  - `f0-full-reproduction` (F0)
  - `f1-full-reproduction` (F1)
  - `f2-full-check` (F2)
  - `f3-full-check` (F3) — contiene `A/B1.json`, baseline copiado al release
  - `f4-full-check` (F4) — modelos de eventos y cabezas contact/groundball/chase
  - `f5-full-check` (F5)
  - `f6-full-check` (F6) — modelo ambiental experimental copiado al release
  - `f7-full-check` (F7) — requerido por `F8.f7_reference_experiment`; debe ser
    corrida completa (`smoke: false`), `status: verified` y `test_accessed: false`
- Que **no** exista `artifacts/modeling/test_exposure.json` (test aún sellado
  en esta máquina).

```bash
cd DiablosHack

# Contrato coherente con los datos antes de empezar
.venv/bin/python scripts/check_modeling_contract.py
```

> Aviso de datos: la corrida oficial documentada (`docs/F8_*`) se hizo en
> Windows contra el data run `c1c8ba48818dc878` con el release
> `f8-release-20261013` (`release_id`
> `4df11fbf516455a6c90c45bea2f780a3e2441a64f1c6f15a6e637c84c619ef64`). Ese
> paquete no está en git (los artefactos son locales) y además quedó fijado a
> ese data run: copiarlo aquí no sirve, `authorize_test` rechaza un dataset
> distinto. Si `expected_data_run` local difiere (p. ej. `e9e0b1114dc68eb2`),
> hay que congelar un release nuevo: el `release_id` y las métricas pueden
> diferir de la evidencia `docs/F8_*`, que sigue siendo la referencia oficial.

## Fase F8 — qué hace

No entrena nada ni ajusta pesos con 2026. Tres pasos, en orden obligatorio:

1. **`freeze`**: empaqueta la política aprobada (modelos de eventos y cabezas
   de F4, calibradores/políticas, normalizadores S0 de F7, B1 de F3, el
   candidato ambiental de F6, soporte de entrenamiento y configuración) en
   `artifacts/modeling/releases/<nombre>/` con `release_lock.json` que fija
   hashes de archivos, de todo `modeling/*.py`, de `requirements-modeling.txt`
   y del dataset. Falla si el test ya fue expuesto localmente.
2. **`smoke`**: prueba previa obligatoria sobre 2025 (no toca 2026). Reproduce
   las probabilidades de F4, comprueba invarianza de lote, entradas mixtas
   inválidas y categorías desconocidas, y mide tiempos sobre 1,000 registros.
   Escribe `pretest_checks.json` y `benchmark.json` dentro del release;
   `evaluate` se niega a correr si algún check no es `true`.
3. **`evaluate`**: verifica el lock completo, registra la apertura del test y
   evalúa solo filas de 2026 sobre la cohorte común F0. Genera métricas,
   calibración, comparaciones pareadas predeclaradas (500 remuestreos por
   partido), subgrupos, cobertura por familia, scores y agregados, y tres casos
   de scouting por volumen de muestra.

El nombre del release debe ser `[A-Za-z0-9][A-Za-z0-9_-]{0,99}`. Convención:
`f8-release-AAAAMMDD`.

```bash
# 1. Congelar el release (imprime la carpeta y el release_id — guardarlo)
.venv/bin/python -m modeling.phase8 freeze --name f8-release-20261014

# 2. Prueba previa sobre 2025 (obligatoria antes de evaluar)
.venv/bin/python -m modeling.phase8 smoke --release artifacts/modeling/releases/f8-release-20261014

# 3. Evaluación final — ABRE EL TEST 2026 (una sola vez por máquina)
# Lee el release_id del lock (64 hex); también sirve pegar el impreso por freeze
RID=$(.venv/bin/python -c "import json;print(json.load(open('artifacts/modeling/releases/f8-release-20261014/release_lock.json'))['release_id'])")
.venv/bin/python -m modeling.phase8 evaluate \
  --release artifacts/modeling/releases/f8-release-20261014 \
  --release-id "$RID"
```

Reproducción posterior (mismo release, crea `evaluation_reproduction_<ts>/`
sin reemplazar la original):

```bash
.venv/bin/python -m modeling.phase8 evaluate \
  --release artifacts/modeling/releases/f8-release-20261014 \
  --release-id "$RID" --reproduce
```

Verificación independiente en otro proceso (revisa hashes del lock, vuelve a
predecir una muestra del test ya guardado, recalcula métricas e intervalos,
agregados y la regla de selección de casos; **no** vuelve a consultar 2026).
Ojo: el release es **argumento posicional**:

```bash
.venv/bin/python scripts/check_phase8.py artifacts/modeling/releases/f8-release-20261014
```

Salida: `artifacts/modeling/releases/f8-release-20261014/` con
`release_lock.json`, `models/` (tres familias × cuatro cabezas), `environment/`,
`*_scale.json`, `B1.json`, `config.json`, `policy.json`, `training_support.json`,
`cohorts.json`, `pretest_checks.json`, `benchmark.json` y `evaluation/` con
`metrics.json`, `calibration.json`, `coverage.json`, `subgroups.json`,
`scores.parquet`, `<familia>_inference.parquet`, `pitcher_aggregates.parquet`,
`pitcher_type_aggregates.parquet`, `scouting_cases.json`,
`evaluation_cohort.parquet`, `population.parquet` y `manifest.json`.
Estado esperado del manifiesto: `"status": "verified"`.

> Entre `freeze` y `evaluate` no modificar `modeling/*.py` ni
> `requirements-modeling.txt`: `verify_release` compara sus hashes contra el
> lock y aborta si cambiaron.
> La evaluación registra la exposición del test **en esta máquina**; el
> registro no se sincroniza solo — al mover los artefactos hay que copiar la
> carpeta completa del release junto con `test_exposure.json` y
> `test_access.jsonl`.

## Interfaz local de inferencia

Servidor HTTP solo en loopback (sin CORS ni autenticación; no publicar). Se
detiene con Ctrl+C:

```bash
.venv/bin/python -m modeling.api --release artifacts/modeling/releases/f8-release-20261014 --serve --port 8765
```

- `GET http://127.0.0.1:8765/health` — estado e ID del release
- `GET http://127.0.0.1:8765/schema` — features por familia, unidades y límites
- `POST http://127.0.0.1:8765/predict` — cuerpo `{"family":"pitching","records":[{...}]}`;
  máximo 10,000 registros y 5 MB

Modo archivo (la salida no sobrescribe un archivo existente; ejemplo de petición
en `docs/F8_API_EXAMPLE.json`):

```bash
.venv/bin/python -m modeling.api \
  --release artifacts/modeling/releases/f8-release-20261014 \
  --input docs/F8_API_EXAMPLE.json --output salida.json
```

Uso directo en Python:

```python
from modeling.inference import ReleasePredictor

predictor = ReleasePredictor("artifacts/modeling/releases/f8-release-20261014")
respuesta = predictor.records(lanzamientos, family="pitching")
```

No exige outcomes ni pitcher conocido; conserva orden e IDs repetidos; filas
inválidas devuelven `invalid_input` con probabilidades y score nulos. Familias:
`stuff`, `location`, `pitching`.

## Regenerar el informe técnico

```bash
.venv/bin/pip install -r requirements-reporting.txt
.venv/bin/python scripts/build_phase8_report.py artifacts/modeling/releases/f8-release-20261014
```

Genera `output/pdf/DIABLOS_INFORME_TECNICO_F8.pdf` (diez páginas) a partir de la
evidencia del release. La copia versionada de la corrida oficial está en
`docs/DIABLOS_INFORME_TECNICO_F8.pdf`.

## Resumen de equivalencias

| Windows (.ps1) | macOS / Linux |
|---|---|
| `.\run_release.ps1 freeze -Name X` | `.venv/bin/python -m modeling.phase8 freeze --name X` |
| `.\run_release.ps1 smoke -Release R` | `.venv/bin/python -m modeling.phase8 smoke --release R` |
| `.\run_release.ps1 evaluate -Release R -ReleaseId ID` | `.venv/bin/python -m modeling.phase8 evaluate --release R --release-id ID` |
| `.\run_release.ps1 evaluate ... -Reproduce` | igual + `--reproduce` |
| `.\run_release.ps1 serve -Release R` | `.venv/bin/python -m modeling.api --release R --serve --port 8765` |
| `.\run_modeling.ps1 contract` | `.venv/bin/python scripts/check_modeling_contract.py` |
| `.\run_modeling.ps1 tests` | `.venv/bin/python -m unittest discover -s tests -v` |

## Orden mínimo F8

```bash
.venv/bin/python scripts/check_modeling_contract.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m modeling.phase8 freeze --name f8-release-20261014
.venv/bin/python -m modeling.phase8 smoke --release artifacts/modeling/releases/f8-release-20261014
RID=$(.venv/bin/python -c "import json;print(json.load(open('artifacts/modeling/releases/f8-release-20261014/release_lock.json'))['release_id'])")
.venv/bin/python -m modeling.phase8 evaluate --release artifacts/modeling/releases/f8-release-20261014 --release-id "$RID"
.venv/bin/python scripts/check_phase8.py artifacts/modeling/releases/f8-release-20261014
```

Si `check_phase8.py` no termina con `status: verified`, no continuar. Si
`evaluate` falla a mitad de camino después de registrar la apertura, el test ya
consta como expuesto: repetir con `--reproduce` y el mismo `release_id`, no
congelar otro release.

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
| F8 | Release congelado, evaluación final 2026 e interfaz local | verified |

Detalles de implementación y resultados de la corrida oficial:
`docs/FASE_8_IMPLEMENTACION.md`, la ficha `docs/FICHA_MODELO_F8.md` y el
contrato `docs/MODELING_SYSTEM_CONTRACT.md`. Evidencia estructurada:
`docs/F8_VALIDATION.json`, `docs/F8_PRETEST_VALIDATION.json`,
`docs/F8_FINAL_METRICS.json`, `docs/F8_COVERAGE.json`, `docs/F8_SUBGROUPS.json`,
`docs/F8_BENCHMARK.json`, `docs/F8_RELEASE_LOCK.json`,
`docs/F8_TEST_EXPOSURE.json` y `docs/F8_HTTP_VALIDATION.json`.
