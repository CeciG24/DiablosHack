# Contrato de datos y decisiones de preparación

## Alcance

Se prepara la representación Parquet entregada en el ZIP. No se ejecuta el pickle y no se
afirma equivalencia binaria o semántica con RDS. La unidad es un lanzamiento, identificado por
`pitch_uid`. Todas las tablas de nivel pitch preservan una fila por ID. `source_row_number`
permite volver a la fila original y no demuestra orden temporal.

## Tablas

| Tabla | Unidad y propósito |
|---|---|
| pitches | 635,002 filas con columnas fuente en snake_case, tipos normalizados y valores fuera de reglas de revisión puestos en nulo |
| features | Variables candidatas físicas, de ubicación y ambiente; sin resultados |
| targets | Etiquetas canónicas provisionales y objetivos condicionales; los nulos son explícitos |
| quality_flags | Banderas de problemas y elegibilidad por uso, una fila por pitch |
| quality_issues | Una fila por problema detectado; un pitch puede tener varios |
| splits | Particiones temporales, por pitcher, folds de partido y grupo ambiental |
| arsenal_features | Diferenciales calculados solo con temporadas anteriores y estado de cobertura |
| arsenal_references | Una referencia de recta por pitcher y año objetivo cuando hay al menos 30 observaciones históricas completas |

`data_catalog.csv` describe columnas, tipos, faltantes, roles y conjuntos de features.
`source_dictionary.csv` conserva las definiciones originales y su correspondencia de nombres.
Las recomendaciones del diccionario original no sustituyen a las listas explícitas de features.
Las columnas fuente `is_*`, resultados y mediciones de batazo en `pitches` siguen siendo datos
de auditoría. Las etiquetas para entrenar son exclusivamente las columnas `y_*` de `targets`.

## Limpieza sin pérdida de trazabilidad

Los originales extraídos son copias verificadas del ZIP. La capa preparada convierte
EffectiveVelo a número, homogeneiza textos, conserva categorías de pitch raras y convierte
Undefined/Switch en mano/lado desconocido cuando no se puede determinar el lado real del pitch.
No se infiere la mano faltante a partir del resto de temporadas.

Los límites en `config/data_contract.json` son reglas operativas conservadoras de revisión,
no leyes físicas ni umbrales optimizados con prueba. Valores fuera de esos límites se ponen
en nulo en la copia limpia. No se eliminan lanzamientos completos. Para movimiento se usa
un límite de ±40 pulgadas, extensión de 0 a 10 pies y otros rangos amplios documentados.
Pueden perderse observaciones físicamente posibles; por eso se preservan originales y banderas.
Un modelo sensible debe comparar el resultado con y sin esas reglas usando validación.

PlateLocHeight=0 se conserva y se excluye por defecto de Location+/Pitching+ hasta confirmar
si es truncamiento o codificación. No se recalcula la zona porque faltan límites individualizados
del bateador. El target de chase usa la definición de zona suministrada y omite ubicaciones cero.
Outs=3 antes del pitch se vuelve nulo. No se rellenan faltantes con cero, medias globales ni datos
de temporadas futuras. No se estandariza ni se codifican categorías con estadísticas del test.

## Política de etiquetas

PitchCall es la fuente provisional del evento de un lanzamiento. Se agrupan BallCalled y
BallinDirt como ball; las tres clases de foul como foul; y se mantienen called_strike, whiff,
in_play y hit_by_pitch. Undefined queda nulo.

La bandera original de golpeado está siempre en cero. Se deriva una nueva etiqueta a partir
de PitchCall cuando play_result no la contradice. Se preserva la bandera original sin corregirla
silenciosamente. Hay 22 golpeados cuyo play_result indica Walk y un StrikeCalled con Walk;
esos eventos se ponen en cuarentena. También se omiten los 450 StrikeSwinging marcados como
contacto y las dos discrepancias entre bandera de bola en juego y PitchCall. Las reglas se
solapan: sumar incidencias no equivale al número de pitches excluidos.

Se conservan `event_candidate` y las razones de revisión. `y_event` y las etiquetas derivadas
son nulas ante contradicción fuerte. Los siete InPlay con NeutralPlay conservan evento in_play,
pero no se usan para targets de hit o jonrón. No se ha adjudicado manualmente cada registro.

## Targets disponibles

| Target | Población y significado |
|---|---|
| y_event | Seis resultados mutuamente excluyentes por pitch con etiqueta confiable según la política provisional |
| y_swing, y_whiff, y_contact | Probabilidades por pitch; contacto incluye fouls |
| y_called_strike, y_ball_in_play, y_hit_by_pitch | Eventos por pitch |
| y_whiff_given_swing | Fallo únicamente entre swings válidos |
| y_called_strike_given_take | Strike cantado entre eventos válidos sin swing |
| y_chase_given_outside | Swing entre lanzamientos fuera de la zona suministrada y con ubicación utilizable |
| y_hard_contact_bip | ExitSpeed >=95 mph entre bolas en juego con medición |
| y_weak_contact_proxy_bip | ExitSpeed <75 mph entre bolas en juego con medición; proxy exploratorio, no estándar oficial |
| y_groundball_bip | GroundBall entre bolas en juego con tipo de batazo conocido |
| y_home_run_bip, y_hit_bip | Resultado reconocido entre bolas en juego |
| y_exit_speed_bip, y_launch_angle_bip | Mediciones continuas de batazo entre bolas en juego |

No se crean xRunValue, barrel, out dentro de una aparición al plato, spin efficiency, tunneling
real ni secuencia previa sin datos y definiciones suficientes. Las etiquetas de contacto son
condicionales: para una probabilidad por pitch se necesita combinarlas con P(in_play).

## Features y acceso seguro

La API `load_model_data` aplica una lista de variables según `stuff`, `location` o `pitching`.
Devuelve X separado de y y de los IDs. Stuff puro excluye ubicación, conteo, lado del bateador,
altitud y variables de trayectoria que puedan reconstruir ubicación. El tipo de pitch y mano
del pitcher son contexto físico explícito. Pitching incorpora ubicación, conteo, lado del bateador
y categoría de altitud. El eje de spin se representa con seno y coseno para respetar su circularidad.

Se conserva el signo original de HB y release lateral; se entrega mano del pitcher para permitir
su interpretación. No se impone una convención arm-side sin validar el sistema de coordenadas.
La API usa casos completos y los filtros de calidad de cada familia. La disponibilidad varía
por target y modelo; los reportes por año, tipo y altitud permiten medir sesgo de selección.
Imputaciones, escalado y codificadores deben ajustarse después y solo en entrenamiento.

## Particiones

- Temporal: 2024 train, 2025 validation, 2026 test. Un partido no cruza temporadas.
- Por pitcher: hash SHA256 estable con semilla del contrato, 70/15/15 esperado por ID.
  Un pitcher queda en una sola partición, pero partidos pueden compartir pitchers de distintos
  grupos. Es una prueba separada de generalización de jugadores, no una prueba cronológica
  ni de independencia por partido. No mezclar sus métricas con la prueba temporal.
- Partido: cinco folds deterministas, solo para usarlos dentro de un conjunto elegido previamente.
- Pitchers no vistos: 249 IDs de 2026 sin presencia en 2024/2025, 42,162 pitches. Su validez
  depende de que los organizadores confirmen estabilidad de IDs entre temporadas.
- Ambiente: se conserva la categoría para diagnósticos. No se entrega un park holdout falso.

La auditoría de calidad sí inspeccionó 2026; eso debe mencionarse al describir la evaluación.
No se ajustó ningún modelo con esos datos ni se eligieron hiperparámetros.

## Arsenal y ausencia de historia

Para cada año objetivo solo se usan años anteriores del mismo pitcher. Se elige la clase más
frecuente entre Four-Seam y Sinker con al menos 30 pitches completos en velocidad, movimiento
y release. Los empates se resuelven alfabéticamente, de forma determinista. Se calculan medias
de referencia, diferenciales de velocidad/IVB/HB y distancia de release. Esa distancia NO es
una medida completa de túnel. La frecuencia de uso proviene de todos los pitches históricos
del pitcher, sin etiquetas de resultado.

2024 no tiene historial previo y sus referencias permanecen nulas. En 2025 la referencia usa
2024; en 2026 usa 2024 y 2025. Por ello `load_model_data` no añade arsenal automáticamente.
Un modelo entrenado solo en 2024 no puede aprender esos diferenciales históricos ausentes.
El equipo deberá conseguir historia anterior, o definir un experimento de adaptación con
muestras de referencia separadas de las de evaluación. No rellenar 2024 usando 2025.
La tabla histórica está diseñada para el protocolo temporal, no para anexarla sin revisión
al holdout por pitcher. Los pitchers nuevos sin historia mantienen estado de referencia insuficiente.

## Operación y pruebas

La identidad de ejecución depende de SHA256 del ZIP, configuración, script de preparación y
versiones de pandas/numpy/pyarrow/duckdb. El manifiesto guarda además versión de Python, fecha
UTC, hashes y tamaños. Las salidas se escriben en una carpeta de construcción y se publican
mediante `data/CURRENT` solo después de validar. La base SQL materializa las tablas para poder
copiarla sin romper rutas. No hay servidor, credenciales ni sincronización externa.

`scripts/check_data.py` verifica hashes, integridad referencial, ausencia de contaminación
en features, particiones, poblaciones condicionales y antigüedad de arsenal; también prueba
consultas SQL y la API. `tests/test_preparation.py` cubre contradicciones, golpeados, faltantes
estructurales, valores fuera de rango, estabilidad de splits y no contaminación desde el futuro.

## Pendientes que requieren a los organizadores

Mapeo de partido a estadio anonimizado, indicador Harp, altitud en metros y límites de categorías;
fecha/orden e ID de aparición al plato; ocupación de bases y definición de run value; definición
de zona y ceros de altura; regla canónica ante etiquetas contradictorias; estabilidad de IDs y
periodo exacto de 2026. Estas ausencias limitan análisis específicos, no impiden empezar con
los targets y modelos definidos arriba.
