# Fase 0: implementación, decisiones y guía de pruebas

Fecha de ejecución: 29 de septiembre de 2026 en México; 30 de septiembre en los registros UTC.

## Resultado

La fase **F0 está implementada y verificada**. Se puede cargar una cohorte reproducible,
separar 2025 por partido, obtener matrices de predictores permitidos y registrar un experimento
con predicciones ficticias. No se entrenó ningún modelo ni se utilizaron etiquetas de 2026.

Se aprobaron **17 pruebas unitarias** (10 nuevas y 7 de preparación existentes) y
**26 controles por ejecución** del flujo final. Dos verificaciones completas reprodujeron
exactamente la cohorte, sus particiones y los archivos de asignaciones y predicciones.

Estado de implementación: `verified`. Decisión científica: `not_applicable`, porque F0 no
compara modelos. Se usa este estado permitido por la sección 5 del contrato; no corresponde
declarar `promote`, `retain_reference` o `inconclusive` para probabilidades inventadas.
**F1 queda habilitada, pero no fue implementada ni ejecutada.** F1–F8 siguen `not_started`.

## Qué se implementó y por qué

| Componente | Implementación y razón |
|---|---|
| Versión fija de datos | `ModelingDataset` fija `c1c8ba48818dc878`, comprueba el estado validado y los SHA256 de la base y las listas de predictores. Verifica el puntero, manifiesto y configuración antes y después de cargar; detecta cambios de tamaño/fecha en los archivos fijados. Evita combinar versiones entre llamadas. |
| Acceso restringido | La consulta enumera columnas y restringe años a 2024–2025. Solicitar `test` produce `PermissionError` antes de abrir la base. No se utiliza el cargador antiguo para consultar filas. |
| Subparticiones de 2025 | SHA256 de `seed + "|" + game_anon_id`, primeros 16 hexadecimales, módulo 10000. Rangos 0–4999 desarrollo, 5000–7499 calibración, 7500–9999 revisión. Se conserva la asignación por pitch y se rechazan partidos que crucen temporadas. |
| Cohortes comparables | Se filtra cada familia y se hace una intersección mediante joins uno a uno por `pitch_uid`. Los índices de pandas nunca se usan como identidad del pitch. La API conserva también la población propia de cada familia. |
| Separación de predictores | Stuff usa exactamente 11 columnas físicas; Location usa 7; Pitching usa 16, sin altitud. IDs, año, outcomes y banderas quedan fuera de X. El conteo para futuros baselines se obtiene por un join separado y no se agrega a Stuff. |
| Nulos y calidad | Se conservan las reglas de elegibilidad preparadas y los casos completos. Un target nulo se excluye, nunca se convierte en negativo. Las exclusiones se registran de forma secuencial para no contar una fila dos veces, con desglose por partición. |
| Muestra rápida | Se ordenan partidos por SHA256 de la semilla numérica y su ID, y se toman partidos completos hasta antes de exceder 20,000 pitches. El tamaño es aproximado; la selección es independiente del orden de filas y de los outcomes. |
| Registro de experimentos | Un directorio exclusivo por ejecución guarda configuración, versiones, semillas, hashes, tiempos, población y estado. Un ID de experimento existente se rechaza para preservar resultados anteriores. Los fallos posteriores a la creación del registro quedan como `blocked`. |
| Predicciones ficticias | Se genera probabilidad uniforme 1/6 por clase, en el orden del contrato. Todas las filas llevan `synthetic_smoke_only` y `not_for_scoring`. No se producen scores, rankings ni métricas de rendimiento. |
| Pruebas y operación | Comando `python -m modeling.cli smoke`, variante `--full`, lanzador de PowerShell y pruebas unitarias compatibles con el descubrimiento existente. Se excluyen los artefactos del versionado en `.gitignore`. |

Se utilizó la base DuckDB de solo lectura y las dependencias ya fijadas en `requirements.txt`.
No hizo falta instalar un backend de aprendizaje: su elección corresponde a F2.

### Decisiones que conviene conservar en las fases siguientes

**Pitching sin altitud como predictor:** se mantiene `eligible_pitching_default`, que también
exige disponibilidad de ambiente. Esto respeta el contrato de calidad existente y conserva
una población comparable para una futura ablación ambiental. No se amplió silenciosamente
la población al quitar `altitude_category` de X.

**F8 todavía no puede abrirse:** pasar `phase="F8"` también falla en esta entrega. F0 no
implementa el congelamiento ni la auditoría de un release de F8; aceptar solo una cadena como
autorización permitiría saltarse el contrato. Esa ruta deberá implementarse junto con
`release_lock.json` en F8. No existe una opción de CLI que habilite 2026.

**La API anterior sigue disponible:** el bloqueo pertenece a `modeling.datasets`; no es un
control de permisos del sistema operativo. El código heredado `diablos_data.py` permite
consultas generales y no fue modificado. El trabajo de modelado debe usar el nuevo adaptador.

**Verificar un hash no equivale a evaluar el test:** el checksum lee bytes de la base completa
para comprobar integridad. Las consultas del adaptador solo devuelven etiquetas de 2024–2025.
El perfilado de calidad anterior de 2026 ya estaba declarado en el contrato.

## Archivos entregados

| Archivo | Uso |
|---|---|
| `modeling/__init__.py` | Paquete de infraestructura de modelado. |
| `modeling/datasets.py` | Versión fija, listas de predictores, particiones, muestra, joins y matrices. |
| `modeling/cli.py` | Comando smoke, controles, predicciones ficticias y registro de experimentos. |
| `tests/modeling/test_infrastructure.py` | Diez pruebas de regresión de F0. |
| `tests/test_modeling.py`, `tests/__init__.py` | Integración con el descubrimiento de pruebas existente. |
| `run_modeling.ps1` | Localiza el Python disponible y ejecuta smoke, full, tests o contract. |
| `config/modeling_contract.json` | F0 marcada `verified`; fases restantes pendientes. |
| `README.md`, `docs/MODELING_SYSTEM_CONTRACT.md` | Estado y comandos actualizados. |
| `.gitignore` | Excluye `artifacts/modeling/`. |
| `docs/F0_VALIDATION.json` | Evidencia compacta de pruebas y reproducción. |

## Datos, cohortes y resultados observados

Versión de datos: `c1c8ba48818dc878`. Protocolo: A. Target: `y_event`.
Semilla general: `20260929`. Semilla de particiones: `diablos-modeling-validation-v1`.
Denominador: pitches elegibles comunes para Stuff, Location y Pitching, con target no nulo.

| Población | Prueba rápida | Verificación completa |
|---|---:|---:|
| Pitches asignados de 2024–2025 | 499,398 | 499,398 |
| Seleccionados antes de filtros | 19,958 | 499,398 |
| Cohorte común | 19,681 | 491,678 |
| Train 2024 común | 10,360 | 239,709 |
| Desarrollo 2025 común | 4,929 | 134,420 |
| Calibración 2025 común | 2,492 | 59,367 |
| Revisión 2025 común | 1,900 | 58,182 |

La asignación incluye todos los pitches de desarrollo, incluso los excluidos posteriormente;
por eso `assignments.parquet` tiene 499,398 filas también en smoke. El límite de 20,000
aplica a la muestra anterior a filtros y a las predicciones, no al archivo de asignaciones.
Los porcentajes de partición son esperados por hash de partido, no cuotas exactas por pitch.

| Familia, población completa | Elegibles propios | Fuera de la intersección común |
|---|---:|---:|
| Stuff | 497,006 | 5,328 |
| Location | 492,501 | 823 |
| Pitching sin altitud en X | 491,678 | 0 |

De los 499,398 pitches, Stuff excluye 2,392 por calidad. Location excluye 6,629 por calidad
y 268 adicionales por predictores faltantes. Pitching excluye 7,720 por calidad. Los
contadores posteriores de target nulo fueron cero porque el filtro de calidad ya había
retirado esos eventos. No significa que todos los targets originales estuvieran presentes.

Hash SHA256 de IDs de la cohorte rápida:

```text
1449c8e2fd9077ca29ec75b4afbc236bac97b70c00ccb3d15f85fdeb362f948c
```

Hash SHA256 de IDs de la cohorte completa, reproducido en ambas ejecuciones:

```text
655d826b2a1ede2e153bd4461d74b208dcb18041f698f50b6a000dfed8270d92
```

Los hashes de IDs usan una lista ordenada codificada como JSON UTF-8 compacto. No dependen
del índice de pandas. Los archivos de predicciones y asignaciones también coincidieron
byte por byte entre las dos verificaciones completas. Los manifiestos generales difieren
normalmente en ID de experimento, hora y duración.

### Artefactos locales de la entrega

- Rápida final: `artifacts/modeling/f0-20260930T054601-ce8375c8/F0/`.
- Completa: `artifacts/modeling/f0-full-check/F0/`.
- Reproducción completa: `artifacts/modeling/f0-full-reproduction/F0/`.
- Se preserva la primera prueba de desarrollo en `artifacts/modeling/f0-initial-smoke/F0/`.

Cada ejecución final contiene:

| Artefacto | Contenido |
|---|---|
| `manifest.json` | Identidad, estado, semillas, versiones, tiempos y hashes de datos/código/configuración/artefactos. |
| `config.json` | Copia de la configuración utilizada. |
| `cohort_manifest.json` | Hashes de IDs, denominador, tamaños, predictores y exclusiones por familia y partición. |
| `assignments.parquet` | Pitch, año, partido, pitcher, partición de pitcher, fold y subpartición temporal. |
| `sampled_ids.parquet` | IDs seleccionados antes de los filtros de familia. |
| `predictions.parquet` | Pitches comunes, particiones, probabilidades ficticias y avisos de uso. |
| `checks.json` | Resultado de los 26 controles del flujo. |
| `metrics.json` | `not_applicable` con población y motivo; no publica log loss ni Brier ficticios. |
| `decision.md` | Estado técnico, decisión científica y condición de avance. |

Las copias de configuración de estas ejecuciones conservan F0 en `in_progress`, su estado
al comenzar. La configuración principal se cambió a `verified` después de comprobar las
pruebas y la reproducción. No se alteraron los registros históricos para ocultar esa secuencia.

## Cómo probarlo

Ejecutar desde la raíz del proyecto. El entorno `.venv` se creó el 30 de septiembre de 2026
con las dependencias de `requirements.txt`. Ambos lanzadores utilizan exclusivamente ese
entorno y fallan si no existe. Dentro de un entorno virtual no se inyecta `.analysis_deps`.
Los registros anteriores conservan el intérprete utilizado originalmente.

```powershell
Set-Location 'C:\Users\ceci_\Documents\Ing_ciencias_de_la_computacion\DiablosHack'
.\run_modeling.ps1 contract
.\run_modeling.ps1 tests
.\run_modeling.ps1 smoke
.\run_modeling.ps1 full
```

Resultados esperados: contrato aprobado; 17 pruebas con `OK`; smoke/full con
`"status": "verified"`; hash y tamaños iguales a los anteriores cuando no cambien los datos
ni la configuración operativa. Cada ejecución imprime su directorio de salida.

Si PowerShell bloquea scripts, no es necesario cambiar la política del equipo. Usar el
intérprete directamente:

```powershell
$modelPython = '.\.venv\Scripts\python.exe'
& $modelPython scripts/check_modeling_contract.py
& $modelPython -m unittest discover -s tests -v
& $modelPython -m modeling.cli smoke
& $modelPython -m modeling.cli smoke --full
```

En otro equipo se puede usar Python 3.12 con `requirements.txt`, copiando previamente la
versión preparada autorizada. No es necesario volver a preparar el ZIP.

### Repetir la comprobación de reproducibilidad

Usar IDs nuevos: los siguientes comandos rechazan un ID que ya exista.

```powershell
python -m modeling.cli smoke --full --experiment-id mi-f0-a
python -m modeling.cli smoke --full --experiment-id mi-f0-b
$a = Get-Content artifacts/modeling/mi-f0-a/F0/manifest.json -Raw | ConvertFrom-Json
$b = Get-Content artifacts/modeling/mi-f0-b/F0/manifest.json -Raw | ConvertFrom-Json
$a.cohort.common_ids_sha256 -eq $b.cohort.common_ids_sha256
$a.artifact_hashes.'assignments.parquet' -eq $b.artifact_hashes.'assignments.parquet'
$a.artifact_hashes.'predictions.parquet' -eq $b.artifact_hashes.'predictions.parquet'
```

Las tres comparaciones deben devolver `True`. Sustituir `python` por el intérprete del
entorno si no está configurado en PATH. Un ID repetido debe terminar con error sin sobrescribir.

### Comprobar los bloqueos y usar el adaptador

```python
from modeling.datasets import ModelingDataset

dataset = ModelingDataset()
cohort = dataset.load(maximum=20000)
X, y, metadata = dataset.matrices(cohort, "stuff")
assert X.shape[1] == 11
assert "balls" not in X and "altitude_category" not in X
assert metadata.pitch_uid.is_unique
assert set(metadata.year) <= {2024, 2025}
```

Ejecutar por separado las llamadas siguientes: **deben fallar explícitamente**.

```python
dataset.load(partitions=["test"])                # PermissionError
dataset.load(partitions=["test"], phase="F8")    # PermissionError: aún no existe release autorizado
dataset.load(target="target_inexistente")        # ValueError
```

La prueba de cambio de versión usa una carpeta temporal: verifica alteraciones del puntero,
manifiesto y configuración sin modificar `data/CURRENT` real. Las pruebas también cubren
IDs duplicados/nulos, partidos sin ID, fronteras del hash, mezcla de temporadas, invariancia
al barajar, muestra por partidos completos, joins con orden invertido, conteo fuera de X y
preservación de nulos en targets condicionales.

## Límites y continuidad

No hay comparación predictiva, calibración, scoring, release de F8 ni integración al dashboard.
Los archivos con probabilidades uniformes solo comprueban formatos. La muestra rápida no
respalda conclusiones científicas. La revisión de 2025 será utilizada en fases sucesivas y no
debe presentarse como evaluación final independiente.

La carga rápida todavía consulta las columnas permitidas de toda la población 2024–2025
antes de muestrear; reduce la salida, pero no garantiza baja memoria. La verificación del
checksum también tiene un costo de lectura local. No se descargaron ni subieron datos.

No se ejecutó `scripts/check_data.py` en esta fase porque también perfila etiquetas del test.
Se conservaron las siete pruebas unitarias de preparación, la validación publicada de la
versión y la verificación de integridad de los archivos utilizados.

No quedan fallos técnicos observados de F0. El siguiente trabajo autorizado por el contrato,
cuando se solicite, es **F1: baselines B0/B1/B2**, usando las cohortes y subparticiones guardadas.
