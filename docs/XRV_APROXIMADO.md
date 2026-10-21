# xRV aproximado con pesos externos

Implementado el 20 de octubre de 2026, versión `xrv_external_mlb2014_v1`.
Autorización: opción 2 solicitada por el equipo. Es una extensión de inferencia
en `backend/xrv.py`; no modifica código, modelos, calibradores ni escalas F8.

## Definición

Para cada familia de probabilidades y conteo explícito:

`xRV = Σ P(evento | entradas) × (wOBA_posterior(evento, conteo) − wOBA_conteo) / 1.304`.

Se expresa en carreras por pitch desde el ataque: **menor favorece al pitcher**.
Por 100 pitches es exactamente 100 veces ese valor, no una proyección por juego.
El simulador muestra la familia Pitching; la API devuelve las familias solicitadas.
La familia Stuff no recibe conteo como predictor físico: el conteo se usa después
para valorar sus probabilidades. Sin conteo explícito xRV queda nulo.

## Referencia externa congelada

Los insumos quedan versionados en `config/xrv_mlb2014.json`; la API informa su SHA-256.
La inferencia no descarga fuentes ni recalcula pesos según el lote.

- Expectativas por los doce conteos: [Dan Meyer, The Hardball Times, 2015, datos MLB 2014](https://tht.fangraphs.com/dynamic-run-value-of-throwing-a-strike-instead-of-a-ball/), columna Start de la tabla 2014.
- Conversión a carreras y pesos de eventos terminales: [FanGraphs Guts, fila 2014](https://www.fangraphs.com/tools/guts?type=cn).
- Mezcla de contacto: [MLB Stats API, totales de bateo de los 30 equipos, temporada regular 2014](https://statsapi.mlb.com/api/v1/teams/stats?stats=season&group=hitting&season=2014&sportIds=1). Se comprobaron 30 equipos y se sumaron los campos numéricos conservados en configuración.

Una bola avanza el conteo o termina en BB; un strike cantado/swing fallido avanza
el conteo o termina en K. Un foul ordinario con dos strikes vale cero; con menos
de dos equivale a un strike. HBP usa su peso terminal propio.

La bola en juego usa un promedio externo constante, incluyendo HR y sacrificios:

`contact_wOBA = (w1B×1B + w2B×2B + w3B×3B + wHR×HR) / (AB − K + SF + SH)`.

`1B = H − 2B − 3B − HR`. Los outs aportan cero al numerador. El resultado es
`0.3526053534975113`. Es una aproximación de contacto agregado, no un modelo de
EV/ángulo ni una estimación individual de HR. Conserva sacrificios para aproximar
la categoría amplia in_play del proyecto. No modela interferencia, foul bunt de
tercer strike, corredores, outs, estadio ni clima. La tabla publicada está
redondeada y el promedio de contacto no depende del conteo: no se impone media cero.

## API, baseline y alcance

- `GET /api/v1/xrv`: definición, pesos, fuentes, versión, hash y limitaciones.
- `POST /api/v1/predict`: cada familia agrega `xrv`, con valor, unidades,
  contribuciones por evento y referencia B1 por conteo, ajustada en 2024.
- `delta_vs_count_baseline = xRV_modelo − xRV_B1`; negativo favorece al modelo
  para ese pitch. Es una comparación de estimaciones, no evidencia de mejora predictiva.
- Un input inválido, conteo ausente o probabilidades incompletas deja xRV nulo.
- El simulador muestra estos valores junto a las escalas previas y distingue
  explícitamente el delta F10 de altitud, que permanece en puntos experimentales.

No se entrenó un target de carreras, no se recalibraron modelos con estos pesos y
no se hizo una nueva evaluación de 2026. Transferir MLB 2014 a LMB requiere validación.
Esto no demuestra el requisito oficial de xRunValue ni permite atribuir RMSE real
de carreras al modelo. La comparación contra resultados transformados sería una
evaluación de proxy y tendría que etiquetarse así.

## Entorno completo en D:

`powershell -ExecutionPolicy Bypass -File .\run_full.ps1`

El lanzador instala dependencias si faltan, deja dependencias, caché, temporales y
logs en `D:\CodexRuntime\DiablosHack`, configura CORS y usa el run local de
`data/CURRENT` para visualización, sin alterar contratos o manifests. Verifica
`/ready`, disponibilidad de pitchers F9 y respuesta del frontend antes de confirmar.
Necesita los artefactos privados existentes; no los descarga ni reentrena.
Guarda PIDs y URLs en `session.json`. Los procesos quedan activos en segundo plano.

Verificación local: build de producción correcto (advertencia preexistente de
presupuesto de CSS en app.component.scss), 18/18 pruebas Python con integración
F8/F10 y 31/31 Angular. Se comprobó la carga real de pitchers y la tarjeta xRV en
el navegador. Una ejecución posterior de las 7 pruebas xRV también pasó tras
hacer sus fixtures independientes de los artefactos privados.

Backend: `http://127.0.0.1:8001/docs`. Frontend: `http://127.0.0.1:4200/simulador`.
Para detenerlos, consultar `session.json` y detener únicamente sus PIDs vigentes.
