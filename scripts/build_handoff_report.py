"""Build the human-readable handoff from the published data run."""
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from diablos_data import current_run
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

run=current_run()
summary=json.loads((run/'summary.json').read_text(encoding='utf-8'))
manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
font='Helvetica'; bold='Helvetica-Bold'
if Path('C:/Windows/Fonts/arial.ttf').exists():
    pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Bold','C:/Windows/Fonts/arialbd.ttf'))
    pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial',boldItalic='Arial-Bold')
    font='Arial'; bold='Arial-Bold'
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyCustom',fontName=font,fontSize=10.4,leading=14.2,spaceAfter=8,textColor=colors.HexColor('#20252B')))
styles.add(ParagraphStyle(name='TitleCustom',fontName=bold,fontSize=25,leading=29,spaceAfter=14,textColor=colors.black))
styles.add(ParagraphStyle(name='SectionCustom',fontName=bold,fontSize=18,leading=22,spaceAfter=12,textColor=colors.black))
styles.add(ParagraphStyle(name='SubCustom',fontName=bold,fontSize=11.5,leading=15,spaceBefore=7,spaceAfter=6,textColor=colors.black,keepWithNext=True))
styles.add(ParagraphStyle(name='SmallCustom',fontName=font,fontSize=8.5,leading=11.5,spaceAfter=7,textColor=colors.HexColor('#4C555F')))
styles.add(ParagraphStyle(name='CellCustom',fontName=font,fontSize=9.2,leading=12,spaceAfter=0))
styles.add(ParagraphStyle(name='CellHeadCustom',fontName=bold,fontSize=9.2,leading=12,textColor=colors.white))
styles.add(ParagraphStyle(name='CodeCustom',fontName='Courier',fontSize=8.5,leading=12,spaceAfter=9))
story=[]
def p(text,style='BodyCustom'): story.append(Paragraph(text,styles[style]))
def sub(text): p(text,'SubCustom')
def section(text): story.append(PageBreak()); p(text,'SectionCustom')
def table(headers,rows,widths):
    data=[[Paragraph(escape(str(x)),styles['CellHeadCustom']) for x in headers]]
    data += [[Paragraph(escape(str(x)),styles['CellCustom']) for x in row] for row in rows]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#273C50')),
      ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F1F4F6')]),
      ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#D9DDE1')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
      ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.append(t); story.append(Spacer(1,10))

p('Entrega de la base de datos de pitcheo','TitleCustom')
p('Diablos Hackathon 2026 | Ingeniería de datos | 27 de septiembre de 2026','SmallCustom')
p('<b>La base está implementada y disponible para empezar a modelar.</b> Se preservó la fuente, se prepararon tablas limpias, se separaron predictores y objetivos, se definieron particiones de evaluación y se habilitó consulta local mediante Python y SQL. La preparación conserva todos los lanzamientos y aplica filtros distintos según el uso.')
table(['Resultado de la preparación','Cantidad'],[
('Lanzamientos preservados','635,002'),('Pitchers y partidos identificados','1,134 pitchers y 2,127 partidos'),('Eventos utilizables según la política de etiquetas','633,687'),('Eventos sin etiqueta de entrenamiento','1,315'),('Filas elegibles para Stuff físico predeterminado','630,585'),('Filas elegibles para Pitching combinado predeterminado','621,731'),('Pitchers no vistos en 2026 frente a 2024 y 2025','249 IDs y 42,162 lanzamientos')],[350,154])
sub('Qué quedó resuelto')
p('El equipo puede cargar matrices de entrenamiento con variables permitidas, consultar estadísticas y revisar incidencias sin reconstruir la preparación. Hay una base DuckDB materializada, tablas Parquet, diccionarios, reglas configurables, pruebas y ejemplos. No se entrenó un modelo ni se produjeron scores Stuff+ en esta fase.')
sub('Por qué se implementó así')
p('Una base local evita dedicar tiempo a servidores y credenciales durante las dos semanas del proyecto. Parquet facilita el trabajo en Python o R; DuckDB permite consultas SQL sobre un archivo portátil. La separación de capas reduce errores de interpretación y permite revisar una regla sin perder la información original.')
p('La elegibilidad indicada no es una garantía de exactitud ni de generalización. Los targets condicionales tienen poblaciones menores; sus conteos están documentados por separado.','SmallCustom')

section('Arquitectura y trazabilidad')
p('El ZIP original permanece intacto. Su huella SHA256 identifica la fuente. Se extrajeron únicamente Parquet y el diccionario; no se ejecutó el archivo pickle ni se afirmó equivalencia con la versión RDS.')
table(['Componente','Contenido y uso'],[
('data/raw','Copia del Parquet y diccionario extraídos. Se verifica su integridad y se mantiene la referencia al ZIP.'),
('pitches','Todas las filas, nombres homogéneos y tipos normalizados. Incluye datos de auditoría que no deben entrar directamente al modelo.'),
('features y targets','Predictores separados de resultados. Las etiquetas y sus poblaciones tienen definiciones explícitas.'),
('quality_flags y quality_issues','Elegibilidad por lanzamiento y lista detallada de incidencias. Un pitch puede tener varios problemas.'),
('splits','Separación temporal, por pitcher, folds de partido y categorías ambientales.'),
('arsenal_features y arsenal_references','Referencias calculadas con años previos y diferenciales respecto a la recta histórica.'),
('diablos.duckdb','Base SQL con ocho tablas preparadas, metadatos y vistas de consulta. Puede copiarse sin depender de rutas de Parquet.'),
('Catálogo y manifiesto','Definiciones, faltantes, listas de variables, versiones de dependencias y hashes de salidas.')],[154,350])
sub('Publicación segura de cada versión')
p('La preparación escribe primero una carpeta de construcción y valida las tablas. Solo al terminar publica la versión en data/CURRENT. Una ejecución interrumpida no reemplaza la versión vigente. Cambios en fuente, configuración, código o dependencias generan otra versión; las anteriores se preservan.')
p('La repetición con las mismas entradas comprueba los hashes de los resultados y reutiliza la versión existente. Esta propiedad permite a los cuatro integrantes trabajar sobre una referencia común y saber exactamente qué preparación produjo sus resultados.')
p('Versión entregada: '+run.name+'. Configuración: 1.0.0. Python '+manifest['versions']['python']+', pandas '+manifest['versions']['pandas']+', PyArrow '+manifest['versions']['pyarrow']+' y DuckDB '+manifest['versions']['duckdb']+'.','SmallCustom')

section('Limpieza y construcción de etiquetas')
p('No se eliminaron filas de la base. Los valores sospechosos se conservan en la fuente y se vuelven nulos en la capa limpia cuando la regla lo requiere. Las incidencias se distinguen de los filtros que aplicará cada familia de modelos.')
table(['Hallazgo','Tratamiento aplicado'],[
('2,280 conflictos en bandera de golpeado','Se conserva la bandera fuente. Se deriva una etiqueta nueva desde PitchCall solo cuando el resultado terminal no la contradice.'),
('450 swings fallidos marcados como contacto','Se mantiene el evento candidato y se dejan nulas las etiquetas para entrenamiento. No se decide automáticamente cuál campo tiene razón.'),
('23 contradicciones terminales y 2 de bola en juego','Se ponen en cuarentena los eventos. Los conteos se solapan con otras reglas; no deben sumarse como pitches únicos.'),
('127 extensiones y 7 mediciones de movimiento fuera de rango','Se ponen en nulo los valores correspondientes en la copia limpia. Los límites son reglas de revisión configurables.'),
('6,669 alturas en plato iguales a cero','Se conserva el valor y se excluye de modelos de ubicación hasta conocer su significado.'),
('3,272 pitches sin pitcher y 3,020 sin altitud','Se conservan. No participan en usos que requieren agrupar por pitcher o conocer el ambiente.')],[220,284])
sub('Tipos y categorías')
p('EffectiveVelo se convirtió de texto a número. Se normalizaron nombres a snake_case y se representaron como nulos las manos y lados desconocidos. No se infirió la mano usando temporadas futuras ni se reclasificaron automáticamente tipos de pitch raros.')
sub('Targets con denominadores explícitos')
p('y_event contiene seis resultados por pitch. Se ofrecen targets de swing, whiff, contacto, strike cantado, bola en juego y golpeado, además de tasas condicionales de whiff dado swing y chase fuera de zona. Contacto duro usa salida de al menos 95 mph; el proxy de contacto débil usa menos de 75 mph y se identifica como exploratorio.')
p('Los targets de batazo se limitan a bolas en juego con medición o resultado conocido. Un lanzamiento sin contacto no recibe un cero de contacto débil. Se excluyen los siete InPlay con resultado NeutralPlay de los objetivos hit/jonrón, sin descartar su evento de bola en juego.','SmallCustom')

section('Evaluación y prevención de información futura')
table(['Partición temporal','Filas totales','Filas Stuff y evento válidas'],[
('Entrenamiento 2024','243,254','242,426'),('Validación 2025','256,144','254,580'),('Prueba final 2026','135,604','133,579')],[190,130,184])
p('Se definió también una partición independiente por pitcher mediante hash estable. Cada ID pertenece a un solo grupo, aunque un partido puede aparecer en varios grupos con pitchers distintos. Esta prueba evalúa jugadores no vistos y no equivale a una prueba temporal o por partido. Los cinco folds por partido se usan dentro de la partición seleccionada.')
sub('Predictores permitidos')
p('Stuff físico utiliza tipo de pitch, mano del pitcher, velocidad, movimiento, spin y release. El eje de spin se codifica como seno y coseno. Location incorpora ubicación, conteo y lado del bateador. Pitching combina física, ubicación y categoría ambiental. IDs, resultados de batazo, año y número de fila no son predictores predeterminados.')
p('La API entrega X, y y metadatos separados. No ajusta imputaciones, escalado ni codificadores: esas transformaciones deberán aprenderse únicamente en entrenamiento. La base de auditoría contiene outcomes; por eso no debe entrenarse con todas sus columnas.')
sub('Arsenal histórico y su límite real')
table(['Año evaluado','Historia permitida','Pitches con referencia'],[
('2024','No disponible','0'),('2025','Solo 2024','131,613'),('2026','2024 y 2025','88,470')],[120,200,184])
p('La referencia es la clase más frecuente entre Four-Seam y Sinker con al menos 30 pitches históricos completos. Se calculan diferenciales de velocidad y movimiento, uso histórico y distancia del release. La distancia no se presenta como tunneling real.')
p('<b>Arsenal no se añade automáticamente a X.</b> Un modelo entrenado solo con 2024 no podría aprender referencias históricas ausentes. Se necesita historia anterior o un experimento de adaptación con muestras de referencia separadas de las de evaluación. Completar 2024 con datos de 2025 introduciría información futura.')

section('Verificación y puesta en marcha')
sub('Qué se verificó')
p('La publicación pasó 22 controles de integridad y contrato, incluido el conteo del join SQL. Se comprobaron IDs únicos, conservación de filas, correspondencia entre tablas, separación por pitcher, poblaciones condicionales, cuarentena de etiquetas y antigüedad de referencias de arsenal. El verificador independiente comprobó las huellas de los 20 artefactos de salida.')
p('Pasaron siete pruebas automatizadas de casos límite: etiquetas contradictorias, reconstrucción de golpeados, ausencia de contacto, valores físicos inválidos, evento desconocido, estabilidad de particiones y ausencia de contaminación de referencias pasadas por un cambio en un pitch futuro.')
p('Se probaron cargas de entrenamiento, validación y prueba. También se verificaron cargas de chase para Location y contacto duro para Pitching. Estas comprobaciones demuestran que la base se puede consumir; no sustituyen una validación predictiva.')
sub('Empezar en esta computadora')
p('Desde la carpeta del proyecto, el lanzador detecta el entorno instalado. El ejemplo carga predictores y etiquetas de entrenamiento y consulta el resumen por año. La guía README explica la alternativa si PowerShell bloquea scripts.')
p('.\\run_data.ps1 example<br/>.\\run_data.ps1 check','CodeCustom')
sub('Uso desde Python')
p('from diablos_data import load_model_data<br/>X, y, metadata = load_model_data(<br/>&nbsp;&nbsp;feature_set="stuff", target="y_event", split="train"<br/>)','CodeCustom')
p('Para comenzar en otro equipo, instalar Python 3.12 y las versiones fijadas en requirements.txt. Copiar el código, la carpeta de la versión publicada y data/CURRENT. La base SQL también puede abrirse por sí sola con DuckDB. No se requiere un servidor.')
sub('Archivos de consulta del equipo')
table(['Archivo','Para qué abrirlo'],[('README.md','Inicio rápido, instalación, carga y reproducción.'),('docs/DATA_CONTRACT.md','Definiciones completas, criterios y límites de uso.'),('data_catalog.csv','Columnas, tipos, roles, unidades y faltantes.'),('quality_summary.csv y target_profile.csv','Incidencias y población disponible para cada objetivo.'),('examples/consultas.sql','Consultas listas para explorar la base.')],[236,268])

section('Límites pendientes y próximos pasos')
p('La preparación resuelve lo que puede hacerse con los datos entregados. No inventa campos faltantes ni presenta como medido lo que requiere información adicional.')
table(['Información pendiente','Qué impide o condiciona'],[
('Estadio e indicador Harp Helú','Simulación específica de CDMX y validación real por parque. Extreme Altitude no identifica por sí sola al Harp.'),
('Altitud en metros y condiciones atmosféricas','Cuantificación física más precisa y separación de ambiente frente a otros efectos de estadio.'),
('Fecha, orden e ID de aparición al plato','Secuencia previa, arsenal acumulado dentro de temporada y objetivos a nivel de aparición al plato.'),
('Ocupación de bases y definición de run value','Construcción estándar de valor esperado de carreras. RunsScored no es un sustituto.'),
('Reglas de etiquetado, zona e IDs estables','Adjudicar contradicciones, interpretar altura cero y confirmar pitchers realmente no vistos entre años.')],[215,289])
sub('Orden recomendado para continuar')
p('<b>1. Datos y evaluación.</b> Revisar las preguntas con organizadores y mantener el contrato. Cualquier corrección debe producir una nueva versión y dejar registro de su motivo.')
p('<b>2. Modelado.</b> Entrenar un baseline por conteo con 2024 y evaluar calibración en 2025. Comparar después Stuff, Location y Pitching usando las mismas poblaciones y particiones. Ajustar transformaciones solo en entrenamiento.')
p('<b>3. Arsenal y ambiente.</b> Elegir un protocolo explícito de historia o adaptación. Usar categorías de altitud para diagnósticos, sin atribuir causalidad ni anunciar resultados específicos del Harp hasta contar con el mapeo.')
p('<b>4. Producto y comunicación.</b> Conectar el dashboard a las predicciones del modelo, mostrar muestra e incertidumbre y preparar tres casos de scouting. Reservar 2026 para la evaluación final de la versión seleccionada.')
sub('Alcance de esta entrega')
p('La auditoría inspeccionó la calidad de 2026, pero no ajustó modelos ni hiperparámetros. No se entrenó ni desplegó un modelo, no se calculó un Stuff+ definitivo y no se resolvieron causalmente las diferencias de altitud. Esas son tareas posteriores a esta base de ingeniería.')
p('Fuente: ZIP y diccionario proporcionados por el equipo; auditoría del Parquet completo y ejecución local de preparación. Reglas y decisiones detalladas en docs/DATA_CONTRACT.md. Los archivos originales y las versiones preparadas permanecen en la carpeta del proyecto.','SmallCustom')

out=ROOT/'output'/'pdf'; out.mkdir(parents=True,exist_ok=True)
path=out/'Entrega_ingenieria_datos_Diablos.pdf'
def footer(canvas,doc):
    canvas.setFont(font,8)
    canvas.setFillColor(colors.HexColor('#59636E'))
    canvas.drawString(54,28,'Diablos Hackathon 2026 - Entrega de ingeniería de datos')
    canvas.drawRightString(558,28,str(doc.page))
doc=SimpleDocTemplate(str(path),pagesize=letter,rightMargin=54,leftMargin=54,topMargin=48,bottomMargin=47,
                      title='Entrega de la base de datos de pitcheo',author='Equipo Diablos Hackathon')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(path)
