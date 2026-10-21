# AlturaPlus

## Rediseño editorial de MICTLAN

La navegación horizontal conecta las cinco herramientas. Los encabezados
compactos dan prioridad a los datos, sin bandas fotográficas antes del análisis.
El simulador presenta dos Stuff+ físicos en la misma escala y una lectura
principal basada en la física, no en la ubicación. En móvil,
los botones «Ajustar pitch» y «Ver resultado» permiten alternar sin recorrer
todo el formulario; los ajustes se conservan.

Análisis presenta los mapas antes de la tabla. Seleccionar un punto o usar las
flechas izquierda/derecha con el mapa enfocado actualiza el pitch inspeccionado.
Los perfiles de scouting y barras de uso conservan la comparación tabular.
La guía desplegable explica Stuff+, Pitch Value+, Location+, Pitching+, IVB, HB y xRV.
Azul representa valor favorable y ámbar desfavorable; los signos, textos y
formas complementan el color. El rojo queda como acento de marca.

El rediseño conserva modelos, unidades, contratos, límites de soporte y
distinción entre datos reales y demostración. Los recursos locales y licencias
se documentan en `public/images/README.md`.

## MICTLAN: cinco módulos

- `/dashboard`: índices de la muestra cargada, comparación observada por altitud,
  lanzadores y tipos destacados, hallazgos y alertas.
- `/lanzamientos`: filtros combinados, tabla paginada, scores y físicas por pitch,
  mapas de ubicación/movimiento y probabilidades del registro seleccionado.
- `/lanzadores`: listado, ficha, uso del arsenal, diferenciales respecto a la recta
  y contraste observado/experimental entre categorías de altitud.
- `/simulador`: físicas editables, Stuff+ físico en origen y destino proyectado,
  referencia del mismo tipo/mano con deciles y perfiles globales de scouting.
- `/perfilador`: candidatos con datos individuales o promedios por tipo,
  importación CSV/TSV/JSON con mapeo y unidades, editor del arsenal, comparación
  física por altitud, referencia LMB 2025/2026 y fichas de evaluación locales.

El perfilador puede abrir sin esperar a la carga global. Su referencia no usa
outcomes ni modifica modelos. Las relaciones del arsenal son descriptivas, sin
historia individual inventada; no hay un score automático de contratación.
Ver [recorrido, contrato y límites](../docs/PERFILADOR.md).

Las rutas antiguas redirigen a estos módulos. Se conserva la identidad visual de
MICTLAN. Las páginas antiguas permanecen como código de referencia, pero no están
en la navegación ni se cargan en el bundle de producción.

### Datos y límites

El backend se configura mediante `window.__DIABLOS_API__` o la clave
`diablos.api` de localStorage; por defecto usa `http://127.0.0.1:8001`.
Debe permitir el origen del frontend en `DIABLOS_CORS_ORIGINS`.
La carga obtiene hasta 130 perfiles del listado más una selección destacada,
en bloques progresivos.
Los indicadores del Dashboard y Análisis no son medias de toda la liga.
La ficha de lanzador y el arsenal usan los agregados completos de revisión 2025
que devuelve la API, no solo los pitches paginados.

No hay identificación de estadios ni altitud continua. `/simulate` devuelve
`stuff_comparison`: el mismo modelo físico congelado en origen y con IVB/HB
proyectados por el modelo de movimiento. No se reetiqueta el índice contextual
de altitud como Stuff+ ni se modifica la escala. El intervalo individual
permanece nulo: no se ha estimado la incertidumbre de esta composición.
Los diagnósticos de ubicación/xRV y el índice contextual se pueden desplegar.
Durante el recálculo se conserva el escenario anterior, con sus inputs y etiquetas
originales y un aviso de desactualización; entradas inválidas o modo demo lo retiran.
La interfaz usa
nombres deportivos en lugar de los identificadores internos de los modelos.
El perfil global de altitud es evidencia precomputada: se destaca el tipo editado,
pero sus números no se personalizan ni se invierten para un trayecto distinto.
Los rankings del dashboard exigen 120 scores físicos finitos después de filtrar.
El mapa del simulador usa solo referencia 2025, mismo tipo y mano; calcula deciles
en toda la referencia cargada y representa hasta 360 puntos más el pitch diseñado.

Las probabilidades individuales se consultan con la familia `pitching` de
`/api/v1/predict` cuando el bundle incluye ubicación, conteo y lado completos;
en caso contrario se utiliza la familia física, sin inventar contexto.
El score con arsenal se llama **Pitch Value+** en producto, se consulta aparte
en `/api/v1/final-score` y permanece
experimental, con escala propia y cobertura explícita. Sin artefactos verificados
no se sustituye por los índices base. El modal ordena los targets y conserva su
procedencia; xRunValue validado sigue no disponible, separado del xRV aproximado
MLB 2014 que se muestra en el simulador. Swing fallido se expresa por pitch;
contacto débil (proxy) y rodado están condicionados a bola en juego. No hay
probabilidad de elevado. Las cabezas no disponibles conservan valores nulos.
Se muestra la procedencia de cada cabeza condicional; una prevalencia de
entrenamiento suavizada nunca se presenta como una predicción individual.
Sin backend, los datos de demostración están identificados y el simulador no
produce scores heurísticos ni recomendaciones ficticias.
El campo técnico `stuff_final` se conserva por compatibilidad. La tabla fija
el número y Pitch Value+ al desplazar horizontalmente; las siete columnas
físicas adicionales se muestran con un botón.

### Verificación

```sh
npm run build
npm test -- --watch=false --browsers=ChromeHeadless
```

This project was generated using [Angular CLI](https://github.com/angular/angular-cli) version 19.2.16.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Karma](https://karma-runner.github.io) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
