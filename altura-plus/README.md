# AlturaPlus

## MICTLAN: cuatro módulos

- `/dashboard`: índices de la muestra cargada, comparación observada por altitud,
  lanzadores y tipos destacados, hallazgos y alertas.
- `/lanzamientos`: filtros combinados, tabla paginada, scores y físicas por pitch,
  mapas de ubicación/movimiento y probabilidades del registro seleccionado.
- `/lanzadores`: listado, ficha, uso del arsenal, diferenciales respecto a la recta
  y contraste observado/experimental entre categorías de altitud.
- `/simulador`: físicas editables, evaluación del pitch, escenario de origen y
  destino, comparación de candidatos del arsenal y recomendaciones de scouting.

Las rutas antiguas redirigen a estos módulos. Se conserva la identidad visual de
MICTLAN. Las páginas antiguas permanecen como código de referencia, pero no están
en la navegación ni se cargan en el bundle de producción.

### Datos y límites

El backend se configura mediante `window.__DIABLOS_API__` o la clave
`diablos.api` de localStorage; por defecto usa `http://127.0.0.1:8001`.
Debe permitir el origen del frontend en `DIABLOS_CORS_ORIGINS`.
La carga mantiene la muestra de hasta ocho lanzadores del frontend existente;
los indicadores del Dashboard y Análisis no son medias de toda la liga.
La ficha de lanzador y el arsenal usan los agregados completos de revisión 2025
que devuelve la API, no solo los pitches paginados.

No hay identificación de estadios ni altitud continua. Los índices de evaluación
y el score experimental de simulación tienen escalas distintas. La interfaz usa
nombres deportivos en lugar de los identificadores internos de los modelos.
El perfil global de altitud es evidencia precomputada y no responde a los filtros
de la muestra ni al pitch editado.

Las probabilidades individuales se consultan con la familia física de
`/api/v1/predict`: el bundle no incluye conteo ni lado del bateador por registro,
por lo que no se inventa ese contexto. Swing fallido se expresa por pitch;
contacto débil (proxy) y rodado están condicionados a bola en juego. No hay
probabilidad de elevado. Las cabezas no disponibles conservan valores nulos.
Se muestra la procedencia de cada cabeza condicional; una prevalencia de
entrenamiento suavizada nunca se presenta como una predicción individual.
Sin backend, los datos de demostración están identificados y el simulador no
produce scores heurísticos ni recomendaciones ficticias.

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
