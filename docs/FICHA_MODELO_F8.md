# Ficha del modelo F8

Fecha: 13 de octubre de 2026.

Release: `f8-release-20261013`. ID: `4df11fbf516455a6c90c45bea2f780a3e2441a64f1c6f15a6e637c84c619ef64`.

## Uso previsto

Probabilidades de eventos por lanzamiento y utilidad exploratoria para análisis deportivo local. Pitching es la referencia; Location permite separar contexto/ubicación y Stuff es un diagnóstico físico. No usar como carreras esperadas, efecto causal de estadio, garantía de rendimiento ni decisión automática de contratación.

## Política y datos

Entrenamiento 2024; desarrollo, calibración y revisión 2025. Test temporal 2026 abierto una vez después del congelamiento. Se había perfilado su calidad previamente. Modelo LightGBM 4.6.0 en CPU; calibración escalar seleccionada en F4. Identificadores de pitcher y partido no entran como predictores.

La política es A/base; no se promovieron arsenal ni ambiente. La cabeza de contacto y chase de Stuff usa prevalencia de entrenamiento. Las demás cabezas conservan su política F4. S0 se normaliza con 59,367 IDs comunes de calibración 2025 y ddof=0, sin reescalar en test.

## Resultados 2026

Cohorte común: 130,053 de 135,604 filas (95.9065%).

| Modelo | Log loss | Brier multiclase |
|---|---:|---:|
| stuff | 1.536157 | 0.763166 |
| location | 1.038812 | 0.539553 |
| pitching | 1.023459 | 0.532800 |
| B1 | 1.486855 | 0.744793 |
| environment | 1.023417 | 0.532822 |

Pitching reduce log loss 1.4779% frente a Location y 31.1662% frente a B1 en este test. Stuff aumenta log loss 3.3159% frente a B1 y no debe presentarse como una mejora predictiva. El candidato ambiental tiene una diferencia diminuta cuyo intervalo incluye cero. Todas las comparaciones son descriptivas finales y no cambian el release.

## Cobertura, soporte y límites

La API requiere features completas por familia, sin outcomes. Los errores de entrada producen nulos; las categorías nuevas producen advertencias. Los límites marginales de entrenamiento son un control operativo, no garantía de soporte multivariado. Los grupos escasos se etiquetan con soporte insuficiente.

Estadio/Harp, altitud numérica, condiciones atmosféricas, PA/bases y valor oficial de carreras siguen pendientes. S0 no equivale al Stuff+ validado de FanGraphs. No se ofrecen intervalos individuales. Un nuevo desarrollo debe declarar que 2026 ya fue expuesto.

## Validación e integración

118 pruebas unitarias; 18 controles de paquete sobre 2025; auditoría independiente de métricas, intervalos, agregados y muestra de inferencia. Prueba HTTP local y ejemplo por archivo completados. Benchmark en F8_BENCHMARK.json: 1,000 filas, cuatro hilos, tres repeticiones calientes por familia; no incluye carga inicial ni red.

Ver FASE_8_IMPLEMENTACION.md para comandos y DIABLOS_INFORME_TECNICO_F8.pdf para la contribución de diez páginas y los tres casos con evidencia.
