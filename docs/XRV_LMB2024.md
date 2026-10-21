# xRV aproximado con pesos LMB 2024

Versión activa: `xrv_external_lmb2024_v1`, 21 de octubre de 2026.
Base de trabajo: `entrega-final` en `bfdc863`, integración del rediseño MICTLAN y
score con arsenal. Se conservan los modelos y las escalas F8/F11. La referencia
MLB 2014 permanece en `config/xrv_mlb2014.json` para comparar, pero ya no es el default.

Antes de publicar se integró también `23a72fb` (perfilador y nuevo laboratorio de
simulación). Se conserva ese diseño y su conteo del último escenario evaluado.
Verificación posterior a la integración: build correcto, 39 pruebas de backend,
modelos y xRV, 4 del perfilador y 70 Angular. Se comprobaron los hashes de los
manifiestos y del constructor dentro del commit, además de la API activa.

## Fuente y cobertura

Calendario y feeds oficiales de MLB Advanced Media para **Mexican League (125),
sport 23, temporada regular**. El dominio statsapi.mlb.com hospeda registros de
LMB; el nombre del servidor no convierte estos partidos en datos de MLB.

- [Calendario LMB 2024](https://statsapi.mlb.com/api/v1/schedule?sportId=23&leagueId=125&startDate=2024-01-01&endDate=2024-12-31&gameType=R).
- [Ejemplo de feed LMB 2024](https://statsapi.mlb.com/api/v1.1/game/770511/feed/live).
- Manifiestos versionados: `XRV_LMB2024_SOURCE_MANIFEST.json` y
  `XRV_LMB2025_SOURCE_MANIFEST.json`, con URL y SHA-256 de cada respuesta original.
- Feeds comprimidos y manifiestos originales: `D:\CodexRuntime\DiablosHack\lmb-xrv`.
  No se agregan esos feeds ni datos privados a Git.

| Población | 2024: ajuste | 2025: diagnóstico separado |
|---|---:|---:|
| Partidos finales únicos descargados | 905 | 915 |
| Partidos con reconstrucción aceptada | 901 | 903 |
| PA en medias entradas completas de regulación | 69,111 | 71,518 |
| PA elegibles para pesos/conteos | 65,241 | 67,036 |
| Pitches en esas PA elegibles | 244,189 | 252,401 |

Se deduplican IDs del calendario (un partido suspendido/reanudado puede aparecer
más de una vez). Se aceptan solo Final/Completed Early y tipo R. Se verifican
liga de ambos equipos, año, secuencia de turnos, progresión de outs, carreras
por media entrada y marcador final. Cuatro partidos 2024 y doce 2025 se excluyen
por turnos incompletos/no secuenciales; sus IDs figuran en el reporte.

## Estimación en carreras, sin constantes MLB

1. Estimar `RE24(outs, bases)` con el promedio de carreras restantes en la media
   entrada, observado al inicio de cada PA de 2024. Se cubren los 24 estados;
   el estado con menor soporte tiene 122 observaciones. RE al tercer out vale cero.
2. Para cada PA, calcular `RV = carreras + RE24(después) − RE24(antes)`.
3. Estimar el valor medio de cada resultado terminal (single, double, out, BB,
   K, HBP, etc.). Eso marginaliza el contexto de bases/outs antes de modelar conteos.
4. Para cada conteo `c`, calcular `V(c)`: media del valor terminal anterior entre
   PA que pasaron por ese conteo. Cada PA cuenta una sola vez por conteo, aunque
   tenga varios fouls con dos strikes. El menor soporte es 2,913 PA.
5. Bola/strike no terminal: `w = V(conteo siguiente) − V(conteo previo)`.
   BB, K, HBP y contacto terminal: `w = valor terminal − V(conteo previo)`.
   El contacto se promedia por conteo con regularización fija de 30 PA hacia la
   media de su clase en 2024. Los fouls ordinarios con dos strikes valen cero.
6. Inferencia: `xRV = Σ P(evento | entradas del modelo) × w(evento, conteo)`.

No se imponen signos, no se ajusta con 2025 y no se usan wOBA/wOBAScale de MLB.
El resultado está en carreras por pitch desde el ataque: **menor favorece al
pitcher**. Multiplicar por 100 da carreras por 100 pitches, sin nueva normalización.

Se excluyen medias entradas incompletas (incluidas victorias walk-off) y extras;
no se asume que una entrada truncada tendría cero carreras futuras. Para pesos
y conteos se excluyen PA con avances/outs de corredores antes del pitch final,
cambios de conteo sin pitch, calls no mapeables y transiciones inconsistentes.
Esas PA pueden seguir aportando a RE24 si su marcador/estado final es coherente.
Los motivos de exclusión corresponden a pasos distintos y pueden solaparse.

Particularidad comprobada: muchos feeds incrementan el contador de bolas al
registrar HBP. Se reconoce el HBP como evento separado y se conserva el conteo
previo; no se interpreta como bola ni como BB. Hay una prueba específica.

## Diagnóstico 2025

Se aplican las mismas reglas a 2025 sin reajustar ningún peso. El artefacto
`config/xrv_lmb2024_validation.json` registra cobertura y transferencia de RE24.
El RMSE de carreras restantes de la tabla RE24 congelada es aproximadamente 1.214.
Para el valor terminal proyectado con pesos 2024, la referencia por conteo tiene
RMSE 0.4763, frente a 0.4813 usando siempre la referencia 0–0.

**Estas cifras no son RMSE del xRV de F8/F11**, ni validación del modelo de pitch.
Miden la referencia externa y su proyección de valores terminales. El cálculo y
diagnóstico de pesos no consulta 2026; la aplicación conserva su visualización e
inferencia de 2026 anterior, sin usarla para este ajuste. No se afirma que 2025 sea un nuevo test independiente de
los modelos del proyecto, que ya lo usaron en desarrollo.

## API e interfaz

- `GET /api/v1/xrv`: pesos, fuentes, método, soportes y SHA-256 del archivo activo.
- `POST /api/v1/predict`: xRV por familia F8 solicitada.
- `POST /api/v1/final-score`: xRV de las probabilidades F11, separado de su score.
- La respuesta incluye `reference_label`, `league`, `season`, versión, hash,
  contribuciones por evento y diferencia frente al B1 por conteo congelado de 2024.
- Sin conteo o probabilidades válidas devuelve nulo con motivo; no inventa 0–0.
- El simulador muestra la procedencia que devuelve la API. Su tarjeta usa
  probabilidades Pitching+ F8; el delta F10 de altitud sigue en puntos, no carreras.

## Límites

Es una aproximación que marginaliza contexto: no predice el RE24 individual ni
el efecto causal de un estadio. El contacto usa resultados medios por conteo,
no EV/ángulo de salida del pitch particular. Los outcomes de pitchers/bateadores
anónimos del hack no se vinculan a identidades públicas. No se valida Harp Helú,
no se agregan predictores/outcomes al modelo y no se cumple automáticamente un
target oficial del hackathon por cambiar la referencia de carreras.

## Reproducir

```powershell
.\.venv\Scripts\python.exe -m experiments.lmb_xrv download --year 2024 --root D:\CodexRuntime\DiablosHack\lmb-xrv
.\.venv\Scripts\python.exe -m experiments.lmb_xrv download --year 2025 --root D:\CodexRuntime\DiablosHack\lmb-xrv
.\.venv\Scripts\python.exe -m experiments.lmb_xrv build --root D:\CodexRuntime\DiablosHack\lmb-xrv --validation-year 2025
.\.venv\Scripts\python.exe -m unittest tests.test_lmb_xrv tests.test_xrv tests.test_backend tests.test_final_score -v
```

La descarga reusa archivos íntegros; el build verifica sus hashes. El año de
ajuste y cada fila de entrenamiento deben ser 2024. El código y los manifiestos
quedan identificados en el artefacto. Los pesos activos se pueden reproducir
desde la caché archivada; una descarga futura puede reflejar correcciones oficiales.
El método de expectativa de carreras sigue [la definición de RE24](https://library.fangraphs.com/misc/re24/).

## Verificación local y disponibilidad

Build de producción, 37 pruebas Python y 51 pruebas Angular correctos; se conserva una advertencia
de presupuesto CSS preexistente en la página de lanzamientos. Los tests Python
incluyen reconstrucción, signos/unidades de referencia histórica, pesos LMB,
procedencia, exclusiones, HTTP y regresiones del score con arsenal.

Backend y frontend permanecen activos. Se verificaron `/ready`, el SHA-256 del
artefacto servido y xRV LMB real para las tres familias F8. El artefacto privado
`artifacts/modeling/final-score-v1` no existe en esta copia: `/final-score`
responde 503 hasta restaurarlo. El adaptador F11 se verifica con probabilidades
sintéticas completas; no se presenta eso como inferencia real F11. No se reentrenó
F11 para cubrir esa dependencia ajena a los pesos.
