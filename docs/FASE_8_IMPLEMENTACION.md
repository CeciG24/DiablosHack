# Fase 8: release congelado, evaluación final e interfaz local

Fecha: 13 de octubre de 2026. Datos: `c1c8ba48818dc878`. Protocolo A.

## Qué se implementó y por qué

Se empaquetó la política aprobada de F7, sin entrenar nuevamente ni ajustar pesos con 2026. El release `f8-release-20261013` contiene los modelos de eventos y las cabezas auxiliares de F4, sus calibradores/políticas, los tres normalizadores S0, los IDs de calibración, soporte de entrenamiento y configuración. Incluye B1 y el candidato ambiental de F6 para comparaciones finales predeclaradas.

El ID del release es:

```text
4df11fbf516455a6c90c45bea2f780a3e2441a64f1c6f15a6e637c84c619ef64
```

`release_lock.json` fija hashes de los archivos, código de modelado, dependencias declaradas y dataset. Se valida antes de cargar el paquete y antes de consultar 2026. La apertura se registra en `artifacts/modeling/test_exposure.json` y `test_access.jsonl`. Una segunda evaluación requiere el mismo release y `--reproduce`; no permite congelar otra política mientras exista el registro de exposición local. Este registro no es un servicio centralizado: debe preservarse al mover los artefactos a otra máquina.

La política publicada sigue siendo base: ni arsenal ni ambiente fueron promovidos. Stuff conserva su carácter diagnóstico. Los fallbacks de contacto/chase de Stuff siguen usando la prevalencia de entrenamiento aprobada en F4. No se crean S1 ni referencias nuevas para 2026. Esto mantiene separadas la evaluación final y la selección de modelos.

## Evaluación final

Se consultan exclusivamente las filas de 2026 después de verificar el release y registrar la apertura. Para comparar familias se conserva la elegibilidad común F0, con target conocido y entradas completas. Se informan log loss, Brier multiclase, diez bins de calibración por clase y métricas de las cabezas condicionales con sus muestras.

Las comparaciones predeclaradas son B1 contra Stuff, Location y Pitching; Location contra Pitching; y Pitching contra el candidato ambiental. Los intervalos usan 500 remuestreos por partido. Todas quedan etiquetadas `report_only_no_selection`: ninguna cambia la política final. F5 conserva su conclusión de desarrollo en protocolo C y no se mezcla con estas comparaciones A.

Se informan dos grupos de pitchers: ausentes de entrenamiento 2024 y ausentes de toda la cohorte 2024-2025. También se desglosa cada categoría de altura. Los grupos con menos de 200 filas o 20 observaciones por clase se etiquetan con soporte insuficiente; sus métricas son descriptivas. No se inventan intervalos individuales ni recomendaciones causales.

La preparación inicial ya había perfilado la calidad de 2026; el lock lo declara. Desde esta fase, el año también está expuesto para evaluación de modelos. Cualquier desarrollo posterior debe declarar esa exposición.

## Inferencia y cobertura: dos poblaciones diferentes

`ReleasePredictor` recibe features observables y una familia. No exige resultados de eventos, contacto ni un pitcher conocido. Conserva orden, identificadores repetidos y una fila de salida por entrada. Los límites físicos provienen del contrato; los conteos deben ser enteros válidos y seno/coseno deben estar entre -1 y 1. Las categorías nuevas usan la rama de valores ausentes del modelo y generan advertencias.

Cada fila devuelve versión de modelo/datos/score/referencia, protocolo, familia, ruta, estado, advertencias, probabilidades y score. Para entradas inválidas, probabilidades e índice son nulos. Para una familia no disponible, devuelve `unsupported_model`. Las cabezas condicionales incluyen su ruta para distinguir modelo y prevalencia. El campo `reference_pitch_count=0` indica que la política base no consume historia de arsenal.

El modelo base no usa la altura como predictor: una categoría desconocida genera advertencia pero no invalida entradas físicas/de ubicación válidas. El simulador ambiental separado sí devuelve `unsupported_environment`. Este comportamiento conserva las decisiones de F6 y no incorpora ajustes de altura sin aprobación científica.

Los archivos `*_inference.parquet` conservan toda la cobertura posible por familia sin exigir outcomes. `scores.parquet` y los agregados de evaluación usan la cohorte común: fuera de ella el score evaluativo es nulo con motivo. Se guardan ambos recuentos para no confundir cobertura de producto y muestra con etiquetas evaluables.

Los agregados representan la mezcla observada por pitcher y pitcher/tipo, con probabilidades, total, número válido y cobertura. Los tres casos de scouting se eligen por mayor cantidad de lanzamientos comunes y desempate por ID, regla fijada antes de abrir test. Es una selección de ejemplos con evidencia abundante, no de los mejores scores. Se conserva evidencia completa por tipo y familia.

## Cómo usar la interfaz local

Desde la raíz del proyecto:

```powershell
.\run_release.ps1 serve
```

El servidor escucha solo en `http://127.0.0.1:8765`. Se detiene con Ctrl+C. No se publica en internet.

- `GET /health`: estado e ID del release.
- `GET /schema`: features por familia, unidades y límites físicos.
- `POST /predict`: cuerpo `{"family":"pitching","records":[{...}]}`.

El máximo es 10,000 registros y 5 MB por petición. La respuesta contiene `records`, con probabilidades anidadas y el índice de cada entrada. Un cuerpo mal formado recibe HTTP 400; una fila con features inválidas conserva su posición y recibe `invalid_input`.

También se puede trabajar sin servidor:

```powershell
.\.venv\Scripts\python.exe -m modeling.api --release artifacts/modeling/releases/f8-release-20261013 --input entrada.json --output salida.json
```

La salida no sobrescribe un archivo existente. Para uso directo en Python:

```python
from modeling.inference import ReleasePredictor

predictor = ReleasePredictor("artifacts/modeling/releases/f8-release-20261013")
respuesta = predictor.records(lanzamientos, family="pitching")
```

Usar `docs/F8_API_EXAMPLE.json` como ejemplo de petición con una fila válida y una inválida. Se construyó con un lanzamiento de 2025 sin outcomes. Las unidades quedan publicadas en `/schema`: mph, rpm, pies para salida/extensión/ubicación, pulgadas para movimiento y seno/coseno adimensionales.

## Cómo probarlo

```powershell
.\run_modeling.ps1 tests
.\run_release.ps1 smoke
.\.venv\Scripts\python.exe scripts/check_phase8.py artifacts/modeling/releases/f8-release-20261013
```

La prueba smoke usa únicamente 2025, comprueba las probabilidades contra F4 y mide tiempos locales sobre 1,000 registros. El verificador final revisa hashes, vuelve a predecir una muestra del test ya guardado, recalcula métricas e intervalos y comprueba los agregados y la regla de selección de casos. No consulta nuevamente 2026 en el dataset ni selecciona modelos.

Para reproducir toda la evaluación después de la apertura original:

```powershell
.\run_release.ps1 evaluate -ReleaseId 4df11fbf516455a6c90c45bea2f780a3e2441a64f1c6f15a6e637c84c619ef64 -Reproduce
```

Esto registra otro acceso y crea una carpeta nueva; no reemplaza la evaluación original. `freeze` es una operación previa a la primera apertura: no debe usarse para borrar el historial de exposición ni volver a seleccionar sobre 2026. Los comandos generales F0-F7 mantienen su bloqueo de test; el acceso final se implementa exclusivamente en `modeling.phase8`.

Los datos/modelos son locales e ignorados por Git. Para transportar la entrega se debe copiar la carpeta completa del release y preservar el registro de exposición, usando el código congelado y las dependencias fijadas. El hash de los datos se comprueba antes de evaluar. Para inferencia basta el paquete y su entorno, sin cargar el dataset original.

## Archivos y evidencia

| Archivo | Función |
|---|---|
| `modeling/release.py` | Congelamiento, integridad y autorización registrada |
| `modeling/inference.py` | Predicción por fila con política final |
| `modeling/api.py` | Interfaz JSON/HTTP local |
| `modeling/phase8.py` | Prueba previa, benchmark y evaluación final |
| `scripts/check_phase8.py` | Auditoría independiente de salidas guardadas |
| `scripts/build_phase8_report.py` | Contribución técnica de diez páginas |
| `tests/modeling/test_release.py` | Integridad, protección de acceso e inferencia mixta |
| `run_release.ps1` | Comandos de release usando `.venv` |

La carpeta `artifacts/modeling/releases/f8-release-20261013/evaluation/` contiene métricas, calibración, cobertura, subgrupos, scores, agregados, inferencias por familia y casos. Los resúmenes de cierre están en `docs/F8_*`. El informe técnico se genera en `output/pdf/DIABLOS_INFORME_TECNICO_F8.pdf` y la ficha del modelo en `docs/FICHA_MODELO_F8.md`.

## Límites

La utilidad S0 no es valor oficial de carreras. La clasificación ambiental no equivale a estadio, altitud numérica ni causalidad. Siguen pendientes mapeo de estadio/Harp, condiciones atmosféricas, secuencia de apariciones al plato, ocupación de bases y adjudicación oficial de algunas etiquetas. La matriz del informe identifica estos pendientes. Completar F8 no implica que esos requisitos oficiales ya estén satisfechos.

## Resultados y cierre verificado

Se evaluaron **130,053 de 135,604 lanzamientos de 2026**, correspondientes a 447 partidos en la cohorte común: **95.9065% de cobertura evaluativa**. La inferencia válida sin exigir outcomes alcanza 134,487 filas de Stuff, 135,173 de Location y 134,316 de Pitching.

| Modelo | Log loss | Brier multiclase |
|---|---:|---:|
| B1 | 1.486855 | 0.744793 |
| Stuff | 1.536157 | 0.763166 |
| Location | 1.038812 | 0.539553 |
| Pitching | 1.023459 | 0.532800 |
| Ambiente experimental | 1.023417 | 0.532822 |

Menor es mejor. Pitching reduce log loss 1.4779% respecto a Location; el delta es -0.015352, con IC 95% [-0.016759, -0.014083]. Stuff empeora frente a B1 y mantiene su interpretación diagnóstica. El delta ambiental es -0.000042, con IC [-0.000410, 0.000289]; no cambia la decisión de desarrollo. No se eligió ningún modelo con estos resultados.

Las medianas calientes para 1,000 entradas fueron 0.0748 s (Stuff), 0.1284 s (Location) y 0.1510 s (Pitching), con cuatro hilos y tres repeticiones. Incluyen las cabezas auxiliares y excluyen carga inicial/red. El hardware y tiempos individuales están en `F8_BENCHMARK.json`.

Pasaron **118 pruebas**, **18 controles previos sobre 2025**, la auditoría independiente final y la prueba HTTP local. El aislamiento de Windows bloqueó inicialmente carpetas temporales y sockets locales; ambas comprobaciones se repitieron con autorización fuera del aislamiento, manteniendo `.venv`. El servidor de prueba se cerró al terminar.

Los tres ejemplos revisables son `pitcher_00292`, `pitcher_00282` y `pitcher_01112`, seleccionados por volumen de muestra, no por calidad. El PDF muestra sus tres tipos más usados; `scouting_cases.json` contiene todos los tipos y familias con cobertura.

La copia versionada del informe está en `docs/DIABLOS_INFORME_TECNICO_F8.pdf`. Para regenerarlo, instalar `requirements-reporting.txt` en `.venv` y ejecutar:

```powershell
.\.venv\Scripts\python.exe scripts/build_phase8_report.py artifacts/modeling/releases/f8-release-20261013
```

En esta ejecución se usaron las librerías de documentos del runtime disponible, importadas desde el Python de `.venv`. Se renderizaron e inspeccionaron las diez páginas. La documentación y el estado administrativo del contrato se cerraron después de evaluar; la configuración copiada dentro del release conserva su estado original `in_progress` y sus hashes intactos.

Para integrar desde una página web de otro origen, usar el backend/proxy local del dashboard. Esta API no configura CORS ni autenticación para exposición remota: su interfaz publicada es local.

## Actualización: evaluación del hackathon (14 de octubre de 2026)

Completar F0-F8 cierra el contrato interno, no el reto completo. Las páginas 9 y 10 del informe contrastan los cuatro criterios, de 25% cada uno, con evidencia y pendientes:

| Criterio | Valoración | Pendiente principal |
|---|---|---|
| Calidad de Stuff+ | Brecha crítica | xRunValue acordado, RMSE y baseline oficial; Stuff no supera el baseline de eventos. |
| Robustez fuera de muestra | Parcial sólido | Park holdout con estadios identificados; sí hay holdout por pitcher y temporal. |
| Arsenal y altitud | Brecha crítica | Incorporación justificada y delta Harp/nivel del mar por pitch shape, con literatura. |
| Aplicabilidad real | Parcial | Interfaz para el coach y evidencia de utilidad en decisiones durante una demostración de 10 minutos. |

Las prioridades son aclarar target y mapeo de estadios con ISAC, fortalecer Stuff+, completar la evaluación por estadio/altura y validar casos con usuarios deportivos. Esta valoración es cualitativa: no estima puntos del jurado. El baseline B1 de eventos no es el baseline oficial de xRunValue por conteo.

Se conserva el release sin cambios. 2026 ya está expuesto y no puede reutilizarse para ajustar modelos y presentarlo después como un nuevo test independiente. La actualización agrega documentación; no implementa los pendientes ni reabre test. Mantener anonimización, confidencialidad y uso exclusivamente deportivo, sin apuestas.
