# Perfilador de candidatos

## Alcance

Ruta `/perfilador`, disponible tambien desde la ficha de un lanzador.
Herramienta operativa para coaches y direccion deportiva: construir un arsenal,
inspeccionar sus relaciones, explorar sensibilidad por altitud y registrar una
decision de evaluacion. No hay un score de contratacion ni un roster identificado
de Diablos. Se conserva el lenguaje visual de MICTLAN.

El usuario autorizo el uso descriptivo de 2025 y 2026 el 21 de octubre de 2026.
La nueva referencia lee exclusivamente identificadores anonimos, temporada,
mano, tipo y caracteristicas fisicas. No lee outcomes, no entrena ni recalibra.
Las escalas F8 siguen ancladas en calibracion 2025. No se presenta 2026 como
confirmacion independiente de decisiones posteriores informadas por esta vista.
No se modifica el registro historico de exposicion ni artefactos congelados.

## Recorrido

1. Crear un candidato manual, importar CSV/TSV/JSON o cargar la muestra de un
   lanzador disponible. Elegir mano, destino y referencia 2025, 2026 o ambas.
2. Revisar columnas y unidades antes de aplicar una importacion. Se admite
   velocidad mph/kmh, movimiento in/cm y liberacion ft/m; eje en grados.
3. Completar las fisicas requeridas. En perfiles promedio, el uso debe sumar
   100%; `n` es opcional y declarado. En datos individuales, cada fila pesa uno.
4. Seleccionar tipos en el mapa o tabla y explorar diferencias respecto a la
   recta del mismo origen: velocidad, IVB, HB y distancia de liberacion.
5. Evaluar el arsenal, revisar scores, cobertura y distribucion individual
   cuando corresponde. Fijar hasta dos escenarios en la mesa de comparacion.
6. Elegir manualmente el siguiente paso, escribir una prueba de bullpen y
   guardar una ficha local o exportar JSON.

Las importaciones admiten hasta 1000 filas y 2 MB por candidato. No se truncan
archivos silenciosamente. Las columnas no mapeadas permanecen vacias; los
campos requeridos ausentes bloquean la evaluacion. Mano y origen compartidos
son elecciones explicitas cuando no vienen en el archivo. Las plantillas son
sinteticas y se identifican como tales.

Convertir lanzamientos a promedios crea un escenario diferente y descarta su
variabilidad para esa evaluacion; el original se conserva para restauracion.
El eje se promedia circularmente. El usuario tambien puede conservar una
captura manual como original. No se reconstruye IVB/HB al cambiar spin.

## Referencia y modelos

`GET /api/v1/profiler/reference?season=2025-2026&hand=Right` devuelve conteos
por temporada, exclusion por fisicas incompletas/fuera de rango, cuantiles
P10/P25/P50/P75/P90 por tipo/mano y una muestra visual de hasta 30 puntos por
tipo. Se usa el run validado de `data/CURRENT`, o `DIABLOS_RUN`. Las categorias
de altitud se mezclan en esta referencia descriptiva. Estar por encima de un
percentil fisico no equivale a ser mejor. Los puntos de referencia no tienen
scores ficticios.

`POST /api/v1/profiler/evaluate` recibe:

```json
{
  "mode": "profiles",
  "target": "Extreme Altitude",
  "entries": [
    {
      "key": "perfil-1",
      "weight": 100,
      "observed_n": null,
      "pitch": {
        "auto_pitch_type": "Four-Seam",
        "pitcher_throws": "Right",
        "altitude_category": "No Altitude",
        "rel_speed": 93,
        "spin_rate": 2350,
        "spin_axis_sin": 0.5,
        "spin_axis_cos": -0.8660254037844386,
        "rel_height": 6,
        "rel_side": 1.8,
        "extension": 6.2,
        "induced_vert_break": 15,
        "horz_break": 8
      }
    }
  ]
}
```

No se permite inyectar historia de pitcher ni variables de arsenal. Se evalua
Stuff fisico F8 en origen y con el movimiento proyectado por F10. Las relaciones
del repertorio son descriptivas: no se inyectan en F11 como historia observada.
No se inventan ubicacion, conteo, bateador ni Pitch Value+ para un candidato.

El resumen de origen usa todos los scores disponibles; origen pareado,
destino y delta usan exactamente el mismo subconjunto con soporte. La cobertura
se pondera por uso en perfiles y por cantidad de filas en modo individual.
No se reetiqueta el indice contextual F10 como Stuff+. Intervalos individuales
permanecen nulos. Un score del pitch promedio no equivale a la media de scores.
Los percentiles de scores individuales son descriptivos, no intervalos.

## Estados y persistencia

- El perfilador abre aunque siga cargando la muestra global de lanzadores.
- Errores de referencia conservan el editor; errores de inferencia no generan
  estimaciones sustitutas.
- Respuestas obsoletas se descartan. Editar despues de evaluar marca los
  resultados como desactualizados y retira proyecciones que ya no corresponden.
- Las fichas se guardan solo en localStorage de este navegador (hasta ocho).
  Errores de cuota se notifican sin borrar trabajo. JSON permite exportacion.
- Al restaurar una ficha no se reutilizan scores archivados como vigentes.
  La exportacion conserva original, escenario, notas y procedencia.

El precalculo del backend usa lotes de 2048 filas y libera el bloqueo de
inferencia entre lotes. Un bloqueo separado evita recalculos concurrentes de
un mismo frame. No cambia modelos, orden de filas ni normalizacion.

## Verificacion

```sh
npm --prefix altura-plus run build
npm --prefix altura-plus test -- --watch=false --browsers=ChromeHeadless
python -m unittest discover -s tests -v
```

Las pruebas del perfilador cubren importacion, conversion de unidades, campos
ausentes, manos mezcladas, pesos, eje circular, estados obsoletos, persistencia,
pareamiento del soporte, filtros 2025/2026 y nulos Arrow del dataset real.
