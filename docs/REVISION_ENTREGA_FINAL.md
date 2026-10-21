# Comparación de entrega-final con el reto

Revisión: 20 de octubre de 2026. Rama descargada: `entrega-final`, commit `72f81b7`, con seguimiento de `origin/entrega-final`. Se partió de `backend` (`7ccd42d`) sin cambios locales.

## Alcance de la comparación

Se usan los requisitos y cuatro criterios de 25% transcritos en `MODELING_SYSTEM_CONTRACT.md`, `FASE_8_IMPLEMENTACION.md`, `PLAN_DE_IMPLEMENTACION.md` y `analysis/build_proposal.py`. No se encontró la convocatoria original en los archivos revisados; el ZIP local contiene datos y diccionario. Esta revisión no certifica equivalencia con una convocatoria externa ni estima puntos del jurado.

## Estado de entregables

| Requisito | Estado observado | Evidencia y límite |
|---|---|---|
| Stuff+, Location+, Pitching+ por lanzamiento, pitcher y arsenal | Implementado con escala provisional | F8 y endpoints predict/summary; las tres familias son distintas. La utilidad de eventos no equivale a xRunValue. |
| Dashboard y simulador para coach | Integración implementada; compilación local sin verificar | Angular en `altura-plus`, rutas dashboard/lanzamientos/lanzadores/simulador; cliente API y mapeadores. Sin backend cae a datos sintéticos identificados. El simulador consulta predict/simulate/recommendations. |
| Mapa de movimiento y consulta de repertorio | Implementado | Componentes de movimiento, fichas y agregados del backend. La carga inicial selecciona hasta ocho pitchers entre los candidatos de la API: no es una vista de toda la liga. |
| Comparación Harp Helú frente a nivel del mar | Parcial mediante categorías | F10 compara No/Medium/Extreme Altitude. No hay identificación del Harp, metros ni atmósfera: no demuestra el delta específico del estadio. |
| Perfil físico ideal y recomendaciones | Parcial, ya existen artefactos | `F10_IDEAL_PROFILE.json`, `phase10_profile.py`, endpoint profile y recomendaciones entre candidatos. Los 490 escenarios y resúmenes por tipo no prueban un óptimo global ni cierran todas las hipótesis H1–H4. |
| Evaluación fuera de muestra | Parcial sólido | Protocolos temporal y por pitcher, test F8 y holdout de categoría para IVB/HB. Falta park holdout real y holdout ambiental sobre eventos. |
| Documento técnico de 6–10 páginas | Existe informe F8; actualización final pendiente | `DIABLOS_INFORME_TECNICO_F8.pdf` y fuentes de generación; no se encontró un informe final que reúna frontend, F9/F10 y holdout de altitud. No se hizo revisión visual del PDF en esta auditoría. |
| Demostración de 10 minutos y casos de decisión | Pendiente de acreditar | Hay producto y casos históricos, pero no se encontró un guion final y evidencia de ensayo de la versión integrada. |

## Lectura de la rúbrica

| Criterio transcrito | Diagnóstico |
|---|---|
| Calidad del Stuff+ (25%) | Brecha crítica: falta objetivo xRunValue, RMSE de carreras y comparación oficial. El cierre F8 reporta que Stuff no supera el baseline de eventos; no se encontró evidencia nueva que revierta esa conclusión. |
| Robustez fuera de muestra (25%) | Hay evidencia temporal, por pitcher y por categoría de altura. El holdout nuevo evalúa movimiento; no sustituye al de estadio ni valida los deltas de score. |
| Arsenal + altitud (25%) | Avance importante en F9/F10 con arsenal regularizado y simulación de movimiento. Sigue siendo experimental y no forma parte de la política congelada F8. Sin efecto específico del Harp ni causalidad demostrada. |
| Aplicabilidad real (25%) | Es el avance más claro: interfaz conectada, análisis por pitch y recomendaciones. Falta comprobar build, recorrido completo en navegador y demo útil para un coach. |

## Verificación local realizada

- `python -m unittest tests.test_altitude_holdout -v`: **8/8 pasan**.
- Con `DIABLOS_INTEGRATION=1`, `python -m unittest tests.test_backend -v`: **11/11 pasan**, incluido `test_real_models`, fuera del sandbox. Los intentos dentro del sandbox se bloquearon y fueron detenidos; no se atribuye ese bloqueo al producto.
- La prueba real comprueba scores F8 y simulación F10, pero la prueba de pitchers/bundle usa fixtures. No acredita la carga completa de pitchers reales en el navegador.
- `npm ci --no-audit --no-fund`: primer intento falló por permisos; reintento fuera del sandbox falló por **ENOSPC (sin espacio)**. No se ejecutaron build ni tests Angular. Se solicitó limpiar únicamente el node_modules creado por estos intentos.
- No se reentrenaron modelos ni se hizo una nueva evaluación del test 2026.

## Riesgos concretos para ejecutar esta copia

1. **Rutas de datos distintas.** `data/CURRENT` local apunta a `c1c8ba48818dc878`; el contrato descargado espera `e9e0b1114dc68eb2`, que no está entre los runs locales. `test2026_frame()` usa ese último como ruta predeterminada. Debe configurarse `DIABLOS_RUN` con un run verificado compatible, o restaurar el run correspondiente. No cambiar contratos o hashes para aparentar compatibilidad. Que pase la inferencia F8/F10 no resuelve esta diferencia.
2. **Artefactos privados fuera de Git.** El checkout no garantiza que F9/F10 locales correspondan a la evidencia generada en otra computadora. Verificar manifests y endpoints pitchers/bundle reales antes de la demo.
3. **2026 ya está expuesto.** El bundle incluye 2026 por defecto (`include_2026=True`), aunque comentarios y README describen principalmente review 2025. Distinguir particiones en las pantallas y documentación. Las consultas exploratorias están registradas en `CONSULTA_2026_H3_H4.md`; no presentar 2026 como test independiente de futuras decisiones.
4. **Interpretaciones más fuertes que la evidencia.** El perfil precomputado habla de gyro, Magnus y riesgo HR. Los datos dan asociaciones categóricas y contacto fuerte; no identifican mecanismos ni estiman HR. Moderar esas conclusiones en el informe y demo.
5. **Checklist desactualizado.** El plan sigue marcando pendiente el perfil que ya está versionado. El README del frontend y la descripción OpenAPI también necesitan reflejar la lectura opcional/predeterminada de 2026.

## Orden recomendado para cerrar

1. Recuperar espacio, instalar dependencias, ejecutar build/tests Angular y recorrer la integración real con los artefactos locales y CORS configurado.
2. Conciliar versiones/rutas y verificar la carga real de pitchers, bundles y simulaciones; conservar trazabilidad.
3. Actualizar documento técnico final y checklist con evidencia F9/F10/holdout, perfil y límites de cada escala.
4. Preparar tres casos de decisión y ensayar la demo de diez minutos, con alternativa offline claramente marcada.
5. Presentar xRunValue, park holdout y delta específico del Harp como brechas justificadas por datos; el holdout de eventos sigue siendo trabajo posible pendiente.
