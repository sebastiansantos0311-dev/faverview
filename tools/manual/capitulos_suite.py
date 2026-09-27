"""Capítulos del manual para los módulos de la suite v3 (Parte II). Se importan desde build.py."""


def suite(fig) -> str:
    return f"""
<h1>Parte II · La suite de preprensa</h1>
<p>Desde la versión 3 FAVERVIEW es una <b>suite</b>: además de comparar el arte con el diseño (capítulos 1 a 20) incluye módulos de
preprensa. Todo funciona en tu equipo, sin internet, sin costo y sin inteligencia artificial. Los resultados de color son
<b>estimaciones orientativas</b>: siempre confirma con una prueba impresa antes de producir.</p>

<h1>21. Cómo está organizada la suite</h1>
{fig("s01_suite", "Las siete pestañas, el botón Tintas y el selector «Enviar a…».")}
<table>
<tr><th>Pestaña</th><th>Para qué sirve</th><th>Necesita Ghostscript</th></tr>
<tr><td>Comparar</td><td>Arte del cliente contra tu diseño (capítulos 1 a 20).</td><td>Solo para algunos PDF</td></tr>
<tr><td>Separar colores</td><td>PDF → placas por tinta, cobertura total (TAC) y problemas; imagen → tintas.</td><td>PDF: sí · Imagen: no</td></tr>
<tr><td>Vectorizar</td><td>Convierte una imagen en vectores por colores, sin huecos.</td><td>Solo para EPS</td></tr>
<tr><td>Preflight</td><td>Revisión técnica del PDF con perfiles y correcciones seguras.</td><td>Para TAC, líneas, texto y sobreimpresión</td></tr>
<tr><td>Códigos de barras</td><td>Generar, verificar y crear lotes.</td><td>Solo para EPS</td></tr>
<tr><td>Herramientas</td><td>Trapping, step &amp; repeat, distorsión flexo, braille, gama extendida, prueba en pantalla y calibración.</td><td>Trapping, gama y prueba: sí</td></tr>
<tr><td>Automatizar</td><td>Recetas que encadenan pasos sobre un archivo, una carpeta o una carpeta vigilada.</td><td>Según los pasos</td></tr>
</table>
<h3>Funciones comunes</h3>
<ul>
<li><b>Soltar o pegar archivos:</b> en cualquier zona de carga puedes arrastrar el archivo o hacer clic.</li>
<li><b>Enviar a…:</b> después de soltar un archivo aparece arriba a la derecha el selector <b>Enviar a…</b>. Elige otro módulo y el mismo
archivo se abre allí sin volver a subirlo (por ejemplo Separar → Preflight → Herramientas).</li>
<li><b>Cancelar:</b> los trabajos largos muestran el botón <b>Cancelar</b>; el trabajo se detiene en su próxima etapa (no interrumpe un
cálculo a la mitad).</li>
<li><b>Visor:</b> rueda del ratón = zoom (de 2 % a 3200 %), arrastrar = mover, <code>Ctrl+0</code> = ajustar a la ventana,
<code>Ctrl+1</code> = tamaño real (100 %). Con el cursor sobre la página se muestran los milímetros.</li>
<li><b>Si falta una herramienta</b> (por ejemplo Ghostscript) la pestaña aparece con aviso y te dice cómo instalarla.</li>
</ul>

<h1>22. Bibliotecas de tintas (Pantone y otras)</h1>
{fig("s02_tintas", "La pantalla Tintas: bibliotecas, importar, editar y exportar.")}
<p>El botón <b>Tintas</b> abre las bibliotecas que usan todos los módulos. Cada tinta tiene nombre, tipo (proceso, directa, blanco,
barniz o técnica), color Lab y, si aplica, opacidad.</p>
<div class="aviso"><b>Sobre Pantone y otras bibliotecas comerciales.</b> Pantone, HKS, RAL, TOYO y DIC son bibliotecas comerciales con licencia.
FAVERVIEW <b>no las incluye</b> ni trae sus valores, y no debes usar copias no autorizadas. Importa <b>tus propias</b> bibliotecas por alguna
de estas vías legales.</div>
<h3>Cómo obtener tus bibliotecas de forma legal</h3>
<ol>
<li><b>Desde Illustrator</b> (con Pantone Connect): panel <b>Muestras</b> → selecciona las muestras → menú ☰ → <b>Guardar biblioteca de
muestras como ASE</b>.</li>
<li><b>Pantone Connect Premium:</b> crea paletas con tus colores y expórtalas como <b>ASE</b> o <b>CxF</b>.</li>
<li><b>Tintas medidas</b> con tu espectrofotómetro: expórtalas a <b>CxF</b> o a un CSV con este formato (una tinta por fila):
<pre>nombre;L;a;b;tipo;opacidad
Azul marino;20;5;-25;spot;0
Blanco flexo;94;0;-2;white;1</pre></li>
<li><b>Pídele las CxF a tu proveedor de tintas</b> (Siegwerk, Sun Chemical, Flint, etc.): suelen entregarlas gratis.</li>
</ol>
<p>Para importarlas: <b>Tintas → Importar</b> (acepta CxF/CxF3, ASE, CSV y JSON) y ponle un nombre. Se guardan en
<code>datos_locales/tintas/</code>, una carpeta privada que <b>nunca se sube a GitHub</b>.</p>
<p><b>Qué trae la app gratis:</b> los CMYK de referencia ISO 12647-2 / Fogra (valores públicos de la caracterización), blanco, barniz,
tintas técnicas (troquel, braille, cotas) y las tintas que crees tú con su Lab.</p>

<h1>23. Separar colores · PDF</h1>
{fig("s03_separar_pdf", "Separación de un PDF: lista de tintas, vista compuesta, problemas y cobertura total.")}
<p>Suelta un PDF en la pestaña <b>Separar colores → PDF</b>. FAVERVIEW lo separa en <b>placas</b> (una por tinta) con Ghostscript y
muestra:</p>
<ul>
<li><b>Tintas:</b> nombre, tipo, porcentaje de cobertura y muestra de color. Los botones <b>Solo</b> y <b>Neg.</b> muestran una placa sola
(o en negativo); la casilla la oculta de la vista compuesta. Las tintas definidas pero sin uso aparecen en gris.</li>
<li><b>Vista compuesta simulada:</b> combina las placas con un modelo de mezcla orientativo (no espectral).</li>
<li><b>Densitómetro:</b> al pasar el cursor por la página muestra el porcentaje de cada tinta y la <b>cobertura total (TAC)</b> del área.</li>
<li><b>Mapa de cobertura:</b> el botón <b>Mapa de cobertura</b> pinta en rojo lo que supera el límite del perfil (offset 300 %, flexo 280 %,
digital 320 %, papel prensa 240 %).</li>
</ul>
{fig("s04_separar_tac", "Mapa de cobertura total: en rojo, lo que supera el límite elegido.")}
<h3>Problemas que detecta</h3>
<table>
<tr><th>Problema</th><th>Por qué importa</th></tr>
<tr><td>Cobertura total sobre el límite</td><td>Exceso de tinta: secado lento y repinte.</td></tr>
<tr><td>Negro enriquecido en texto pequeño</td><td>Un desajuste de registro engorda el texto.</td></tr>
<tr><td>Texto de menos de 6 pt en varias tintas</td><td>Se vuelve ilegible con el mínimo mal registro.</td></tr>
<tr><td>Barniz en knockout, blanco sobreimpreso, tinta técnica sin sobreimpresión</td><td>Borra la tinta de abajo o desaparece.</td></tr>
<tr><td>Objetos en color de registro (All)</td><td>Salen en todas las placas.</td></tr>
<tr><td>RGB o Lab sin convertir</td><td>El resultado depende de la conversión del RIP.</td></tr>
<tr><td>Líneas más finas de 0,1 mm en varias tintas</td><td>No se imprimen bien.</td></tr>
</table>
<p>Haz clic en un problema para acercarte a la zona. <b>Edición</b> (siempre sobre una copia; tu archivo no se modifica): <b>Unir
duplicadas</b> (por ejemplo «Pantone 485C» y «PANTONE 485 C»), <b>Convertir a proceso</b> (directa simple con alternativo CMYK),
<b>Eliminar no usadas</b> y <b>Deshacer</b>. <b>Exportar placas</b> descarga un ZIP con TIFF de 8 o 1 bit (negro = tinta), un PDF de placas
o solo el informe.</p>

<h1>24. Separar colores · Imagen</h1>
{fig("s05_separar_imagen", "Imagen → tintas: pasos numerados, vista simulada y lista de tintas con su cobertura.")}
<p>La sub-pestaña <b>Imagen → tintas</b> tiene cuatro pasos: <b>1 Imagen y sustrato</b> (papel, prenda negra, gris, roja, azul marino,
kraft), <b>2 Modo y tintas</b>, <b>3 Ajustes</b> y <b>4 Salida</b>. Cambiar un ajuste actualiza la vista a baja resolución.</p>
<table>
<tr><th>Modo</th><th>Cuándo usarlo</th></tr>
<tr><td>Tintas planas</td><td>Logos e ilustraciones. Detecta la paleta sola (o usa la que marques), quita islas y puede suavizar bordes.</td></tr>
<tr><td>Proceso simulado</td><td>Fotos con pocas tintas o sobre prenda. Marca las tintas (el blanco se imprime primero): busca las coberturas que
mejor reproducen cada color. Incluye base blanca con <i>choke</i> y muestra el error estimado (ΔE medio y p95).</td></tr>
<tr><td>Índice</td><td>Paleta y difusión de error Floyd–Steinberg. No se puede reescalar después.</td></tr>
<tr><td>CMYK</td><td>Conversión con un perfil ICC (FOGRA, GRACoL o el tuyo), con límite de TAC y «negro solo en sombras». Necesita un perfil
ICC CMYK en Windows o en <code>datos_locales/perfiles_icc</code>.</td></tr>
</table>
<p><b>Salida:</b> canales TIFF de 8 bits por tinta, placas tramadas de 1 bit (AM con lpi y ángulo por tinta, o FM/estocástico),
<b>PDF DeviceN</b> con los nombres de las tintas, la simulación en PNG y un informe. No se genera PSD multicanal.</p>
<div class="nota">Un ΔE alto en azules o rojos muy saturados suele ser real: el juego de tintas elegido no alcanza ese color. El mapa de error lo
muestra. Para afinar el modelo con tu proceso usa la <b>Calibración</b> (capítulo 28).</div>

<h1>25. Vectorizar</h1>
{fig("s06_vectorizar", "Vectorizar un logo: ajustes a la izquierda, colores y edición a la derecha.")}
<p>Suelta una imagen y elige un preajuste: <b>Logo</b>, <b>Línea (B/N)</b>, <b>Ilustración</b>, <b>Escaneo</b> o <b>Foto posterizada</b>. El
vectorizador reduce la imagen a unos pocos colores y traza las <b>fronteras compartidas</b> entre regiones: cada borde se ajusta una sola vez
y las dos regiones lo usan, así que <b>no quedan huecos ni solapes</b> entre colores.</p>
<ul>
<li><b>Ver:</b> vector, original, superpuesto (con opacidad), contornos y nodos, o diferencias con el original.</li>
<li><b>Ajustes:</b> colores máximos, fusión de colores parecidos, detalle mínimo en mm, tolerancia del ajuste, ángulo de esquina, suavidad,
modo <i>sin solapes</i> o <i>apilado</i> y tamaño final en mm.</li>
<li><b>Geometría y preprensa (v2):</b> primitivas exactas (arcos, círculos, elipses), enderezar líneas casi horizontales o verticales, simetría,
líneas como trazos con grosor, engrosar detalles finos y tratamiento del texto (marcar la zona o reemplazarlo por texto real).</li>
<li><b>Edición básica:</b> unir dos colores, borrar una región, recolorear y volver a trazar una zona seleccionada.</li>
<li><b>Descargar:</b> SVG, PDF con cada color como <b>tinta directa</b> con su nombre, EPS (Ghostscript) y DXF en mm para corte.</li>
</ul>
{fig("s07_vectorizar_contornos", "Contornos y nodos: pocos puntos, curvas suaves y esquinas nítidas.")}
<div class="nota">En el banco de pruebas interno (40 logos con vector verdadero) el resultado iguala o supera en fidelidad a VTracer en el 92 % de los
casos usando unas 4 veces menos nodos. No se ha comparado con Illustrator ni CorelDRAW: si quieres, genera sus SVG y guárdalos en
<code>datos_locales/vector_bench/externos/</code>.</div>

<h1>26. Preflight</h1>
{fig("s08_preflight", "Preflight: resultados por severidad a la izquierda; clic en un problema para acercarse a la zona.")}
<p>Elige un <b>perfil</b> (Offset hoja, Flexo empaque, Etiquetas digital, Serigrafía o Solo revisión básica; los tres primeros están «inspirados en
GWG 2015», no son una certificación) y suelta el PDF. Los resultados se agrupan en <b>errores</b>, <b>advertencias</b> e <b>información</b>.</p>
<p>Reglas: fuentes no incrustadas o Type 3, resolución efectiva de las imágenes, espacios de color, número de tintas directas y duplicadas,
cobertura total, líneas y texto pequeños, negro enriquecido, sobreimpresión, sangrado y zona segura, TrimBox, transparencias, capas ocultas,
anotaciones, PDF/X, OutputIntent y compresión JPEG fuerte. Los perfiles son archivos JSON que puedes duplicar y editar.</p>
<p><b>Corregir…</b> aplica correcciones seguras <b>sobre una copia</b>: eliminar anotaciones, unir tintas duplicadas, añadir TrimBox y BleedBox con
el sangrado que indiques, y poner en sobreimpresión las tintas técnicas y el negro 100 % K. Después vuelve a revisar y muestra cuánto se parece
el resultado visual al original. No se pueden incrustar fuentes que faltan: solo se avisa. <b>Reporte PDF</b> descarga el resumen con miniaturas.</p>

<h1>27. Códigos de barras</h1>
{fig("s09_codigos", "Generar un EAN-13: el dígito de control se calcula solo y la salida es vectorial.")}
<h3>Generar</h3>
<p>Tipos: EAN-13, EAN-8, UPC-A, UPC-E, ITF-14, Code 128, GS1-128, Code 39, GS1 DataBar, Data Matrix, GS1 DataMatrix y QR. La app calcula o verifica el
<b>dígito de control</b> y valida los datos GS1 (identificadores de aplicación entre paréntesis, por ejemplo
<code>(01)09501101530003(17)250101(10)AB12</code>).</p>
<ul>
<li><b>Magnificación</b> 80–200 % (EAN-13 al 100 % mide 37,29 × 26 mm con módulo X de 0,33 mm) o módulo X directo.</li>
<li><b>Reducción de barras (BWR)</b> en µm: compensa la ganancia de punto. Pon el valor de tu proceso y confírmalo con una prueba impresa.</li>
<li><b>Tinta:</b> negro o una tinta de tus bibliotecas; avisa si el contraste con luz roja es insuficiente.</li>
<li>Salida <b>siempre vectorial</b>: PDF (con la tinta directa), SVG y EPS. El texto legible usa Helvetica (no se incluye OCR-B).</li>
<li><b>Lote:</b> un CSV <code>tipo;datos;nombre</code> produce un ZIP con un PDF por código, una hoja con todos y un archivo con los errores por fila.</li>
</ul>
<h3>Verificar</h3>
<p>Suelta un PDF o imagen: se detectan y decodifican todos los códigos (a 300, 600 o 1200 dpi) y se informa el contenido, el dígito de control, la
<b>magnificación medida</b>, las <b>zonas de silencio</b>, el <b>contraste en luz roja</b> (rojo sobre blanco = error) y, si indicas la dirección de
impresión, si las barras van paralelas a ella (flexo). Además muestra un <b>grado estimado A–F</b> inspirado en ISO/IEC 15416.</p>
<div class="aviso">El grado es una <b>estimación</b>, no una verificación certificada. Para certificar usa un verificador homologado.</div>

<h1>28. Herramientas</h1>
<h3>Trapping (reventado)</h3>
{fig("s12_trapping", "Mapa de traps sobre el trabajo en gris: en color, donde una tinta se expande bajo otra.")}
<p>Trabaja sobre las placas: <b>la tinta más clara se expande bajo la más oscura</b>. El negro, el barniz y las tintas técnicas nunca se expanden; el
blanco solo se contrae (<i>choke</i>). Anchos por defecto: flexo 0,15 mm, offset 0,08 mm, serigrafía 0,25 mm (editables), con opción de trap reducido y
tope de cobertura en la zona. <b>Mal registro</b> desplaza una placa unas micras y muestra el resultado con y sin trap. Exporta las placas con trap,
el mapa y un PDF de placas. Es una estimación: confirma los anchos con tu imprenta.</p>
<h3>Step &amp; repeat</h3>
{fig("s11_step_repeat", "Imposición de 2 × 2 con marcas de registro, corte, barra de color y el nombre de cada tinta.")}
<p>Coloca la etiqueta (usa TrimBox y BleedBox) en una hoja o banda: columnas y filas (o rellenar), separaciones, márgenes, rotación por fila,
desfase y aprovechamiento. Marcas: registro y corte en la tinta <b>All</b> (salen en todas las placas), barra de control con parches al 100 % y 50 % de
cada tinta, microdots y un rótulo con el nombre de cada tinta impreso <b>en esa tinta</b>. El contenido se reutiliza: el archivo no crece por copia.</p>
<h3>Distorsión flexo</h3>
<p>Compensa el alargamiento del cliché al montarlo: <b>D % = 2π · k / R · 100</b>, con k = espesor del cliché menos el de la base (de la tabla de tu
proveedor) y R = repetición en mm. También puedes escribir D % directamente. El PDF se comprime solo en la dirección elegida (100 mm con D = 2 % pasan a
98 mm) y se anota la distorsión en el margen.</p>
<h3>Braille</h3>
{fig("s10_braille", "Braille español grado 1 con geometría Marburg Medium.")}
<p>Traduce texto a braille español grado 1 con una tabla propia (letras, ñ, acentos, números con signo numérico, mayúsculas y puntuación básica) y dibuja los
puntos como vectores en la tinta técnica <b>Braille</b> con sobreimpresión. La geometría (diámetro 1,6 mm, puntos a 2,5 mm, celdas a 6 mm y líneas a
10 mm) es configurable: <b>verifícala con la norma EN 15823 o con tu proveedor</b>, y deja el braille lejos de pliegues, solapas y cortes.</p>
<h3>Gama extendida</h3>
<p>Para cada tinta directa del PDF calcula una <b>receta</b> con un juego fijo de tintas (por ejemplo CMYK + naranja, verde y violeta): hasta 3 tintas,
mejor 2, el ΔE estimado y un semáforo (≤ 2 verde, ≤ 4 amarillo, más de 4 rojo = no reproducible con ese juego). <b>Aplicar al PDF</b> sustituye las
directas convertibles por DeviceN de las tintas fijas. Es una estimación basada en un modelo: confirma con prueba impresa.</p>
<h3>Prueba en pantalla</h3>
<p>Simula el trabajo con las tintas reales, el sustrato (color y textura kraft, cartón o prenda), la ganancia de punto y la opción «ver sin blanco».
Lleva siempre la etiqueta <i>Vista orientativa, no es una prueba contractual</i>.</p>
<h3>Calibración del modelo</h3>
<p>Mejora la precisión de las simulaciones con tu proceso: 1) descarga el <b>gráfico</b> (rampas de 0 a 100 % y sobreimpresiones), 2) imprímelo con tus
tintas reales y mide los parches, 3) rellena la <b>plantilla CSV</b> con los Lab, 4) súbela: se ajustan el Lab del sólido, la ganancia de punto y el factor
n, y se guarda un perfil en <code>datos_locales/tintas/perfiles/</code>.</p>

<h1>29. Automatizar</h1>
{fig("s13_automatizar", "Editor de recetas: pasos con sus parámetros, reordenables, y ejecución sobre un archivo o una carpeta.")}
<p>Una <b>receta</b> es una lista de pasos (por ejemplo: <i>preflight → unir duplicadas → distorsión flexo → step &amp; repeat → exportar placas →
resumen</i>). Vienen tres de ejemplo: <b>Revisión rápida</b>, <b>Preparar etiqueta flexo</b> y <b>Separar logo para serigrafía</b>. Puedes crear las tuyas,
reordenar los pasos arrastrándolos, e importar o exportar el JSON.</p>
<ul>
<li><b>Sobre un archivo:</b> suéltalo en la zona de ejecución y descarga el resultado en un ZIP.</li>
<li><b>Sobre una carpeta:</b> indica la de entrada y la de salida. Los archivos correctos quedan en <code>salida/&lt;archivo&gt;/</code>; los que fallan o se detienen,
en <code>errores/</code> junto a su registro; los resúmenes, en <code>reportes/</code>.</li>
<li><b>Carpeta vigilada:</b> cada archivo nuevo que aparezca en la carpeta de entrada se procesa solo mientras FAVERVIEW esté abierto (se detiene desde el mismo panel).</li>
<li><b>Condiciones:</b> por ejemplo, el paso <i>preflight</i> puede detener el proceso y mover el archivo a <code>errores/</code> si hay errores.</li>
</ul>

<h1>30. Instalar Ghostscript</h1>
<p>Ghostscript (gratuito, de Artifex) se necesita para separar PDF en placas, medir cobertura, hacer trapping y otras funciones. No está en winget: usa
este comando de PowerShell, que descarga la versión oficial más reciente, <b>verifica su firma</b> y solo entonces la instala:</p>
<pre>$r = Invoke-RestMethod https://api.github.com/repos/ArtifexSoftware/ghostpdl-downloads/releases/latest; $a = $r.assets | ? name -like '*w64.exe'; $f = "$env:TEMP\\$($a.name)"; Invoke-WebRequest $a.browser_download_url -OutFile $f; $s = Get-AuthenticodeSignature $f; if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'Artifex') {{ Start-Process $f -ArgumentList '/S' -Verb RunAs -Wait; Write-Host 'Ghostscript instalado' }} else {{ Write-Host "Firma NO valida: $($s.Status). No se instalo." }}</pre>
<p>Comprueba la instalación:</p>
<pre>&amp; (Get-ChildItem "C:\\Program Files\\gs\\*\\bin\\gswin64c.exe" | Select -Last 1).FullName --version</pre>
<table>
<tr><th>Si algo falla</th><th>Qué hacer</th></tr>
<tr><td>Pide permisos de administrador y no los tienes</td><td>Pídele a quien administra el equipo que lo instale; sin Ghostscript el resto de la app funciona.</td></tr>
<tr><td>El antivirus lo bloquea</td><td>Revisa que la descarga sea de github.com/ArtifexSoftware; si la firma no es válida, <b>no lo instales</b>.</td></tr>
<tr><td>«Firma NO valida»</td><td>El comando no instala nada. Descarga el instalador desde ghostscript.com y comprueba su firma antes de ejecutarlo.</td></tr>
<tr><td>La app sigue sin encontrarlo</td><td>Reinicia FAVERVIEW. Si está en otra carpeta, indica la ruta en <code>ghostscript_cmd</code> de <code>data/config.json</code>.</td></tr>
</table>


<h1>33. Reventado (trapping) y tolerancia de registro</h1>
<p>En la máquina cada tinta sale de una pantalla, cliché o plancha distinta y <b>nunca caen exactamente en el mismo sitio</b> (mal registro). Si dos
colores solo se tocan en el borde, al moverse aparece un <b>filete</b> de sustrato (una línea blanca) o un solape feo. El <b>reventado</b> agranda un
color un poco <i>por debajo</i> del vecino para que, dentro de la <b>tolerancia de movimiento</b> de tu máquina, el borde siga cubierto.</p>
<h3>1. Elige (o crea) un perfil de máquina</h3>
<p>Un <b>perfil de máquina</b> guarda la tolerancia en mm, el factor del trap, el choke del blanco, la retracción del negro y otras reglas. Vienen
ejemplos <b>orientativos</b>: serigrafía textil manual 0,40 mm, serigrafía textil automática 0,20 mm, flexo banda angosta 0,15 mm, flexo banda ancha /
corrugado 0,25 mm, offset pliego 0,08 mm y digital 0 (sin trap). Tú puedes guardar los tuyos (incluso con una tolerancia distinta en x e y).</p>
<div class="aviso"><b>Cómo elegir la tolerancia:</b> imprime una prueba de registro (por ejemplo cruces y filetes finos en varias tintas) y mide
cuánto se mueve <b>realmente</b> tu máquina entre tintas. Usa ese valor: los de ejemplo son solo un punto de partida.</div>
<p><b>Ancho del trap = tolerancia × factor</b> (por defecto 1,0). El choke del blanco y la retracción del negro usan la tolerancia si no indicas otro valor.</p>
<h3>2. Dónde se aplica</h3>
<ul>
<li><b>Separar colores → Imagen:</b> la casilla <b>Auto-trap</b> viene activada con los perfiles de serigrafía y flexo. Se aplica a los canales antes del tramado y de
la exportación. Ves el <b>Mapa de traps</b> y la <b>Prueba de movimiento</b> (sin trap | con trap) y un mensaje como «✔ Sin filetes con ±0,20 mm». En el modo
índice no se aplica (no hay bordes a tope); en proceso simulado solo el choke del blanco y las tintas opacas.</li>
<li><b>Separar colores → PDF:</b> el botón <b>Auto-trap</b> usa el perfil elegido, muestra la vista con trap, el mapa, la prueba de movimiento y un
<b>deslizador de movimiento</b> que desplaza una placa hasta el doble de la tolerancia. El trap se aplica a las placas rasterizadas (sube la resolución a 300 dpi o más);
el PDF original no se modifica. El informe de separaciones incluye una sección «Trapping».</li>
<li><b>Vectorizar:</b> «Añadir trap para impresión» crea en el PDF una capa <b>Traps FAVERVIEW</b> con trazos en <b>sobreimpresión</b> recortados a la unión
de las dos regiones. Como las fronteras se comparten, el trap vectorial es exacto. El SVG no tiene sobreimpresión: lleva traps simulados.</li>
<li><b>Herramientas → Trapping:</b> lo mismo con tabla de anchos por par de tintas, trap reducido y tope de cobertura.</li>
<li><b>Preflight</b> (perfiles de serigrafía y flexo): la regla «Bordes sin protección de registro» avisa dónde un mal registro dejaría un filete.
<b>Automatizar:</b> los pasos <code>auto_trap</code> y <code>prueba_movimiento</code> (que puede mover el archivo a <code>errores/</code> si hay filetes).</li>
</ul>
<h3>3. Reglas que se aplican (orientativas)</h3>
<table>
<tr><th>Situación</th><th>Qué hace</th></tr>
<tr><td>Tinta técnica o barniz</td><td>Nunca se trapea.</td></tr>
<tr><td>Blanco (base)</td><td>Solo se contrae (choke).</td></tr>
<tr><td>Negro o tinta muy oscura</td><td>La otra se expande <b>bajo</b> la oscura; el negro no se mueve.</td></tr>
<tr><td>Luminosidad muy distinta</td><td>La más clara se expande bajo la más oscura.</td></tr>
<tr><td>Luminosidad parecida</td><td><b>Trap centrado</b>: cada tinta se expande la mitad hacia la otra.</td></tr>
<tr><td>Tinta opaca contra transparente</td><td>La transparente se expande bajo la opaca.</td></tr>
<tr><td>Negro enriquecido (K + CMY)</td><td>Retracción de CMY desde el borde del negro.</td></tr>
<tr><td>Objetos finos</td><td>El trap se limita a un tercio del grosor del objeto que se expande.</td></tr>
<tr><td>Texto pequeño (PDF)</td><td>Sin trap.</td></tr>
<tr><td>Degradados</td><td>Solo se trapea entre zonas sólidas (≥ 50 %); tope de cobertura total en la zona.</td></tr>
</table>
<h3>4. La prueba de movimiento</h3>
<p>Para comprobar que la tolerancia se cumple, cada placa se desplaza una distancia igual a la tolerancia en 8 direcciones y se cuentan los <b>filetes</b>: píxeles entre dos
zonas entintadas que estaban cubiertos y dejan de estarlo. Con el trap debe dar <b>0</b>; con el movimiento al doble de la tolerancia dará filetes (así se ve que la
prueba mide algo). El resultado se muestra en mm² y como mapa (filetes en magenta).</p>
<h3>Límites</h3>
<ul>
<li>Es una <b>estimación</b>: confirma con tu imprenta. No sustituye una prueba de máquina.</li>
<li>Un objeto de debajo más fino que el trap no se puede proteger del todo (el trap no puede salir al sustrato).</li>
<li>El trap vectorial funciona con arte plano; con degradados, transparencias o imágenes usa las placas con trap (ráster) o el Buscatrazos de Illustrator.</li>
<li>La retracción del negro, los objetos finos y el texto pequeño solo se aplican en el trap por placas, no en el vectorial.</li>
</ul>


<h1>34. FAVERVIEW en Illustrator</h1>
<p>El <b>plugin de Illustrator</b> es un panel que se conecta con FAVERVIEW (debe estar abierto) para usar sus herramientas sin salir de Illustrator. Funciona con
Illustrator 2024, 2025 y 2026. Es un <b>puente</b>: exporta una copia de tu mesa, FAVERVIEW la analiza en tu equipo y el resultado vuelve al documento. No se conecta a internet.</p>
<div class="nota"><b>Estado de las pruebas:</b> todo lo que se puede comprobar sin Illustrator ya está probado automáticamente. Las pruebas que necesitan Illustrator real están en
<code>plugin/PRUEBAS_MANUALES.md</code> y las ejecuta el usuario; hasta entonces el panel debe considerarse <b>sin validar en Illustrator</b>.</div>
<h3>Instalación</h3>
<ol>
<li>Descarga <code>FAVERVIEW-Illustrator-&lt;versión&gt;.zxp</code> del Release de GitHub (firmado con el certificado propio del taller).</li>
<li>En PowerShell, con el instalador oficial de Creative Cloud (verifica la ruta en tu equipo):
<pre>&amp; "C:\\Program Files\\Common Files\\Adobe\\Adobe Desktop Common\\RemoteComponents\\UPI\\UnifiedPluginInstallerAgent\\UnifiedPluginInstallerAgent.exe" /install "C:\\ruta\\FAVERVIEW-Illustrator-3.2.0.zxp"</pre></li>
<li>Reinicia Illustrator y abre <b>Ventana → Extensiones → FAVERVIEW</b>.</li>
</ol>
<p>Para actualizar instala el <code>.zxp</code> nuevo (el panel avisa en <b>Ajustes</b>); para desinstalar: <code>UnifiedPluginInstallerAgent.exe /remove com.faverview.illustrator</code>.</p>
<h3>La conexión</h3>
<table>
<tr><th>Indicador</th><th>Significa</th></tr>
<tr><td>🟢 Conectado a FAVERVIEW</td><td>Todo listo.</td></tr>
<tr><td>🟡 Versión incompatible</td><td>Actualiza FAVERVIEW o el plugin (el mensaje dice cuál).</td></tr>
<tr><td>🔴 FAVERVIEW no está abierto</td><td>Abre FAVERVIEW desde su acceso directo; el panel reintenta solo cada 5 segundos.</td></tr>
</table>
<p>La comunicación usa un <b>token</b> que FAVERVIEW guarda en <code>%APPDATA%\\FAVERVIEW\\plugin.json</code>: ninguna página web puede llamar a la API de tu equipo.</p>
<h3>Las pestañas</h3>
{fig("p01_vectorizar", "Vectorizar: la imagen seleccionada se vectoriza y se coloca encima.", 42)}
<ul>
<li><b>Vectorizar:</b> con una imagen seleccionada (vinculada o incrustada, incluso rotada) elige preajuste, colores, detalle, tintas de tu biblioteca y, si quieres, el trap. Ves una
vista previa y <b>Colocar sobre la imagen</b> pone el vector en la capa «FAVERVIEW – Vector», con las mismas posición, tamaño y rotación, y con muestras spot (sin duplicar las que ya existen).</li>
</ul>
{fig("p02_preflight", "Preflight: resultados por severidad, clic para hacer zoom y correcciones nativas.", 42)}
<ul>
<li><b>Preflight:</b> revisa la mesa actual o todas con un perfil. Un clic en un hallazgo hace <b>zoom y selecciona</b> los objetos de esa zona; «Marcar todos» dibuja marcadores en la capa
«FAVERVIEW – Revisión» (bloqueada y que no se imprime). Las <b>correcciones nativas</b> trabajan sobre tu documento (siguen siendo editables): sobreimpresión en tintas técnicas, texto negro
pequeño a K 100 %, unir muestras spot duplicadas y eliminar las que no se usan. Cada una tiene «Ver» (cuántos objetos afecta), confirmación y se puede deshacer con Ctrl+Z.</li>
<li><b>Separar:</b> muestra las tintas del PDF frente a las muestras del documento (avisa de las que faltan y de las que sobran), la cobertura por tinta, el TAC máximo, los problemas de separación
(clic → zoom), las placas («Solo» y «Negativo»), un densitómetro (toca la vista previa) y «Exportar placas…».</li>
<li><b>Comparar:</b> elige el arte del cliente (o pégalo con Ctrl+V) y compáralo con la mesa: marca las diferencias en el documento y puedes abrir la comparación completa en FAVERVIEW.</li>
</ul>
{fig("p03_codigos", "Códigos: vista previa con validación en vivo e inserción como vector.", 42)}
<ul>
<li><b>Códigos:</b> genera EAN/UPC, ITF-14, Code 128, GS1-128, Code 39, DataBar, DataMatrix, GS1 DataMatrix y QR con validación en vivo, y braille (tinta técnica «Braille» en sobreimpresión). «Insertar»
lo coloca como vector en el centro de la vista o de la selección. «Verificar códigos del documento» decodifica los de la mesa y estima su grado (no certificado).</li>
</ul>
{fig("p04_trap", "Trap: prueba de movimiento con la tolerancia de la máquina.", 42)}
<ul>
<li><b>Trap:</b> elige el perfil de máquina y la tolerancia. <b>Analizar registro</b> hace la prueba de movimiento de la mesa y marca los filetes en el documento; <b>Crear traps vectoriales</b> (solo arte
plano) añade en la capa «FAVERVIEW – Traps» los trazos de trap, en sobreimpresión y con las mismas tintas. Con degradados, transparencias o imágenes el panel lo dice y propone las placas con trap (ráster).
También puedes usar <b>Buscatrazos → Reventar</b> de Illustrator para casos simples. Es una estimación: confirma con tu imprenta.</li>
</ul>
<h3>Qué no hace el plugin</h3>
<ul>
<li>No modifica tu documento sin una acción explícita (colocar, corregir, marcar), y todo se puede deshacer.</li>
<li>No corrige RGB a CMYK ni incrusta fuentes: solo lo reporta.</li>
<li>La versión actual usa CEP; Adobe lo retirará en 2028–2029 y el panel está preparado para migrar a UXP (<code>plugin/MIGRACION_UXP.md</code>).</li>
</ul>

<h1>31. Glosario de preprensa</h1>
<table>
<tr><th>Término</th><th>Significado</th></tr>
<tr><td>TAC / cobertura total</td><td>Suma de los porcentajes de todas las tintas en un punto (máximo 400 % con CMYK). Cada proceso tiene su límite.</td></tr>
<tr><td>Placa / separación</td><td>Imagen de una sola tinta: dónde y cuánto se imprime ese color.</td></tr>
<tr><td>Tinta directa (spot)</td><td>Tinta premezclada (Pantone, por ejemplo) que se imprime con su propia placa.</td></tr>
<tr><td>Separation / DeviceN</td><td>Formas de definir tintas directas en un PDF: una tinta, o varias en un mismo espacio.</td></tr>
<tr><td>Sobreimpresión</td><td>Imprimir una tinta encima de otra en vez de borrar lo de abajo (<i>knockout</i>).</td></tr>
<tr><td>Trapping (reventado)</td><td>Solapar un poco dos colores vecinos para que un mal registro no deje huecos blancos.</td></tr>
<tr><td>Choke</td><td>Reducir un objeto (típicamente el blanco) para que no asome por los bordes.</td></tr>
<tr><td>Tolerancia de registro / filete</td><td>Movimiento máximo entre tintas de tu máquina / línea de sustrato que aparece entre dos colores cuando se mueven.</td></tr>
<tr><td>Registro</td><td>Alineación de las placas entre sí; las marcas de registro sirven para comprobarla.</td></tr>
<tr><td>Sangrado / TrimBox / BleedBox</td><td>Margen de arte más allá del corte / caja del tamaño final / caja del arte con sangrado.</td></tr>
<tr><td>Ganancia de punto</td><td>El punto impreso sale más grande que el de la placa; se compensa con curvas o con BWR en códigos de barras.</td></tr>
<tr><td>Lineatura (lpi) y ángulo</td><td>Líneas de puntos por pulgada de la trama y su inclinación, distinta por tinta para evitar muaré.</td></tr>
<tr><td>Tramado AM / FM</td><td>Puntos de tamaño variable (AM) o puntos diminutos de posición variable (FM, estocástico).</td></tr>
<tr><td>BWR</td><td>Reducción de barras: se adelgazan las barras del código para compensar la ganancia de punto.</td></tr>
<tr><td>Módulo X</td><td>Ancho de la barra o cuadro más fino de un código de barras.</td></tr>
<tr><td>Lab / ΔE</td><td>Espacio de color independiente del dispositivo / distancia entre dos colores (ΔE2000; alrededor de 2 apenas se nota).</td></tr>
<tr><td>GCR</td><td>Sustitución de gris: reemplazar CMY por negro para bajar la cobertura total.</td></tr>
<tr><td>OutputIntent / PDF/X</td><td>Condición de impresión declarada en el PDF / familia de PDF pensada para imprenta.</td></tr>
<tr><td>Step &amp; repeat</td><td>Repetir la etiqueta en una hoja o banda para imprimir varias a la vez.</td></tr>
<tr><td>Distorsión (flexo)</td><td>Compensación del alargamiento del cliché al montarlo en el cilindro.</td></tr>
</table>

<h1>32. Qué es exacto y qué es una estimación</h1>
<ul>
<li><b>Exacto:</b> inventario de tintas, porcentajes de cobertura de las placas, geometría de la imposición, fórmulas (distorsión flexo), decodificación
de los códigos, ausencia de huecos entre regiones vectorizadas.</li>
<li><b>Estimación orientativa:</b> colores simulados (modelo de mezcla no espectral), ΔE de las recetas, trapping, prueba en pantalla, grado A–F de
códigos y semáforos. Se afinan con la calibración, pero <b>nunca sustituyen una prueba impresa</b>.</li>
<li><b>Sin certificación:</b> los perfiles de preflight están «inspirados en GWG 2015» y el grado de códigos «inspirado en ISO/IEC 15416»: ninguno es una
verificación certificada.</li>
</ul>
"""
