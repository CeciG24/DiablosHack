# Base de datos de pitcheo de Diablos

## Contenido del repositorio

Este repositorio contiene el código, contratos, pruebas y documentación hasta F4.
Los datos del hackathon, `.venv`, los modelos entrenados, artefactos de experimentos y
tablas de análisis se mantienen locales y están excluidos de Git.

Después de clonar, crear `.venv` e instalar `requirements-modeling.txt`. Las pruebas
unitarias usan ejemplos sintéticos; para ejecutar las fases completas también se necesita
la versión de datos autorizada y los artefactos aprobados de las fases anteriores,
distribuidos por el canal privado permitido por el equipo. Sus rutas e identificadores
figuran en `config/modeling_contract.json`; no se descargan automáticamente de GitHub.

La preparación está ejecutada. La versión publicada se identifica en `data/CURRENT`.
Se conservan todos los lanzamientos y se ofrecen tablas de consulta, variables predictoras,
objetivos de aprendizaje, reglas de calidad y particiones de evaluación.

## Empezar a trabajar

Desde la raíz del proyecto, con Python 3.12:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python examples/load_training_data.py
```

El entorno `.venv` está creado en esta computadora con las dependencias de `requirements.txt`.
También puede ejecutarse sin activarlo:

```powershell
.\.venv\Scripts\python.exe examples/load_training_data.py
```

No es necesario volver a preparar el ZIP para consultar la base existente.

En Windows los lanzadores usan exclusivamente el entorno `.venv` del proyecto:

```powershell
.\run_data.ps1 example
.\run_data.ps1 check
```

Si la política local de PowerShell bloquea scripts, usar los comandos de Python anteriores;
no es necesario cambiar la política de seguridad del equipo.

```python
from diablos_data import load_model_data, connect

X, y, metadata = load_model_data(
    feature_set='stuff', target='y_event', split='train'
)
# X: solo variables permitidas. y: objetivo. metadata: IDs para agrupar y auditar.
# Entrenar codificadores y cualquier transformación SOLO con entrenamiento.

with connect() as db:
    resumen = db.execute('SELECT * FROM summary_year ORDER BY year').df()
```

`feature_set`: `stuff`, `location` o `pitching`.
`split`: `train`, `validation` o `test`.
`protocol`: `season` por defecto; `pitcher` como evaluación separada por IDs.
La API devuelve casos completos según la familia seleccionada. No entrena ni imputa.

## Dónde están los datos

| Ubicación | Uso |
|---|---|
| ZIP original | Fuente preservada; no se modifica |
| `data/raw/<hash>/` | Parquet y diccionario extraídos con integridad verificada |
| `data/runs/<versión>/diablos.duckdb` | Base SQL materializada y portátil |
| `data/runs/<versión>/*.parquet` | Tablas interoperables para Python o R |
| `data/runs/<versión>/data_catalog.csv` | Diccionario de tablas y columnas preparadas |
| `data/runs/<versión>/quality_summary.csv` | Conteos de reglas de calidad |
| `data/runs/<versión>/target_profile.csv` | Disponibilidad de cada target |
| `data/runs/<versión>/manifest.json` | Trazabilidad, versiones y SHA256 de artefactos |
| `docs/DATA_CONTRACT.md` | Definiciones, exclusiones y límites de uso |
| `examples/consultas.sql` | Consultas iniciales para el equipo |

La base DuckDB no necesita un servidor. En otro equipo se puede abrir copiando el archivo
`.duckdb`; las tablas están materializadas y no dependen de rutas originales. Para usar
la API de Python, copiar también el código y la carpeta de la versión publicada junto con
`data/CURRENT`. Distribuir estos datos únicamente dentro del uso autorizado de la competencia.

## Reproducir y verificar

```powershell
.venv\Scripts\python scripts/prepare_data.py
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python scripts/check_data.py
```

La preparación verifica el ZIP, aplica reglas del contrato, escribe una carpeta de versión,
valida las tablas y publica el puntero solo después de terminar. Si se ejecuta con la misma
fuente, configuración, código y dependencias, comprueba las sumas de verificación de la versión
existente y la reutiliza. Los cambios producen otra versión y preservan las anteriores.
Una ejecución interrumpida deja una carpeta `.building`, nunca una versión publicada.

Si el organizador cambia el ZIP, revisen el contrato antes de modificar sus conteos esperados.
No borren una carpeta `.building` sin comprobar que ningún proceso la utiliza.

## Reglas de uso esenciales

- No entrenar con `SELECT *` de `pitches` o `model_base`: incluyen resultados y metadatos.
  Usar la API y sus listas explícitas de predictores.
- No usar IDs de jugadores, partido, año ni `source_row_number` como predictores.
- No calcular medias de arsenal con el dataset completo. La tabla histórica usa solo años anteriores.
- Los targets nulos no equivalen a cero. Un pitch sin contacto no es contacto débil.
- Las categorías de altitud no identifican al Harp Helú ni sustituyen un holdout por estadio.
- El test de 2026 queda reservado; su perfilado de calidad ya se realizó, pero no se usó para ajustar modelos.
- La tabla de arsenal no está incorporada a las matrices predeterminadas porque 2024 no tiene historia previa.
  Su uso requiere un protocolo adicional, explicado en el contrato.

## Qué sigue

El desarrollo por fases se rige por [System contract de modelado](docs/MODELING_SYSTEM_CONTRACT.md)
y su [configuración](config/modeling_contract.json). F0 y F1 están implementadas
y verificadas; F2 conserva B1 como referencia histórica. F3 está verificada y promueve
Pitching sin ambiente en los protocolos temporal y por pitcher. F4 está verificada con
calibración y contacto en el protocolo temporal. F5 está verificada con historia fija de 2024
y protocolo C separado. F6 está verificada con ablación ambiental y simulación de asociaciones;
F7–F8 están pendientes.
Consultar [implementación, decisiones y pruebas de F0](docs/FASE_0_IMPLEMENTACION.md).
F1 incorpora baselines de eventos B0/B1/B2. No son scores ni xRunValue.
Verificar cada fase antes de avanzar.
Para comprobar el contrato sin entrenar modelos: `python scripts/check_modeling_contract.py`.

```powershell
.\run_modeling.ps1 smoke    # Hasta 20,000 pitches por partidos completos; probabilidades ficticias
.\run_modeling.ps1 full     # Verificación completa de 2024–2025; 2026 sigue sellado
.\run_modeling.ps1 tests    # Pruebas de datos y modelado
.\run_modeling.ps1 f1-smoke # Baselines F1, muestra rápida y 20 remuestreos por partido
.\run_modeling.ps1 f1       # Baselines F1 completos y 500 remuestreos por partido
.\run_modeling.ps1 f2-smoke # Stuff físico: prueba rápida
.\run_modeling.ps1 f2       # Stuff: selección en desarrollo y comparación con B0/B1
.\run_modeling.ps1 f3-smoke # Location/Pitching: prueba rápida de los protocolos A y B
.\run_modeling.ps1 f3       # Familias sin ambiente y evaluación de pitchers no vistos
.\run_modeling.ps1 f4-smoke # Calibración y cabezas auxiliares: prueba rápida
.\run_modeling.ps1 f4       # Calibración 2025 y contacto/groundball/chase
.\run_modeling.ps1 f5-smoke # Arsenal: prueba de cobertura y fallback
.\run_modeling.ps1 f5       # Protocolo C, referencia fija 2024 y ablación pareada
.\run_modeling.ps1 f6-smoke # Ambiente: prueba rápida
.\run_modeling.ps1 f6       # Ablación ambiental A y simulación de asociaciones
.\run_modeling.ps1 f7-smoke # Scores: muestra por partidos y referencia completa fija
.\run_modeling.ps1 f7       # Stuff+, Location+, Pitching+ y cobertura
```

Equivalente con el Python del entorno: `python -m modeling.cli smoke` y
`python -m modeling.cli smoke --full`. Cada ejecución crea un directorio nuevo en
`artifacts/modeling/<experiment_id>/F0/`; nunca sobrescribe un experimento existente.

F1 se ejecuta también con `.\.venv\Scripts\python.exe -m modeling.cli train --phase F1`
(añadir `--smoke` para la prueba rápida). Guarda modelos JSON, probabilidades, métricas,
curvas SVG y controles en `artifacts/modeling/<experiment_id>/F1/`.
Ver [implementación y pruebas de F1](docs/FASE_1_IMPLEMENTACION.md).

Para F2, instalar las dependencias adicionales dentro del entorno virtual:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-modeling.txt
.\.venv\Scripts\python.exe -m modeling.cli train --phase F2
```

LightGBM está fijado en la versión 4.6.0 y se ejecuta en CPU. F2 guarda el modelo físico,
los vocabularios de entrenamiento, la selección de configuraciones, importancia por
permutación y comparación contra los baselines aprobados. Ver
[implementación y pruebas de F2](docs/FASE_2_IMPLEMENTACION.md).

F3 conserva modelos separados de Stuff, Location y Pitching. Las comparaciones utilizan
los mismos lanzamientos y el protocolo por pitcher entrena modelos propios solo en 2024–2025.
Ver [qué se implementó, por qué y cómo probar F3](docs/FASE_3_IMPLEMENTACION.md).
Para verificar el resultado completo guardado:

```powershell
.\.venv\Scripts\python.exe scripts/check_phase3.py --experiment-id f3-full-check
```

F4 incorpora temperaturas ajustadas solo en calibración 2025 y cabezas condicionales de
contacto, roletazo y chase. Los nulos se preservan; las cabezas sin mejora conservan la
prevalencia de entrenamiento. Ver [implementación, decisiones y pruebas de F4](docs/FASE_4_IMPLEMENTACION.md).

```powershell
.\.venv\Scripts\python.exe scripts/check_phase4.py --experiment-id f4-full-check
```

F5 implementa arsenal con historia fija de 2024 y modelos ajustados en desarrollo 2025.
Ver [implementación, decisión y pruebas de F5](docs/FASE_5_IMPLEMENTACION.md).

El verificador de F5 exige los hashes de su código original. Para reproducirlo después
de cambios de interfaz de fases posteriores, usar la revisión F5 (`0a52041`).

```powershell
.\.venv\Scripts\python.exe scripts/check_phase5.py f5-full-check
```

F6 compara Pitching con/sin categoría ambiental y conserva la referencia si no alcanza el criterio
de promoción. Su simulador mantiene la forma física fija; no representa causalidad ni un estadio.
Ver [implementación, decisión y pruebas de F6](docs/FASE_6_IMPLEMENTACION.md).

```powershell
.\.venv\Scripts\python.exe scripts/check_phase6.py f6-full-check
```

F7 convierte las probabilidades aprobadas en Stuff+, Location+ y Pitching+ provisionales,
con referencia común de calibración 2025 y cobertura por pitcher/tipo. Ver
[implementación y pruebas de F7](docs/FASE_7_IMPLEMENTACION.md).

```powershell
.\.venv\Scripts\python.exe scripts/check_phase7.py f7-full-check
```

El verificador histórico de F6 requiere su revisión original (`00e3410`), porque comprueba
los hashes del código de esa fase. F7 verifica la integridad de sus artefactos como dependencias.

F8 está implementada: release congelado, evaluación final de 2026, API local, ficha del
modelo y contribución técnica de diez páginas. Ver [implementación y pruebas de F8](docs/FASE_8_IMPLEMENTACION.md).
2026 ya está expuesto; ninguna comparación del test cambió la política.

```powershell
.\run_release.ps1 smoke
.\run_release.ps1 serve
.\.venv\Scripts\python.exe scripts/check_phase8.py artifacts/modeling/releases/f8-release-20261013
```

El cierre F7 corresponde a la revisión `fd394e8`; sus artefactos se conservaron intactos.
El release F8 exige mantener el código de modelado congelado para verificar sus hashes.
Las etiquetas y campos externos pendientes siguen requiriendo confirmación de los organizadores.
