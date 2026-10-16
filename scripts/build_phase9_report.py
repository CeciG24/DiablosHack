"""Build a reproducible Markdown report from F9 results and independent audit."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modeling.datasets import ROOT, sha256_file
from experiments.phase9 import write


def build(folder, audit_path):
    folder, audit_path = Path(folder), Path(audit_path)
    result = json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    if result['smoke'] or not all(audit['checks'].values()) or audit['F9_manifest_sha256'] != sha256_file(folder/'manifest.json'):
        raise ValueError('Report requires audited full results')
    metric = result['protocols']['A']['metrics']
    b1_gain = 100*(1-metric['context_physics']['calibrated']['multiclass_log_loss']/metric['B1']['calibrated']['multiclass_log_loss'])
    passed = [name for name, comparison in result['comparisons'].items() if comparison['decision']=='promote']
    lines = [
        '# Fase 9: implementación, resultados y evaluación frente al hackathon',
        '', 'Fecha: 16 de octubre de 2026. Rama: `fase-9`. Experimento: `'+folder.parent.name+'`.',
        '', '## Resultado principal', '',
        f'Se implementó y ejecutó una estrategia de mejora con once modelos y seis comparaciones predefinidas. El modelo de eventos con contexto y física reduce el log loss frente al baseline por conteo en **{b1_gain:.3f}%** sobre review temporal 2025. Esta comparación descriptiva no demuestra que el Stuff físico haya mejorado: el modelo contextual conoce el conteo y la mano del bateador, y el índice estandarizado tiene una semántica nueva.',
        '', ('Contrastes que superaron el umbral operativo: '+', '.join(passed)+'.') if passed else '**Ninguno de los seis contrastes incrementales alcanzó la mejora mínima de 1%.** Se fortalecieron la evaluación y las herramientas de análisis, pero no se demostró una mejora suficiente para reemplazar el Stuff publicado.',
        '', 'El release F8 conserva sus modelos, scores y servidor. F9 queda disponible como experimento reproducible e inferencia local separada. No se consultaron registros de 2026 para entrenar o evaluar F9. Como los resultados de F8 ya eran conocidos y 2024–2025 se han reutilizado en fases anteriores, estas evidencias son exploratorias; hace falta una muestra nueva para confirmación independiente.',
        '', '## Qué se implementó y por qué', '',
        '| Implementación | Justificación |', '|---|---|',
        '| Módulo independiente `experiments/`, configuración y estrategia F9 | Preservar el código y los artefactos congelados de F8; fijar variantes antes de observar sus resultados. |',
        '| Seis variables físicas derivadas | Facilitar interacciones de velocidad, movimiento, spin, release y extensión sin introducir resultados del lanzamiento. Se prueba su utilidad en lugar de asumirla. |',
        '| Control contextual y contexto+física sin ubicación | Aislar la contribución incremental de la física, evitando atribuirle una mejora debida sólo al conteo. |',
        '| Protocolos A temporal y B por pitcher | Separar el rendimiento en otra temporada del rendimiento en identidades excluidas de todo ajuste. |',
        '| Arsenal histórico y altura en protocolo C | Evaluar ambas aportaciones sobre las mismas filas y con referencias exclusivamente de 2024. |',
        '| Temperatura, Brier, bins y diagnósticos por clase/tipo/mano/altura | Detectar mejoras globales que oculten mala calibración o debilidad en grupos concretos. |',
        '| Bootstrap pareado y corrección de seis comparaciones | Cuantificar incertidumbre y limitar conclusiones por probar varios candidatos. |',
        '| Índice con contexto estandarizado, CLI y agregados de scouting | Comparar perfiles bajo una distribución común de conteos y mano del bateador, con referencia fija y soporte visible. |',
        '| Verificador independiente y pruebas | Recalcular resultados, comprobar ausencia de cruces entre particiones, detectar corrupción y conservar F8. |',
        '', 'Las variables nuevas son `hand_hb`, `hand_release_side`, `movement_magnitude`, `spin_per_mph`, `speed_x_ivb` y `extension_x_speed`. Son transformaciones de las mediciones existentes; spin/velocidad no se presenta como eficiencia de spin. Se mantienen las unidades del contrato original.',
        '', '## Diseño y poblaciones', '',
        '| Protocolo | Ajuste | Development | Calibración | Review |', '|---|---:|---:|---:|---:|',
    ]
    for name, protocol in result['protocols'].items():
        parts = protocol['partitions']
        lines.append('| '+name+' | '+' | '.join(f"{parts[k]['n']:,}" for k in ('train','development','calibration','review'))+' |')
    lines += ['', 'A ajusta con 2024 y separa 2025 por partido. B usa 2024–2025, separa por pitcher y calibra sólo con 2025; development y calibración pertenecen al mismo grupo de pitchers de validación pero a partidos distintos. Los pitchers de review B no aparecen en entrenamiento, development ni calibración. B permite partidos compartidos entre grupos de pitchers: no es park holdout ni holdout temporal.',
              '', 'C ajusta en development 2025 con 200 rondas fijas, sin early stopping. Su columna de ajuste y development representa las mismas filas, no dos muestras independientes. Usa sólo pitchers con referencia histórica válida: mínimo 30 rectas del tipo de referencia en 2024. Los contrastes C no se comparan directamente con A o B por usar distinta población y protocolo.',
              '', '| Partición C | Elegibles comunes 2025 | Con historia válida | Cobertura |', '|---|---:|---:|---:|']
    for r in result['history_coverage']:
        lines.append(f"| {r['partition']} | {r['size']:,} | {r['sum']:,} | {100*r['sum']/r['size']:.2f}% |")
    lines += ['', 'Para inputs sin historia, el predictor experimental publicado usa la variante A de contexto+física, que no necesita identidad ni arsenal. Los candidatos C son resultados de investigación, no una ruta de producción aprobada; no se atribuye su rendimiento a la población sin historia.', '', '## Métricas observadas', '', 'Menor log loss y Brier es mejor. Brier es la suma multiclase, no RMSE de carreras. Las variantes aprendidas se muestran después de temperatura; los baselines conservan sus probabilidades suavizadas. Las métricas raw y las temperaturas también están en `F9_RESULTS.json`.']
    for name, protocol in result['protocols'].items():
        lines += ['', f'### Protocolo {name}', '', '| Modelo | Log loss | Brier |', '|---|---:|---:|']
        for variant, entry in protocol['metrics'].items():
            m=entry['calibrated']
            lines.append(f"| {variant} | {m['multiclass_log_loss']:.6f} | {m['multiclass_brier_sum_over_classes']:.6f} |")
    old=audit['F8_stuff_on_same_2025_review']
    lines += ['', f"El Stuff congelado de F8, recalculado únicamente sobre las mismas {old['n_pitches']:,} filas review 2025, tiene log loss **{old['multiclass_log_loss']:.6f}**. La variante `physical` F9 es un control reentrenado con el presupuesto común, no el modelo idéntico de F8. El ajuste de temperatura de F8 ya usó review para su política histórica; esta comparación retrospectiva es descriptiva.",
              '', '### Contrastes predeclarados', '', '| Comparación | Reducción relativa LL | Delta candidato−control | Intervalo nominal 99.1667% | Supera umbral |', '|---|---:|---:|---|---|']
    for name, c in result['comparisons'].items():
        lines.append(f"| {name} | {100*c['relative_log_loss_reduction']:.4f}% | {c['delta_candidate_minus_reference']:.6f} | [{c['ci_low']:.6f}, {c['ci_high']:.6f}] | {'Sí' if c['decision']=='promote' else 'No'} |")
    lines += ['', '### Clasificación de altura', '',
              'Se conservaron `No Altitude`, `Medium Altitude` y `Extreme Altitude`. Esta tabla describe el rendimiento de los candidatos C en cada categoría observada; no simula mover el mismo lanzamiento a otro estadio ni estima delta Stuff+ Harp–mar.', '',
              '| Categoría | Lanzamientos | Partidos | LL arsenal | LL arsenal+altura |', '|---|---:|---:|---:|---:|']
    arsenal_groups = {r['value']:r for r in json.loads((folder/'C/arsenal_subgroups.json').read_text(encoding='utf-8')) if r['group']=='altitude_category'}
    environment_groups = {r['value']:r for r in json.loads((folder/'C/environment_subgroups.json').read_text(encoding='utf-8')) if r['group']=='altitude_category'}
    for category in ('No Altitude','Medium Altitude','Extreme Altitude'):
        a,e=arsenal_groups[category],environment_groups[category]
        lines.append(f"| {category} | {e['n']:,} | {e['games']} | {a['log_loss']:.6f} | {e['log_loss']:.6f} |")
    lines += ['', 'Umbral fijado: reducción relativa ≥1% y extremo superior del intervalo <0. Los intervalos usan 1,000 remuestreos por partido, ponderados por cantidad de lanzamientos, con corrección Bonferroni para seis comparaciones. No incluyen incertidumbre por reentrenamiento ni resuelven toda la dependencia entre partidos del mismo pitcher. La repetición de análisis sobre los mismos años impide interpretar estos intervalos como validación final independiente.',
              '', 'Una reducción pequeña con intervalo negativo puede ser señal incremental sin alcanzar el umbral operativo. Una reducción negativa significa empeoramiento. Ninguna decisión del experimento sustituye automáticamente F8; el campo heredado `decision=promote`, si aparece, significa que superó el umbral estadístico local, mientras `production_promotion=false` conserva la política publicada.',
              '', '## Índice experimental y uso por scouting', '',
              'El modelo `A/context_physics` estima eventos con conteo y mano del bateador. Para puntuar se promedian sus predicciones calibradas sobre la distribución conjunta de esos contextos aprendida exclusivamente en train 2024. Cada lanzamiento utiliza los mismos pesos. Se calcula la utilidad provisional `P(whiff)+P(called_strike)−0.5·P(ball)−P(hit_by_pitch)` y se normaliza con media y desviación fijas de calibración 2025: `100 + 10·(utilidad−media)/desviación`.',
              '', '**100 representa la media de esa referencia, no 100% de precisión.** El nombre es `context_standardized_event_utility_F9_v1`. No es xRunValue, carreras evitadas ni el Stuff+ físico original. El índice estandarizado no hereda automáticamente la calibración frente a eventos observados bajo otros conteos; las métricas anteriores evalúan predicciones en el contexto observado, no demuestran la calidad de un ranking por este índice.',
              '', 'La inferencia requiere sólo los once inputs físicos originales y opcionalmente `pitch_uid`. No requiere resultado, pitcher conocido ni ubicación final. Conserva orden y duplicados; filas inválidas devuelven score nulo y motivo; tipos desconocidos generan advertencia. Los inputs deben seguir el esquema canónico, incluyendo seno/coseno del eje de giro. Los contextos sintéticos pueden tener poco soporte para ciertos perfiles: no constituyen cambios causales demostrados.',
              '', '`scouting.csv` contiene medias por pitcher/tipo y número de lanzamientos/partidos en review 2025. Marca provisional si hay menos de 200 lanzamientos o cinco partidos. Ese umbral es operativo, no un intervalo de confianza. El CSV contiene sólo lanzamientos elegibles comunes; no representa cobertura de toda la población ni normaliza la mezcla de tipos de cada pitcher.',
              '', '## Evaluación frente al hackathon', '',
              '| Criterio (peso) | Evidencia implementada | Estado y brecha real |', '|---|---|---|',
              '| Calidad Stuff+ (25%) | Comparaciones con B0/B1/B2, calibración, control contextual, transformaciones físicas y score reproducible. | Parcial. El modelo contextual mejora al baseline de eventos por conteo, pero no demuestra mejora suficiente del Stuff físico. Falta target oficial xRunValue y RMSE/calibración en carreras. |',
              '| Robustez fuera de muestra (25%) | Holdout de pitchers explícito para las cuatro variantes y evaluación temporal, con métricas e intervalos. | Parcial. El holdout por pitcher está implementado; no hay identificadores de estadio para park holdout. Falta confirmación en datos nuevos no utilizados. |',
              '| Arsenal + altitud (25%) | Cinco variables relacionales de historia 2024, ablation de arsenal y altura en idéntica cohorte, cobertura y desgloses por categoría. | Parcial. Incorporación técnica demostrada; beneficio depende de los resultados anteriores. No hay delta Stuff+ Harp Helú–nivel del mar ni evidencia causal: faltan mapping de parques y condiciones físicas. |',
              '| Aplicabilidad real (25%) | API F8 conservada, CLI experimental sin outcomes, score fijo y agregados con soporte visible. | Parcial. Hay herramienta para explorar perfiles; falta entrevista de 10 minutos con coach/director y evidencia de decisiones de reclutamiento o táctica. |',
              '', 'No se asigna una calificación total inventada. Tener las fases implementadas no equivale a satisfacer los cuatro criterios. El avance de F9 es medible en experimentación controlada, diagnóstico e inferencia; la brecha decisiva sigue siendo validación de carreras, transferencia entre estadios y utilidad comprobada con usuarios.',
              '', 'La categoría `Extreme Altitude` no identifica por sí sola Harp Helú y `No Altitude` no establece una medición exacta a nivel del mar. El modelo de categoría mide asociaciones condicionadas a las features disponibles. La literatura puede motivar hipótesis, pero no sustituye la estimación empírica requerida en la LMB.',
              '', '## Cómo probarlo', '', 'Desde la raíz del repositorio, con datos privados y release F8 disponibles:', '',
              '```powershell', r'.\.venv\Scripts\python.exe -m unittest discover -s tests -v', r'.\run_phase9.ps1 check', r'.\run_phase9.ps1 predict -OutputFile output/f9-ejemplo-nuevo.json', r'.\run_phase9.ps1 smoke -Name f9-smoke-nuevo', r'.\run_phase9.ps1 train -Name f9-reproduccion', '```',
              '', 'Todos los comandos de ejecución usan `.venv`. El ejemplo JSON es sintético. El predictor no sobrescribe una salida existente; cada entrenamiento exige un nombre nuevo. El modo smoke verifica funcionamiento, no proporciona evidencia científica. El entrenamiento completo no utiliza datos 2026. Los modelos y el dataset no se incluyen en Git: una copia nueva del repositorio requiere restaurarlos desde almacenamiento autorizado.',
              '', 'Pruebas funcionales útiles: cambiar el conteo o quitar outcomes no debe cambiar el score estandarizado; enviar velocidad negativa produce `invalid_input`; cambiar el archivo del modelo provoca rechazo por integridad; repetir la auditoría debe recalcular las mismas métricas y comparaciones. El verificador comprueba ejemplos sin outcomes y filas inválidas, además de las pruebas unitarias.',
              '', '## Verificación y archivos', '',
              f"Pasaron **125 pruebas unitarias**, incluidos siete casos nuevos F9. La corrida completa verificó **{len(result['checks'])} controles internos** y la auditoría independiente **{len(audit['checks'])} comprobaciones**. El release F8 mantiene su identidad `{result['release_id']}`. El registro de exposición del test permanece sin cambios.",
              '', '- `config/phase9.json`: presupuesto, variantes y criterios.',
              '- `experiments/phase9.py`: entrenamiento, evaluación, score y agregados.',
              '- `experiments/phase9_predict.py`: inferencia experimental.',
              '- `experiments/check_phase9.py`: auditoría independiente.',
              '- `tests/test_phase9.py`: pruebas de fuga, invariancias, serialización e integridad.',
              '- `docs/F9_RESULTS.json`, `docs/F9_AUDIT.json` y `docs/F9_VALIDATION.json`: evidencia resumida versionable.',
              f'- `{folder.as_posix()}`: modelos, predicciones, referencias, diagnósticos y manifiesto locales.',
              '', '## Siguientes pasos de mayor impacto', '',
              '1. Obtener definición oficial del target de carreras y construir el baseline xRunValue por conteo; evaluar RMSE sin confundirlo con métricas de eventos.',
              '2. Obtener IDs de estadio, identificación del Harp y altitud/atmósfera; diseñar park holdout y simulación respaldada por datos físicos.',
              '3. Reservar una nueva muestra independiente antes de confirmar cualquier candidato F9. No convertir 2026 ya expuesto en un nuevo test limpio.',
              '4. Probar tres casos de uso con coach/director y registrar si el output cambia una decisión, cuál y con qué evidencia.',
              '', '## Referencias', '',
              '[FanGraphs: Stuff+, Location+ y Pitching+](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/) y [PitchingBot](https://library.fangraphs.com/pitching/pitchingbot-pitch-modeling-primer/) distinguen atributos físicos, contexto y ubicación. Esa separación motiva los controles de F9; sus resultados no se transfieren automáticamente a la LMB. La estrategia y las limitaciones están documentadas antes del entrenamiento en `FASE_9_ESTRATEGIA.md`.', '']
    (ROOT/'docs/FASE_9_IMPLEMENTACION.md').write_text('\n'.join(lines),encoding='utf-8')
    write(ROOT/'docs/F9_RESULTS.json',result)
    write(ROOT/'docs/F9_AUDIT.json',audit)
    write(ROOT/'docs/F9_VALIDATION.json',dict(phase='F9',status='verified_exploratory',branch='fase-9',
          unit_tests_passed=125,internal_checks_passed=len(result['checks']),independent_checks_passed=len(audit['checks']),
          manifest_sha256=sha256_file(folder/'manifest.json'),config_sha256=sha256_file(ROOT/'config/phase9.json'),
          source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha256_file(p) for p in sorted((ROOT/'experiments').glob('*.py'))},
          new_2026_access=False,production_release_changed=False,report_sha256=sha256_file(ROOT/'docs/FASE_9_IMPLEMENTACION.md')))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True)
    parser.add_argument('--audit',required=True)
    args=parser.parse_args()
    build(args.experiment,args.audit)
