"""Build the ten-page technical contribution from the frozen evaluation evidence."""
import argparse
import json
from pathlib import Path
import sys
from html import escape


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release');parser.add_argument('--packages',help='Optional bundled reportlab/pypdf site-packages')
    args=parser.parse_args()
    if args.packages:sys.path.append(args.packages)
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from pypdf import PdfReader
    folder=Path(args.release);out=folder/'evaluation'
    def read(name):return json.loads((folder/name).read_text(encoding='utf-8'))
    lock=read('release_lock.json');m=read('evaluation/manifest.json')
    evidence=read('evaluation/metrics.json');subgroups=read('evaluation/subgroups.json')
    coverage=read('evaluation/coverage.json');cases=read('evaluation/scouting_cases.json')
    benchmark=read('benchmark.json');checks=read('pretest_checks.json')
    assert m['status']=='verified'
    target=Path('output/pdf/DIABLOS_INFORME_TECNICO_F8.pdf');target.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Caption',fontName='Helvetica',fontSize=8,leading=11,textColor=colors.HexColor('#526171')))
    styles.add(ParagraphStyle(name='Body',fontName='Helvetica',fontSize=10,leading=15,spaceAfter=10,textColor=colors.HexColor('#263445')))
    styles.add(ParagraphStyle(name='SmallCell',fontName='Helvetica',fontSize=8,leading=11))
    styles['Title'].textColor=colors.HexColor('#951e2b')
    styles['Heading1'].textColor=colors.HexColor('#951e2b')
    story=[]
    def paragraph(text):story.append(Paragraph(text,styles['Body']))
    def heading(title,number):
        if number>1:story.append(PageBreak())
        story.append(Paragraph('DIABLOS HACK / CONTRIBUCION TECNICA',styles['Caption']))
        story.append(Spacer(1,10));story.append(Paragraph(title,styles['Title']));story.append(Spacer(1,12))
    def table(headers,rows,widths):
        cells=[[Paragraph(escape(str(c)),styles['SmallCell']) for c in row] for row in [headers]+rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f3dadd')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#ccd2da')),
            ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.append(t);story.append(Spacer(1,14))
    def fmt(v):return 'n/d' if v is None else f'{v:.6f}'
    heading('1. Release y alcance',1)
    paragraph('<b>13 de octubre de 2026.</b> Esta contribución de diez páginas documenta la entrega de F8: política congelada, evaluación temporal final y una interfaz local de inferencia. Complementa las evidencias de las fases F0-F7 y no sustituye las reglas oficiales pendientes de aclaración.')
    paragraph('El producto entrega Stuff+, Location+ y Pitching+ provisionales junto con las probabilidades de seis eventos. Pitching es la referencia predictiva aprobada. Stuff se conserva como diagnóstico físico. Los candidatos de arsenal y ambiente no fueron promovidos durante desarrollo y no sustituyen esa política en la evaluación final.')
    paragraph('<b>Release:</b> '+escape(lock['name'])+'<br/><b>ID SHA-256:</b> '+lock['release_id'][:32]+'<br/>'+lock['release_id'][32:]+'<br/><b>Datos:</b> '+lock['data_run'])
    paragraph('El bloqueo contiene los hashes de modelos, calibradores, normalizadores, IDs de referencia, configuración, código y datos. Se creó antes de acceder a las filas finales de 2026. La apertura quedó registrada. La calidad de 2026 ya había sido perfilada en la preparación de datos: el aislamiento corresponde al desarrollo de los modelos, no a un desconocimiento absoluto del archivo.')
    paragraph('La política publicada usa S0, una utilidad exploratoria de eventos. El resultado de test se informa sin cambiar modelos, pesos, temperaturas ni referencia. Si se desarrolla otra versión después de esta apertura, deberá declararse que el test ya estuvo expuesto.')
    heading('2. Protocolo, datos y escala',2)
    table(['Etapa','Población y uso'],[['2024','Ajuste de modelos y vocabularios; soporte de entrada.'],['2025 desarrollo','Selección y parada temprana.'],['2025 calibración','Temperaturas y referencia fija de 59,367 lanzamientos.'],['2025 revisión','Decisiones de aceptación y promoción antes del test.'],['2026 final',f"{m['n_total']:,} filas; {m['n_common']:,} elegibles comunes para evaluación."]],[112,378])
    paragraph('La evaluación común mantiene las reglas de F0: calidad, target conocido y features completas para las tres familias. La API, en cambio, acepta features observables por familia y no exige outcomes. Por eso cobertura de inferencia y cobertura de evaluación no son equivalentes; ambas se registran.')
    paragraph('<b>S0 = P(whiff) + P(called_strike) - 0.5 P(ball) - P(hit_by_pitch).</b><br/>Índice = 100 + 10 (S0 - media de referencia) / desviación de referencia, con ddof=0. Foul e in_play pesan cero en esta versión.')
    paragraph('Los normalizadores se conservan sin reajuste en 2026 ni por pitcher, tipo o altura. Cien representa la media de la cohorte elegible de calibración, no de toda la liga. No equivale a carreras esperadas ni al Stuff+ validado de FanGraphs. S1 con contacto permanece separado como experimento de F7.')
    paragraph('Los agregados describen la mezcla observada: media de scores válidos por lanzamiento, con total, número válido y cobertura. No se iguala artificialmente el peso de cada tipo del arsenal. Una ausencia de cobertura permanece nula y nunca se reemplaza por 100.')
    heading('3. Resultados finales',3)
    table(['Modelo','N evaluado','Log loss','Brier multiclase'],[[r['model'],r['n_pitches'],fmt(r['multiclass_log_loss']),fmt(r['multiclass_brier_sum_over_classes'])] for r in evidence['metrics']],[110,90,145,145])
    paragraph('En ambas métricas, menor es mejor. La Brier es la suma de los errores cuadrados de las seis probabilidades. El modelo ambiental se muestra como candidato diagnóstico; una diferencia favorable en este año no lo convierte en la política elegida.')
    table(['Control / candidato','Delta log loss','IC 95% por partido'],[[r['reference']+' / '+r['candidate'],fmt(r['delta_candidate_minus_reference']),fmt(r['ci_low'])+' a '+fmt(r['ci_high'])] for r in evidence['comparisons']],[170,115,205])
    paragraph('Las cinco comparaciones estaban declaradas antes de abrir el test. Los intervalos usan 500 remuestreos pareados por partido y pérdidas ponderadas por lanzamiento. Un delta negativo favorece al candidato en este conjunto. Se reportan sin seleccionar ganadores ni interpretar estos cinco contrastes como evidencia confirmatoria corregida por multiplicidad.')
    paragraph('Las curvas de calibración por evento, las métricas condicionales de contacto/groundball/chase y sus tamaños de muestra están disponibles en calibration.json y metrics.json. Las cabezas no promovidas siguen su fallback de prevalencia de 2024, sin usar frecuencias de 2026.')
    heading('4. Cobertura y generalización',4)
    table(['Familia','Inferencia válida / total','Evaluación común'],[[f,f"{c['n_inference_valid']:,} / {c['n_total']:,}",f"{100*c['common_coverage']:.2f}%"] for f,c in coverage.items()],[110,215,165])
    selected=[r for r in subgroups if r['model']=='pitching']
    table(['Subgrupo Pitching','N válido','Log loss','Soporte'],[[r['group']+'='+r['value'],r['n_valid'],fmt(r['metrics']['multiclass_log_loss']) if r['metrics'] else 'n/d',r['status']] for r in selected],[190,65,85,150])
    paragraph('Unseen_training significa ausente en el ajuste de 2024; unseen_development significa ausente de toda la cohorte 2024-2025. Esta distinción evita presentar como totalmente nuevo a un pitcher ya observado durante desarrollo. El identificador no es un predictor del modelo base.')
    paragraph('El soporte descriptivo exige al menos 200 filas y 20 observaciones por clase. Los demás grupos conservan recuentos y métricas descriptivas con advertencia. No se generan rankings confiables a partir de grupos escasos. Las cotas marginales de features no garantizan soporte multivariado completo.')
    heading('5. Tres casos de scouting',5)
    paragraph('Los casos se seleccionaron mediante una regla fijada antes del test: los tres pitchers con más lanzamientos en la cohorte común, con desempate por ID. Son ejemplos auditables de uso, no una selección de los mejores scores ni recomendaciones de contratación.')
    for case in cases:
        pid=case['pitcher_anon_id'];data=[r for r in case['evidence'] if r['family']=='pitching' and r['n_valid']>0]
        n=sum(r['n_valid'] for r in data);mean=sum(r['score']*r['n_valid'] for r in data)/n
        paragraph(f'<b>{escape(pid)}</b>: {n:,} lanzamientos válidos; Pitching+ observado {mean:.2f}. No visto en ajuste 2024: {case["unseen_training"]}.')
        data=sorted(data,key=lambda r:(-r['n_valid'],str(r['auto_pitch_type'])))[:3]
        table(['Tipo (tres más usados)','N','Pitching+','P(whiff)','P(ball)'],[[r['auto_pitch_type'],r['n_valid'],f"{r['score']:.2f}",f"{r['p_whiff']:.3f}",f"{r['p_ball']:.3f}"] for r in data],[190,55,85,80,80])
    paragraph('La evidencia completa incluye todos los tipos, las tres familias y su cobertura en scouting_cases.json. Una diferencia entre tipos puede reflejar conteo, ubicación y bateador: no implica que aumentar el uso de un lanzamiento causará una mejora. Debe acompañarse de observación y contexto deportivo.')
    heading('6. Interfaz para el dashboard',6)
    paragraph('La interfaz local ofrece archivos JSON o HTTP en 127.0.0.1:8765. GET /health informa el release; GET /schema describe features, unidades y límites; POST /predict recibe una familia y una lista de registros. El servidor se inicia explícitamente y no publica datos en internet.')
    paragraph('Cada fila devuelve request_id/pitch_uid, versión del modelo y datos, score y referencia, familia, ruta, estado, advertencias, probabilidades de eventos, probabilidades condicionales y el índice correspondiente. Preserva orden y filas incluso con identificadores repetidos. Los IDs internos del lote no entran al modelo.')
    table(['Entrada','Respuesta'],[['Feature ausente o no válida','invalid_input; probabilidades e índice nulos.'],['Tipo de lanzamiento no visto','Rama nativa de categoría ausente; advertencia.'],['Pitcher sin historia','Modelo base sin exigir historia; advertencia si se informa ID nuevo.'],['Altura desconocida','La política base la ignora y lo advierte; el simulador ambiental la rechaza.'],['Familia no publicada','unsupported_model; sin score.']],[180,310])
    paragraph('Velocidad usa mph; spin rpm; altura/lado de salida, extensión y ubicación usan pies; movimiento usa pulgadas; seno y coseno son adimensionales. Los conteos se validan como enteros. Los límites físicos operativos provienen del contrato de datos; los rangos de entrenamiento generan advertencias adicionales.')
    paragraph('No se ofrecen efectos causales de estadio, optimización de física, intervalos individuales ni una política de arsenal no aprobada. reference_pitch_count=0 expresa que esta política no consume historia de arsenal.')
    heading('7. Pruebas y rendimiento local',7)
    paragraph(f'La suite pasó 118 pruebas. El paquete congelado pasó {len(checks)} comprobaciones previas al test sobre 2025, incluyendo recarga, coincidencia con F4, invariancia por lote y entradas inválidas. Las carpetas temporales de Windows requirieron ejecutar la suite fuera del aislamiento; se mantuvo el Python de .venv.')
    table(['Familia','Tamaño de lote','Mediana caliente (s)'],[[r['family'],r['batch_size'],fmt(r['median_seconds'])] for r in benchmark['results']],[150,150,190])
    paragraph('Cada mediana proviene de tres repeticiones con modelos ya cargados; incluye validación, predicción de eventos y cabezas auxiliares. Se usan cuatro hilos. No incluye red ni carga inicial y no constituye una promesa universal de latencia.')
    paragraph('<b>Hardware/entorno:</b> '+escape(str(benchmark['hardware']))+'. El archivo benchmark.json conserva las tres mediciones individuales.')
    paragraph('check_phase8.py verifica el bloqueo y los hashes de salidas, recalcula métricas globales e intervalos, revisa agregados y vuelve a predecir una muestra de 1,000 filas del test ya guardado. No abre otra consulta del dataset ni decide entre modelos. La repetición integral exige el mismo release y la opción --reproduce, y deja otra entrada en el registro de acceso.')
    paragraph('Los artefactos locales incluyen release_lock.json, modelos nativos, calibradores, normalizadores, configuración, soporte, cohortes, cobertura, métricas y salidas por lanzamiento. Git conserva el código y el resumen verificable; los datos/modelos siguen excluidos del repositorio.')
    heading('8. Cumplimiento y límites',8)
    table(['Requisito','Estado de la entrega'],[['Familias por lanzamiento','Implementadas; probabilidades e índices provisionales versionados.'],['Agregados de pitcher y arsenal observado','Implementados con N válido, total, cobertura y mezcla observada.'],['Arsenal histórico como predictor','Evaluado en F5; no promovido, política base conservada.'],['Ambiente / clasificación de altura','Ablación y simulador disponibles; asociación de forma fija, experimental.'],['Harp / estadio / park holdout','Pendiente: no hay mapeo de estadios validado.'],['Altitud numérica y atmósfera','Pendiente de campos externos.'],['Secuencia PA, bases y carreras oficiales','Pendiente; no se presenta S0 como run value.'],['Release, test y API local','Implementados con bloqueo, registro y evaluación no selectiva.'],['Documento y casos','Contribución de diez páginas y tres ejemplos con evidencia.']],[180,310])
    paragraph('F8 cierra la implementación del contrato interno con resultados revisables. No certifica el cumplimiento de campos o etiquetas oficiales todavía ausentes. Las diferencias entre temporadas, la calidad de etiquetas y el soporte de categorías siguen limitando la interpretación.')
    paragraph('<b>Fuentes internas:</b> docs/MODELING_SYSTEM_CONTRACT.md; config/data_contract.json; los cierres F0-F7; release_lock.json; evaluation/manifest.json, metrics.json, coverage.json, subgroups.json, scouting_cases.json y benchmark.json del release indicado en la página 1.')
    paragraph('Toda modificación futura de modelos, calibración o score debe declarar que 2026 ya fue expuesto. La evaluación de este release permanece inmutable y no se reinterpreta retrospectivamente como una búsqueda de mejores hiperparámetros.')
    heading('9. Evaluación frente al hackathon',9)
    paragraph('<b>Actualización: 14 de octubre de 2026.</b> Las fases F0-F8 del contrato interno están completas. Eso no equivale a cumplir íntegramente el reto. Esta valoración usa los criterios compartidos por el equipo; es una evaluación cualitativa de brechas, no una calificación del jurado ni un porcentaje de cumplimiento.')
    table(['Criterio / peso','Evidencia disponible','Brecha y valoración'],[
        ['Calidad del Stuff+ / 25%','Probabilidades calibradas, referencia fija y test temporal.','Brecha crítica: S0 no es xRunValue. Falta RMSE de carreras y comparación con el baseline oficial por conteo. Stuff no supera el baseline de eventos.'],
        ['Robustez fuera de muestra / 25%','Holdout por pitcher en F3; test temporal y pitchers no vistos en F8.','Parcial sólido: falta park holdout real. Las categorías de altura no identifican estadios.'],
        ['Arsenal + altitud / 25%','Features relacionales, ablaciones y simulador por categoría.','Brecha crítica: arsenal y ambiente no se incorporaron a la política final por falta de mejora suficiente. Falta delta Harp/nivel del mar y respaldo bibliográfico.'],
        ['Aplicabilidad real / 25%','API local, agregados, cobertura y tres casos de scouting.','Parcial: falta una experiencia para el coach y demostrar, en la entrevista de 10 minutos, cambios útiles de reclutamiento o táctica.']
    ],[112,163,215])
    paragraph('<b>Pitching no sustituye la validación de Stuff+.</b> En 2026, Pitching obtuvo log loss 1.023459; Stuff, 1.536157; B1, 1.486855. B1 predice eventos por conteo: no es el baseline de xRunValue promedio por conteo solicitado por el hackathon. No se puede presentar una mejora frente a uno como cumplimiento frente al otro.')
    paragraph('Las 118 pruebas respaldan el funcionamiento del sistema, pero la evaluación deportiva exige discriminación útil, generalización y decisiones revisables. Tampoco una asociación entre categorías, manteniendo fija la física observada, demuestra cómo cambiaría el mismo lanzamiento al trasladarlo a Harp Helú.')
    paragraph('<b>Conclusión:</b> hay una base técnica reproducible, pero faltan avances sustanciales en el núcleo competitivo: Stuff+ y la adaptación al entorno de Harp Helú.')
    heading('10. Prioridades para cerrar las brechas',10)
    table(['Prioridad','Trabajo pendiente','Evidencia de cierre'],[
        ['1. Aclarar datos con ISAC','Definir xRunValue o método autorizado; obtener IDs anonimizados de estadio y correspondencia de Harp. Confirmar disponibilidad de estados de bases/outs si el target los requiere.','Diccionario y target acordados, mapeo de estadios validado y restricciones de uso documentadas. No requiere desanonimizar personas.'],
        ['2. Fortalecer Stuff+','Investigar el rendimiento del modelo físico y evaluar contra el objetivo y baseline oficiales.','RMSE y calibración del target acordado en holdout; comparación trazable con baseline, cobertura y límites.'],
        ['3. Validar estadio y altura','Implementar park holdout y contraste Harp/nivel del mar. Revisar literatura y declarar supuestos físicos y confundidores.','Delta por pitch shape, incertidumbre, soporte de datos y fuentes bibliográficas. Separar asociación de estimación causal.'],
        ['4. Probar utilidad deportiva','Preparar una interfaz para el coach y una demostración de 10 minutos con decisiones concretas.','Casos de reclutamiento y táctica con alternativas, evidencia y cobertura; retroalimentación de usuarios deportivos.']
    ],[90,215,185])
    paragraph('<b>Protocolo posterior a F8:</b> 2026 ya fue evaluado. Las mejoras pueden desarrollarse con 2024-2025, pero no se deben ajustar repetidamente a 2026 y luego describirlo como test independiente. Para una nueva conclusión confirmatoria se necesita un conjunto final no utilizado o un protocolo nuevo que declare explícitamente la exposición previa.')
    paragraph('<b>Alcance de esta actualización:</b> se documentan pendientes; no se ejecutan nuevas fases, no se cambian modelos, pesos o normalizadores y no se reabre el dataset de test. El release y sus resultados originales se conservan.')
    paragraph('<b>Uso responsable:</b> mantener IDs anonimizados y respetar las condiciones de confidencialidad/NDA que correspondan. El uso previsto es análisis deportivo y scouting, excluyendo apuestas. Cualquier incorporación futura de datos personales requiere revisar las obligaciones aplicables; no es necesaria para resolver el mapeo anonimizado de estadios.')
    paragraph('<b>Fuentes de la valoración:</b> criterios de evaluación proporcionados por el equipo el 14 de octubre de 2026; ficha del modelo F8; evidencia de F3, F5, F6 y F8. No se verificaron requisitos adicionales de convocatoria fuera del texto compartido.')
    def page(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#951e2b'));canvas.line(52, fifty:=50,543,fifty)
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#526171'))
        canvas.drawString(52,36,'Diablos Hack | F8 | Actualizado 14 octubre 2026 | Utilidad provisional')
        canvas.drawRightString(543,36,str(doc.page))
    SimpleDocTemplate(str(target),pagesize=(595.28,841.89),leftMargin=52,rightMargin=52,topMargin=45,bottomMargin=65).build(story,onFirstPage=page,onLaterPages=page)
    pdf=PdfReader(target)
    if len(pdf.pages)!=10:raise RuntimeError('Expected exactly ten pages, got '+str(len(pdf.pages)))
    for p in pdf.pages:
        if len(p.extract_text())<200:raise RuntimeError('Unexpected empty page')
    print(str(target.resolve()))


if __name__=='__main__':main()
