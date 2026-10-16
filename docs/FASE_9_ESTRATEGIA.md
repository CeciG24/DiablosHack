# Fase 9: protocolo exploratorio previo a las corridas

Fecha: 16 de octubre de 2026. Rama: `fase-9`.

## Diagnóstico y objetivo

F8 terminó la implementación interna, pero su evaluación no demuestra el cumplimiento completo del hackathon. Stuff físico no supera al baseline por conteo en eventos; este contraste mezcla diferencias de contexto y de información física. Arsenal y ambiente tampoco alcanzaron los criterios de promoción. F9 mide aportaciones incrementales mediante controles comparables. No se optimizará contra 2026, cuya evaluación ya fue expuesta.

## Experimentos fijados antes del entrenamiento

Configuración independiente: `config/phase9.json`. Una configuración de hiperparámetros, sin búsqueda posterior sobre review.

- A: entrenamiento 2024; development, calibración y review 2025 separados por partido, con las asignaciones del contrato original. Cuatro variantes: física original; física con seis transformaciones; contexto (tipo, manos y conteo); contexto más física transformada. Se reportan B0/B1/B2 sobre idénticas filas.
- B: las mismas cuatro variantes y baselines, con particiones por pitcher del contrato. Los pitchers de review no participan en ajuste, early stopping ni calibración. Calibración usa únicamente las filas 2025 del grupo de calibración. Es holdout de identidad, no temporal ni de estadio.
- C: historia fija 2024 y entrenamiento de 200 rondas en development 2025. Se comparan contexto+física, la misma variante con cinco variables de arsenal y esta última con categoría de altura. Las tres usan exactamente las mismas filas con historia válida. Se informa cobertura; no se extrapola el resultado a pitchers sin historia.

Transformaciones: movimiento horizontal y lado de release orientados por mano, magnitud del movimiento, spin/velocidad, velocidad×IVB y extensión×velocidad. Son representaciones deterministas de variables ya aprobadas; no medidas nuevas de eficiencia de spin, ni fórmulas físicas causales. No se incluyen ubicación final, resultado del contacto, ID del pitcher, estadio ni año como predictores.

La altura conserva las tres categorías originales. No equivale a identificar Harp Helú ni a medir metros o densidad del aire.

## Evaluación y decisión

Métrica primaria: log loss multiclase; secundaria: Brier. Temperatura ajustada sólo en calibración, sin elegir entre calibrada/raw usando review. Se guardan ambas métricas, curvas de diez bins, frecuencias por clase y desgloses por tipo, mano y altura.

Seis contrastes predeclarados: física transformada contra física original y contexto+física contra contexto en A y B; arsenal contra su control y ambiente contra arsenal en C. Bootstrap pareado por partido (1,000 remuestreos), con intervalos nominales Bonferroni de 99.1667% para seis comparaciones. Umbral operativo: reducción relativa ≥1% y límite superior del delta <0. La dependencia entre partidos del mismo pitcher sigue siendo una limitación del bootstrap por partido.

Incluso si un candidato supera ese umbral, queda como evidencia exploratoria posterior a exposición del test. No se reemplaza automáticamente F8. La variante física requiere mejora en A y B para recomendar su avance. Un resultado negativo también se publica.

## Producto implementable

Índice experimental: predicciones de contexto+física promediadas bajo la misma distribución conjunta de conteo y mano del bateador aprendida en 2024. Se fija una escala 100/10 con calibración 2025. El índice evita que el conteo de la consulta cambie la puntuación; sigue siendo una asociación dependiente del modelo y del soporte de los contextos. No es xRunValue, Stuff+ oficial ni evidencia causal. La mezcla de tipos de lanzamiento de cada pitcher sigue siendo la observada.

Se entregarán inferencia local, agregados de scouting con soporte visible, artefactos reproducibles y reporte contra la rúbrica. Los modelos y datos privados se mantienen fuera de Git.

## Límites que el código no puede resolver

Faltan target oficial de carreras, identificación de estadios/Harp, altitud numérica/atmósfera y nueva muestra final independiente. No se inventarán RMSE de carreras, park holdout ni delta Harp–mar. La utilidad para coaches requiere una prueba de decisiones con usuarios.

Fuentes metodológicas: [FanGraphs, Stuff/Location/Pitching](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/) y [PitchingBot](https://library.fangraphs.com/pitching/pitchingbot-pitch-modeling-primer/). Motivan separar física, contexto y ubicación y estudiar diferencias respecto a la recta; no validan este modelo específico de LMB.
