"""Contenido HTML de los documentos PDF (además del Manual de uso): instalación y actualización, plugin de Illustrator,
guía rápida y guía del mantenedor. Lo usa build.py."""

REPO = "https://github.com/sebastiansantos0311-dev/faverview"
# Los comandos de los PDF van en líneas cortas (≤ 88 caracteres): al copiar desde un PDF, un salto de línea visual dentro de
# un comando largo se copia y lo rompe. Cada línea es válida por sí sola y el bloque se pega entero en PowerShell.
NOTA_PEGAR = ('<p class="nota">Si un comando ocupa varias líneas, <b>cópialas todas juntas</b> y pégalas de una vez en PowerShell; '
              'se ejecutan en orden.</p>')

UPIA_SET = ('$upi = "C:\\Program Files\\Common Files\\Adobe\\Adobe Desktop Common\\RemoteComponents\\UPI"\n'
            '$upia = "$upi\\UnifiedPluginInstallerAgent\\UnifiedPluginInstallerAgent.exe"')
UPIA_FIND = ('$dir = "C:\\Program Files\\Common Files\\Adobe"\n'
             'Get-ChildItem $dir -Recurse -Filter UnifiedPluginInstallerAgent.exe -EA SilentlyContinue')

GS_CMD = ("$api = \"https://api.github.com/repos/ArtifexSoftware/ghostpdl-downloads/releases/latest\"\n"
          "$a = (Invoke-RestMethod $api).assets | ? name -like '*w64.exe'\n"
          "$f = \"$env:TEMP\\$($a.name)\"\n"
          "Invoke-WebRequest $a.browser_download_url -OutFile $f\n"
          "$s = Get-AuthenticodeSignature $f\n"
          "if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'Artifex') {\n"
          "  Start-Process $f -ArgumentList '/S' -Verb RunAs -Wait; 'Ghostscript instalado'\n"
          "} else { \"Firma NO valida: $($s.Status). No se instalo.\" }")


# ============================================================================ INSTALACIÓN Y ACTUALIZACIÓN
def guia_instalacion(version: str) -> str:
    return f"""
<h1>Contenido</h1>
<ol>
<li>Antes de empezar</li>
<li>Instalación paso a paso</li>
<li>Comprobar que todo funciona</li>
<li>Uso diario</li>
<li>Instalar el plugin de Illustrator (opcional)</li>
<li>Actualizar FAVERVIEW</li>
<li>Actualizar el plugin, Tesseract y Ghostscript</li>
<li>Qué versión tengo</li>
<li>Instalar en varios equipos y llevar tus datos</li>
<li>Desinstalar</li>
<li>Si algo falla</li>
</ol>

<h1>1. Antes de empezar</h1>
<h3>Qué necesitas</h3>
<ul>
<li>Un computador con <b>Windows 10 u 11</b> (64 bits).</li>
<li><b>Internet</b> solo para instalar y actualizar. La app funciona sin conexión.</li>
<li>Unos <b>2 GB libres</b> de disco y entre 5 y 10 minutos.</li>
<li>No hace falta ser administrador (salvo para Ghostscript, paso 2b).</li>
</ul>
<h3>Qué se instala</h3>
<table>
<tr><th>Programa</th><th>Para qué sirve</th><th>¿Obligatorio?</th></tr>
<tr><td>uv</td><td>Descarga Python y las librerías de la app automáticamente.</td><td>Sí</td></tr>
<tr><td>Git</td><td>Descarga FAVERVIEW desde GitHub y permite actualizarlo.</td><td>Sí</td></tr>
<tr><td>Tesseract OCR</td><td>Lee el texto de las imágenes (Comparar).</td><td>Sí</td></tr>
<tr><td>Ghostscript</td><td>Separa PDF en placas, cobertura, trapping, códigos de barras y EPS.</td><td>Recomendado</td></tr>
<tr><td>Plugin de Illustrator</td><td>Usar las herramientas dentro de Illustrator 2024, 2025 o 2026.</td><td>Opcional</td></tr>
</table>
<div class="nota"><b>¿Por qué no hay un instalador .exe?</b> Windows y los antivirus marcan como sospechosos los ejecutables sin firma digital.
FAVERVIEW se instala con <b>winget</b> (el instalador oficial de Windows) y con paquetes firmados, así que no aparecen avisos de virus.</div>

<h1>2. Instalación paso a paso</h1>
<p>Solo se hace <b>una vez</b> por computador.</p>
<h2>Paso 1 – Abrir PowerShell</h2>
<p>Menú Inicio → escribe <b>PowerShell</b> → ábrelo. No hace falta abrirlo como administrador.</p>
<h2>Paso 2 – Instalar las herramientas</h2>
<p>Copia y pega este comando y presiona Enter. Acepta los permisos si Windows los pide.</p>
<pre>winget install -e --id astral-sh.uv
winget install -e --id Git.Git
winget install -e --id UB-Mannheim.TesseractOCR</pre>
{NOTA_PEGAR}
<p><b>Cierra PowerShell y ábrelo de nuevo</b> para que Windows reconozca los programas nuevos.</p>
<h2>Paso 2b – Instalar Ghostscript (recomendado)</h2>
<p>No está en winget. Este comando descarga la versión oficial de Artifex, <b>verifica su firma</b> y solo entonces la instala (pide permiso de
administrador). Sin Ghostscript la app funciona, pero Separar colores, Códigos de barras y parte de Herramientas quedan desactivados.</p>
<pre>{GS_CMD}</pre>
<p>Si dice «Firma NO valida» no se instala nada: descarga Ghostscript desde ghostscript.com y comprueba la firma antes de ejecutarlo.</p>
<h2>Paso 3 – Descargar FAVERVIEW</h2>
<pre>git clone {REPO}.git $HOME\\FAVERVIEW</pre>
<p>Crea la carpeta <code>FAVERVIEW</code> en tu carpeta de usuario. Usa siempre <code>git clone</code> (no el ZIP): así funcionan las actualizaciones automáticas.</p>
<h2>Paso 4 – Primer arranque</h2>
<pre>cd $HOME\\FAVERVIEW; uv run faverview</pre>
<p>La primera vez descarga Python y las librerías (unos minutos). Después se abre el navegador con la aplicación.</p>
<h2>Paso 5 – Acceso directo (automático)</h2>
<p>En el primer arranque FAVERVIEW crea el acceso directo <b>FAVERVIEW</b> con su logo en el Escritorio y en la carpeta de la app. Si lo borras:</p>
<pre>cd $HOME\\FAVERVIEW; uv run faverview --acceso-directo</pre>

<h1>3. Comprobar que todo funciona</h1>
<ol>
<li>Mira el <b>pie de la página</b>: debe decir <b>FAVERVIEW v{version}</b> (o la versión que hayas instalado).</li>
<li>Si una pestaña aparece con aviso (por ejemplo «falta Ghostscript»), pasa el ratón por encima: te dice qué instalar.</li>
<li>Pestaña <b>Comparar</b>: arrastra <code>samples\\cliente_errores.png</code> a la zona A y <code>samples\\diseno.pdf</code> a la zona B y pulsa
<b>Comparar</b>. Debes ver cerca de <b>96 % «Revisar»</b> con 4 errores. Con <code>samples\\cliente_ok.png</code> debe dar <b>100 % «Aprobado»</b>.</li>
<li>Opcional (unos 3 minutos): <code>cd $HOME\\FAVERVIEW; uv run pytest</code> debe terminar con «passed» y sin «failed».</li>
</ol>

<h1>4. Uso diario</h1>
<ol>
<li>Doble clic en el acceso directo <b>FAVERVIEW</b>.</li>
<li>Se abre una ventana negra (el servidor) y el navegador. <b>No cierres la ventana negra</b> mientras usas la app.</li>
<li>Para salir, cierra la ventana negra.</li>
</ol>
<p>La app solo es accesible desde tu propio equipo (127.0.0.1), no desde la red. Si el puerto 8000 está ocupado usa el siguiente libre; la dirección aparece en la ventana negra.</p>

<h1>5. Instalar el plugin de Illustrator (opcional)</h1>
<p>Necesitas <b>Illustrator 2024, 2025 o 2026</b> con Creative Cloud, y FAVERVIEW instalado (pasos 1 a 5).</p>
<ol>
<li>Descarga <code>FAVERVIEW-Illustrator-&lt;versión&gt;.zxp</code> de la sección <b>Releases</b> de {REPO} (o pídeselo a quien mantiene la app).
Debe ser un archivo <b>firmado</b>; los <code>.zxp</code> sin firma no se pueden instalar.</li>
<li>Cierra Illustrator. En PowerShell (cambia la ruta del archivo):
<pre>{UPIA_SET}
&amp; $upia /install "$HOME\\Downloads\\FAVERVIEW-Illustrator-{version}.zxp"</pre>
Es el instalador oficial de Creative Cloud. Si esa ruta no existe en tu equipo, búscalo con:
<pre>{UPIA_FIND}</pre></li>
<li>Abre FAVERVIEW y luego Illustrator → <b>Ventana → Extensiones → FAVERVIEW</b>. El panel debe mostrar <span style="color:#16a34a">●</span> <b>Conectado a FAVERVIEW</b>.</li>
</ol>
<p>El uso del panel está en el <b>Manual del plugin de Illustrator</b>.</p>

<h1>6. Actualizar FAVERVIEW</h1>
<h3>La app revisa sola si hay actualizaciones</h3>
<ul>
<li>Una vez al día, si hay internet, FAVERVIEW consulta GitHub <b>sin bloquear el arranque</b>.</li>
<li>Si hay una versión nueva, aparece arriba un <b>aviso azul</b> con el número de versión, el botón <b>Actualizar</b> y un desplegable
<b>Novedades</b> con lo que trae. El aviso se mantiene aunque cierres y vuelvas a abrir la app.</li>
<li>Para comprobarlo en el momento, pulsa <b>Buscar actualizaciones</b> en el pie de la página. Te dirá «Tienes la última versión (x.y.z)», mostrará el aviso o indicará si no hay internet.</li>
</ul>
<h3>Cómo actualizar</h3>
<ol>
<li>Pulsa <b>Actualizar</b> en el aviso azul.</li>
<li>Cuando diga «Actualizado», <b>cierra la ventana negra</b> y vuelve a abrir FAVERVIEW con el acceso directo.</li>
<li>La primera apertura puede tardar un poco más si la versión nueva trae librerías nuevas (uv las instala solo).</li>
<li>Comprueba el número de versión en el pie de la página.</li>
</ol>
<h3>Actualizar a mano</h3>
<pre>cd $HOME\\FAVERVIEW; git pull</pre>
<h3>Si el botón Actualizar no funciona</h3>
<table>
<tr><th>Mensaje</th><th>Qué hacer</th></tr>
<tr><td>«Hay cambios locales sin guardar en la carpeta de la app»</td><td>Alguien modificó archivos de la app. Para descartar esos cambios y actualizar:
<code>cd $HOME\\FAVERVIEW; git stash; git pull</code> (tus datos en <code>data</code> y <code>datos_locales</code> no se tocan).</td></tr>
<tr><td>«La carpeta de la app está en la rama X»</td><td><code>cd $HOME\\FAVERVIEW; git switch main; git pull</code></td></tr>
<tr><td>«No se pudo consultar GitHub»</td><td>Sin internet o bloqueado por un proxy: inténtalo más tarde.</td></tr>
<tr><td>Instalaste desde un ZIP</td><td>El aviso no funciona. Reinstala con <code>git clone</code> (paso 3) y copia tus carpetas <code>data</code> y <code>datos_locales</code>.</td></tr>
</table>
<div class="nota">Actualizar <b>nunca</b> borra tus datos: resultados, diccionario personal, plantillas, bibliotecas de tintas, perfiles de máquina y
lo aprendido por el OCR viven en <code>data</code> y <code>datos_locales</code>, que git no toca.</div>

<h1>7. Actualizar el plugin, Tesseract y Ghostscript</h1>
<h3>Plugin de Illustrator</h3>
<p>La pestaña <b>Ajustes</b> del panel avisa cuando hay un <code>.zxp</code> nuevo en los Releases de GitHub. Para actualizar, cierra Illustrator e instala
el <code>.zxp</code> nuevo con el mismo comando de la sección 5 (reemplaza la versión anterior). Actualiza también FAVERVIEW: si una de las dos partes es
demasiado antigua, el panel muestra <span style="color:#d97706">●</span> «Versión incompatible» y te dice cuál actualizar.</p>
<h3>Tesseract y el resto de herramientas instaladas con winget</h3>
<pre>winget upgrade -e --id UB-Mannheim.TesseractOCR
winget upgrade -e --id astral-sh.uv
winget upgrade -e --id Git.Git</pre>
<h3>Ghostscript</h3>
<p>Vuelve a ejecutar el comando del paso 2b: instala la última versión oficial (con la firma verificada). FAVERVIEW usa siempre la versión más alta instalada.</p>

<h1>8. Qué versión tengo</h1>
<table>
<tr><th>Qué</th><th>Dónde se ve</th></tr>
<tr><td>FAVERVIEW</td><td>Pie de la página de la app, o <code>http://127.0.0.1:8000/api/version</code></td></tr>
<tr><td>Plugin de Illustrator</td><td>Pestaña <b>Ajustes</b> del panel («Versión del panel»)</td></tr>
<tr><td>Tesseract y Ghostscript</td><td>Los detecta la app al arrancar (<code>http://127.0.0.1:8000/api/status</code>); si falta alguno, la pestaña afectada muestra un aviso</td></tr>
</table>

<h1>9. Instalar en varios equipos y llevar tus datos</h1>
<ul>
<li>Repite los pasos 1 a 5 (y 5 del plugin si lo usas) en cada computador. No copies la carpeta <code>.venv</code> de otro equipo.</li>
<li><b>Lo aprendido por el OCR:</b> en el equipo de origen, <b>Aprendizaje → Exportar</b>; en el nuevo, <b>Importar</b>. Por defecto no incluye imágenes de clientes.</li>
<li><b>Bibliotecas de tintas y perfiles de máquina:</b> están en <code>datos_locales\\tintas</code> y <code>datos_locales\\prensas</code>; cópialos a mano.</li>
<li><b>Casos de prueba, plantillas y diccionario personal:</b> <code>datos_locales</code> y <code>data</code>.</li>
</ul>

<h1>10. Desinstalar</h1>
<ol>
<li>Plugin (si lo instalaste): cierra Illustrator y ejecuta:<pre>{UPIA_SET}
&amp; $upia /remove com.faverview.illustrator</pre></li>
<li>Cierra FAVERVIEW. Copia <code>datos_locales</code> y <code>data</code> si quieres conservar tus datos, y borra la carpeta <code>FAVERVIEW</code>.</li>
<li>Borra el acceso directo del Escritorio y, si quieres, la carpeta <code>%APPDATA%\\FAVERVIEW</code> (datos de conexión del plugin).</li>
<li>Si ya no los necesitas: <code>winget uninstall astral-sh.uv</code>, <code>winget uninstall Git.Git</code>, <code>winget uninstall UB-Mannheim.TesseractOCR</code> y
Ghostscript desde <b>Configuración → Aplicaciones</b>.</li>
</ol>

<h1>11. Si algo falla</h1>
<table>
<tr><th>Problema</th><th>Solución</th></tr>
<tr><td>«winget no se reconoce»</td><td>Instala <b>App Installer</b> desde Microsoft Store y vuelve a abrir PowerShell.</td></tr>
<tr><td>«uv» o «git» no se reconoce</td><td>Cierra y vuelve a abrir PowerShell. Si sigue igual, reinicia el equipo.</td></tr>
<tr><td>Aviso «no se encontró Tesseract»</td><td><code>winget install UB-Mannheim.TesseractOCR</code> y reinicia la app.</td></tr>
<tr><td>Aviso «falta Ghostscript»</td><td>Paso 2b y reinicia la app.</td></tr>
<tr><td>El navegador no se abre</td><td>Abre a mano la dirección de la ventana negra (por ejemplo <code>http://127.0.0.1:8000</code>).</td></tr>
<tr><td>La primera vez tarda mucho</td><td>Normal: descarga Python y las librerías. Las siguientes veces abre en segundos.</td></tr>
<tr><td>El antivirus o SmartScreen avisa</td><td>FAVERVIEW no trae ejecutables propios. Si usaste <code>git clone</code> y winget no debería aparecer; revisa qué archivo señala.</td></tr>
<tr><td>El plugin no aparece en Illustrator</td><td>Instala un <code>.zxp</code> <b>firmado</b> con Illustrator cerrado y reinícialo. Ver el Manual del plugin.</td></tr>
<tr><td>El panel dice <span style="color:#dc2626">●</span> con FAVERVIEW abierto</td><td>Cierra y abre FAVERVIEW; comprueba que existe <code>%APPDATA%\\FAVERVIEW\\plugin.json</code>.</td></tr>
</table>
<div class="nota">¿Sigues con problemas? Anota el mensaje exacto de la ventana negra, de PowerShell o del panel; casi siempre dice qué falta.</div>
"""


# ============================================================================ PLUGIN DE ILLUSTRATOR
def manual_plugin(fig, version: str) -> str:
    return f"""
<h1>Contenido</h1>
<ol>
<li>Qué es y cómo funciona</li>
<li>Requisitos</li>
<li>Instalar, actualizar y desinstalar</li>
<li>Primeros pasos y conexión</li>
<li>Vectorizar</li>
<li>Preflight y correcciones</li>
<li>Separar</li>
<li>Comparar</li>
<li>Códigos de barras y braille</li>
<li>Trap (reventado)</li>
<li>Ajustes</li>
<li>Seguridad y privacidad</li>
<li>Si algo falla</li>
<li>Estado de validación y pruebas manuales</li>
</ol>

<h1>1. Qué es y cómo funciona</h1>
<p>El plugin es un <b>panel dentro de Illustrator</b> que usa las herramientas de FAVERVIEW sin salir del programa. Es un <b>puente</b>: exporta una
<b>copia</b> de tu mesa de trabajo (o la imagen seleccionada), FAVERVIEW la analiza en tu equipo y el resultado vuelve al documento
(vectores, marcadores, correcciones, códigos). No se conecta a internet: solo habla con FAVERVIEW en <code>127.0.0.1</code>.</p>
<div class="nota"><b>Regla de oro:</b> el panel nunca modifica tu documento sin que pulses una acción (Colocar, Aplicar, Marcar, Insertar), y todo se
puede deshacer con Ctrl+Z.</div>

<h1>2. Requisitos</h1>
<ul>
<li><b>Illustrator 2024 (v28), 2025 (v29) o 2026 (v30)</b> en Windows. macOS es compatible pero no se ha probado.</li>
<li><b>FAVERVIEW {version} o superior abierto</b> (acceso directo). Ghostscript instalado para Separar, Trap y Códigos.</li>
<li>El archivo <code>FAVERVIEW-Illustrator-&lt;versión&gt;.zxp</code> <b>firmado</b>.</li>
</ul>

<h1>3. Instalar, actualizar y desinstalar</h1>
<h3>Instalar</h3>
<ol>
<li>Descarga el <code>.zxp</code> de la sección <b>Releases</b> de {REPO}.</li>
<li>Cierra Illustrator y ejecuta en PowerShell (cambia la ruta del archivo):
<pre>{UPIA_SET}
&amp; $upia /install "$HOME\\Downloads\\FAVERVIEW-Illustrator-{version}.zxp"</pre>
Si esa ruta no existe:
<pre>{UPIA_FIND}</pre></li>
<li>Abre Illustrator → <b>Ventana → Extensiones → FAVERVIEW</b>.</li>
</ol>
<h3>Actualizar</h3>
<p>La pestaña <b>Ajustes</b> avisa cuando hay un <code>.zxp</code> nuevo. Cierra Illustrator e instala el nuevo con el mismo comando. Mantén también
FAVERVIEW actualizado (su propio aviso azul): si las versiones no son compatibles, el panel muestra <span style="color:#d97706">●</span> y dice cuál actualizar.</p>
<h3>Desinstalar</h3>
<pre>{UPIA_SET}
&amp; $upia /remove com.faverview.illustrator</pre>

<h1>4. Primeros pasos y conexión</h1>
<ol>
<li>Abre <b>FAVERVIEW</b> primero y después Illustrator.</li>
<li>Abre el panel: <b>Ventana → Extensiones → FAVERVIEW</b>. Puedes acoplarlo junto a tus otros paneles.</li>
<li>Arriba verás el indicador de conexión:</li>
</ol>
<table>
<tr><th>Indicador</th><th>Significa</th><th>Qué hacer</th></tr>
<tr><td><span style="color:#16a34a">●</span> Conectado a FAVERVIEW</td><td>Todo listo.</td><td>—</td></tr>
<tr><td><span style="color:#d97706">●</span> Versión incompatible</td><td>El plugin y FAVERVIEW no son compatibles.</td><td>Actualiza el que indica el mensaje.</td></tr>
<tr><td><span style="color:#dc2626">●</span> FAVERVIEW no está abierto</td><td>No encuentra la app.</td><td>Ábrela con su acceso directo; el panel reintenta solo cada 5 s.</td></tr>
</table>
<p>Los análisis trabajan sobre la <b>mesa de trabajo activa</b> (o todas, cuando la pestaña lo ofrece). Los archivos temporales van a
<code>%TEMP%\\FAVERVIEW</code> y se borran solos a las 24 horas.</p>

<h1>5. Vectorizar</h1>
{fig("p01_vectorizar", "Pestaña Vectorizar.", 45)}
<ol>
<li>Selecciona una imagen colocada (vinculada o incrustada, incluso rotada).</li>
<li>Elige el <b>preajuste</b> (Logo, Línea, Ilustración, Escaneo, Foto posterizada), el número de colores y el detalle mínimo.</li>
<li>Opcional: <b>Usar tintas de la biblioteca</b> (tus tintas de FAVERVIEW) y <b>Añadir trap</b> con tu perfil de máquina.</li>
<li>Pulsa <b>Vectorizar</b> y revisa la vista previa y las estadísticas (nodos, trazados, colores).</li>
<li><b>Colocar sobre la imagen</b>: el vector queda en la capa «FAVERVIEW – Vector» con la misma posición, tamaño y rotación, y las tintas como
muestras spot (sin duplicar las que ya existen). Los traps quedan en un subgrupo aparte, en sobreimpresión.</li>
</ol>

<h1>6. Preflight y correcciones</h1>
{fig("p02_preflight", "Pestaña Preflight.", 45)}
<ol>
<li>Elige el perfil (offset, flexo, serigrafía, digital…) y pulsa <b>Revisar mesa actual</b> o <b>Revisar todas las mesas</b>.</li>
<li>Los hallazgos aparecen por severidad (errores, advertencias, información). <b>Clic</b> en uno: hace zoom y selecciona los objetos de esa zona.</li>
<li><b>Marcar todos</b> dibuja marcadores numerados en la capa «FAVERVIEW – Revisión» (bloqueada y que <b>no se imprime</b>); <b>Quitar marcas</b> la borra.</li>
</ol>
<h3>Correcciones nativas</h3>
<p>Trabajan sobre tu documento, que sigue siendo editable. Cada una tiene <b>Ver</b> (cuántos objetos afecta), confirmación y Ctrl+Z:</p>
<ul>
<li>Sobreimpresión en tintas técnicas (troquel, cotas, braille).</li>
<li>Texto negro pequeño a K 100 % con sobreimpresión.</li>
<li>Unir muestras spot duplicadas («PANTONE 485 C» y «Pantone 485C»).</li>
<li>Eliminar muestras que no se usan.</li>
</ul>
<p>RGB a CMYK y fuentes que faltan <b>solo se reportan</b>: corrígelos tú en Illustrator. Después de corregir se vuelve a revisar solo.</p>

<h1>7. Separar</h1>
<ul>
<li><b>Analizar separaciones</b> de la mesa: lista de tintas del PDF comparada con las muestras del documento (avisa de muestras sin uso y de tintas sin muestra),
cobertura por tinta, TAC máximo según el perfil y problemas de separación (clic → zoom).</li>
<li><b>Placas:</b> miniatura por tinta, con «Solo» y «Negativo».</li>
<li><b>Densitómetro:</b> toca la vista previa y verás el % de cada tinta en ese punto.</li>
<li><b>Exportar placas…</b> guarda un ZIP con TIFF o PDF de placas; <b>Abrir en FAVERVIEW</b> lleva el análisis a la app completa.</li>
</ul>

<h1>8. Comparar</h1>
<ol>
<li>Elige el arte del cliente (JPG, PNG, PDF…) o pégalo con <b>Ctrl+V</b>.</li>
<li>Pulsa <b>Comparar</b>: verás el % de similitud, el semáforo y la lista de diferencias.</li>
<li>Las diferencias se marcan sobre tu diseño (capa de revisión); clic en la lista → zoom. <b>Ver comparación completa en FAVERVIEW</b> abre todas las vistas.</li>
</ol>

<h1>9. Códigos de barras y braille</h1>
{fig("p03_codigos", "Pestaña Códigos.", 45)}
<ul>
<li>Tipos: EAN-13/8, UPC-A/E, ITF-14, Code 128, GS1-128, Code 39, GS1 DataBar, DataMatrix, GS1 DataMatrix y QR. La validación es en vivo
(dígito de control, longitudes, AIs de GS1).</li>
<li>Ajusta magnificación, altura, reducción de barras (BWR) y tinta; <b>Insertar</b> lo coloca como vector en el centro de la vista o de la selección.</li>
<li><b>Verificar códigos del documento</b>: decodifica los de la mesa y estima el grado (A–F, orientativo, no certificado).</li>
<li><b>Braille:</b> escribe el texto, revisa la vista previa e inserta en la tinta técnica «Braille», en sobreimpresión y en su propia capa.</li>
</ul>

<h1>10. Trap (reventado)</h1>
{fig("p04_trap", "Pestaña Trap.", 45)}
<ol>
<li>Elige tu <b>perfil de máquina</b>; la tolerancia de movimiento se rellena sola (puedes cambiarla).</li>
<li><b>Analizar registro</b>: desplaza las tintas la tolerancia en 8 direcciones y marca en el documento dónde aparecería un filete blanco.</li>
<li><b>Crear traps vectoriales</b> (solo arte plano): añade en la capa «FAVERVIEW – Traps» trazos en sobreimpresión con las mismas tintas.
Con degradados, transparencias o imágenes el panel lo indica y propone las placas con trap en FAVERVIEW.</li>
<li>Vuelve a pulsar <b>Analizar registro</b>: debe decir «✔ 0 filetes con ±X mm».</li>
</ol>
<p>Las reglas y cómo medir la tolerancia real de tu máquina están en el Manual de uso (capítulo «Reventado»). Es una estimación: confirma con tu imprenta.</p>

<h1>11. Ajustes</h1>
{fig("p05_ajustes", "Pestaña Ajustes.", 45)}
<ul>
<li><b>Preajuste de PDF</b> con el que se exporta la mesa para analizarla (por defecto PDF/X-4 si existe).</li>
<li><b>Versión del panel</b> y aviso de versión nueva del plugin con enlace de descarga.</li>
<li><b>Limpiar temporales</b> ahora.</li>
</ul>

<h1>12. Seguridad y privacidad</h1>
<ul>
<li>Todo ocurre en tu equipo: el panel solo habla con FAVERVIEW en <code>127.0.0.1</code>.</li>
<li>FAVERVIEW guarda un <b>token</b> en <code>%APPDATA%\\FAVERVIEW\\plugin.json</code>; el panel lo usa en cada petición. Ninguna página web puede usar
la API de tu equipo aunque FAVERVIEW esté abierto.</li>
<li>Las copias exportadas quedan en <code>%TEMP%\\FAVERVIEW</code> y se borran a las 24 horas.</li>
</ul>

<h1>13. Si algo falla</h1>
<table>
<tr><th>Síntoma</th><th>Qué hacer</th></tr>
<tr><td>No aparece en Ventana → Extensiones</td><td>Instala un <code>.zxp</code> <b>firmado</b> con Illustrator cerrado y reinícialo.</td></tr>
<tr><td>El panel sale en blanco</td><td>Actualiza Illustrator a la última versión de su año. Si persiste, anota la versión exacta de Illustrator y avisa a quien mantiene la app.</td></tr>
<tr><td><span style="color:#dc2626">●</span> con FAVERVIEW abierto</td><td>Cierra y abre FAVERVIEW; comprueba <code>%APPDATA%\\FAVERVIEW\\plugin.json</code>; el cortafuegos debe permitir el tráfico local a 127.0.0.1.</td></tr>
<tr><td><span style="color:#d97706">●</span> Versión incompatible</td><td>Actualiza FAVERVIEW o el plugin (el mensaje dice cuál).</td></tr>
<tr><td>Aviso de editor no verificado al instalar</td><td>El <code>.zxp</code> está firmado con el certificado propio del taller; confirma la instalación si confías en quien te lo dio.</td></tr>
<tr><td>«La mesa de trabajo está vacía»</td><td>Activa una mesa con contenido.</td></tr>
<tr><td>Illustrator se pone lento con documentos enormes</td><td>Normal con miles de objetos: cada operación del panel está limitada para no congelarlo más de unos segundos.</td></tr>
</table>

<h1>14. Estado de validación y pruebas manuales</h1>
<div class="aviso">Todo lo que se puede comprobar sin Illustrator está probado automáticamente (servidor, capa de Illustrator simulada y panel en
un navegador con CEP simulado). Las pruebas que <b>solo</b> se pueden hacer con Illustrator real están en <code>plugin/PRUEBAS_MANUALES.md</code>
(13 pruebas: instalar, conexión, vectorizar, preflight, correcciones, separaciones, comparar, códigos, trap, deshacer, rendimiento y desinstalar).
Hasta que se ejecuten, considera el plugin <b>sin validar en Illustrator</b>.</div>
<p>Para ejecutarlas: abre en Illustrator <b>Archivo → Scripts → Otro script…</b> → <code>plugin/tests/archivos/crear_documento_de_prueba.jsx</code> (crea un documento con
errores conocidos) y sigue la tabla, marcando ✔ o ✘ con observaciones y capturas.</p>
"""


# ============================================================================ NOVEDADES
def novedades(fig, version: str) -> str:
    return f"""
<h1>Contenido</h1>
<ol>
<li>Resumen: de comparador a suite de preprensa</li>
<li>Pestañas nuevas y funciones comunes</li>
<li>Bibliotecas de tintas</li>
<li>Separar colores · PDF</li>
<li>Separar colores · Imagen</li>
<li>Vectorizar</li>
<li>Preflight</li>
<li>Códigos de barras</li>
<li>Herramientas</li>
<li>Automatizar</li>
<li>Auto-trap y tolerancia de registro (3.1)</li>
<li>Plugin de Illustrator (3.2)</li>
<li>Actualizaciones automáticas mejoradas (3.2)</li>
<li>Seguridad (3.2.1)</li>
<li>Manuales nuevos</li>
<li>Qué necesitas instalar para lo nuevo</li>
<li>Historial de versiones</li>
</ol>

<h1>1. Resumen: de comparador a suite de preprensa</h1>
<p>Hasta la versión 2, FAVERVIEW comparaba el arte del cliente con tu diseño. Desde la <b>versión 3</b> es una <b>suite de preprensa</b>: además de
comparar, separa colores, vectoriza, revisa PDF (preflight), genera y verifica códigos de barras, hace reventado (trapping), prepara montajes y
automatiza tareas. Y desde la 3.2 también funciona <b>dentro de Illustrator</b>. Todo sigue corriendo en tu equipo, sin internet y sin costo.</p>
<table>
<tr><th>Versión</th><th>Lo principal</th></tr>
<tr><td><b>3.0</b></td><td>Suite con pestañas: Separar colores, Vectorizar, Preflight, Códigos de barras, Herramientas y Automatizar; bibliotecas de tintas.</td></tr>
<tr><td><b>3.1</b></td><td>Auto-trap con la tolerancia de movimiento de tu máquina y prueba de filetes.</td></tr>
<tr><td><b>3.2</b></td><td>Plugin de Illustrator; aviso de actualización con versión y novedades; botón «Buscar actualizaciones»; manuales nuevos.</td></tr>
<tr><td><b>3.2.1</b></td><td>Revisión completa de seguridad.</td></tr>
</table>
<div class="nota">Lo que ya conocías de Comparar (errores por colores, semáforo, visor, checklist, reporte, aprendizaje del OCR…) sigue igual.
Este manual cubre solo lo nuevo; el detalle completo de cada función está en el <b>Manual de uso</b>.</div>

<h1>2. Pestañas nuevas y funciones comunes</h1>
{fig("s01_suite", "La suite: una pestaña por módulo y el botón Tintas arriba a la derecha.")}
<ul>
<li><b>Pestañas:</b> Comparar · Separar colores · Vectorizar · Preflight · Códigos de barras · Herramientas · Automatizar.</li>
<li><b>Enviar a…:</b> cuando cargas un archivo aparece este selector para pasar el <b>mismo archivo</b> a otra pestaña sin volver a subirlo
(por ejemplo, de Separar a Vectorizar o a Preflight).</li>
<li><b>Cancelar:</b> las tareas largas muestran una barra de progreso por etapas y se pueden cancelar.</li>
<li><b>Arrastrar, soltar y pegar (Ctrl+V)</b> funcionan en todas las pestañas.</li>
<li><b>Avisos por herramienta:</b> si falta Ghostscript o Tesseract, la pestaña afectada lo indica al pasar el ratón; el resto funciona.</li>
</ul>

<h1>3. Bibliotecas de tintas</h1>
{fig("s02_tintas", "Pantalla Tintas: bibliotecas, importación y tintas propias.", 90)}
<p>El botón <b>Tintas</b> (arriba a la derecha) guarda tus colores de impresión para usarlos en todos los módulos:</p>
<ul>
<li>Trae de fábrica <b>CMYK de referencia (ISO/Fogra)</b>, blanco, barniz y tintas técnicas (troquel, braille, cotas).</li>
<li><b>Importa</b> tus bibliotecas en <b>ASE</b> (Illustrator), <b>CxF</b> (medición/proveedor) o <b>CSV</b> (<code>nombre,L,a,b</code>).</li>
<li>Crea tintas propias con su valor Lab.</li>
</ul>
<div class="aviso"><b>Pantone, HKS, RAL, TOYO y DIC</b> son bibliotecas comerciales con licencia: FAVERVIEW no las incluye. Expórtalas desde tu
Illustrator (Pantone Connect) o pide las CxF a tu proveedor de tintas. Se guardan en <code>datos_locales/tintas</code>, que nunca se sube a internet.</div>

<h1>4. Separar colores · PDF</h1>
{fig("s03_separar_pdf", "Separar → PDF: tintas, visor y problemas.")}
<p>Suelta un PDF y verás <b>una placa por tinta</b> (CMYK, Pantones, blanco, barniz, troquel):</p>
<ul>
<li><b>Lista de tintas</b> con su cobertura; botones <b>Solo</b> (ver solo esa tinta) y <b>Neg.</b> (negativo).</li>
<li><b>Densitómetro:</b> pasa el cursor por la página y ves el % de cada tinta en ese punto.</li>
<li><b>Mapa de cobertura (TAC):</b> marca en rojo las zonas que superan el límite de tinta total del perfil (offset, flexo, digital…).</li>
<li><b>Problemas</b> (clic → zoom): negro enriquecido en texto pequeño, texto pequeño en varias tintas, barniz/blanco/tintas técnicas con la
sobreimpresión equivocada, color de registro en el arte, RGB sin convertir, líneas finas y exceso de tinta.</li>
<li><b>Edición sobre una copia</b> (tu PDF nunca se toca): unir tintas duplicadas («PANTONE 485 C» y «Pantone 485C»), renombrar, convertir una
tinta directa a proceso y eliminar las que no se usan.</li>
<li><b>Exportar placas</b> en TIFF (8 o 1 bit) o PDF, más un informe de separaciones.</li>
</ul>
{fig("s04_separar_tac", "Mapa de cobertura total (TAC).", 90)}

<h1>5. Separar colores · Imagen</h1>
{fig("s05_separar_imagen", "Separar → Imagen: asistente de 4 pasos con vista previa.")}
<p>Separa una imagen (logo, ilustración o foto) en las tintas con las que vas a imprimir, ideal para <b>serigrafía, flexo y etiquetas</b>:</p>
<table>
<tr><th>Modo</th><th>Para qué</th></tr>
<tr><td>Tintas planas</td><td>Logos e ilustraciones de colores sólidos. Detecta la paleta sola o usa la de tu biblioteca.</td></tr>
<tr><td>Proceso simulado</td><td>Fotos con pocas tintas, sobre papel o prenda oscura; calcula la <b>base blanca</b> con choke.</td></tr>
<tr><td>Índice</td><td>Serigrafía con puntos cuadrados del mismo tamaño (difusión de error).</td></tr>
<tr><td>CMYK</td><td>Con perfil ICC y límite de tinta total.</td></tr>
</table>
<p>Incluye <b>tramado</b> AM (lineatura y ángulo por tinta) y FM, y salidas en canales TIFF, placas de 1 bit, <b>PDF con canales por tinta (DeviceN)</b>,
simulación sobre el sustrato e informe. Desde la 3.1 también aplica el <b>auto-trap</b> (sección 11).</p>

<h1>6. Vectorizar</h1>
{fig("s06_vectorizar", "Vectorizar: preajustes, controles y visor.")}
<p>Convierte una imagen en vectores <b>pensados para imprimir</b>:</p>
<ul>
<li><b>Cero huecos entre colores:</b> dos formas vecinas comparten exactamente el mismo borde.</li>
<li><b>Colores exactos</b> de tu paleta o de tu biblioteca, y salida en <b>PDF con tintas directas</b>, además de SVG, EPS y DXF (para corte).</li>
<li><b>Geometría limpia:</b> círculos, arcos y elipses perfectos; rectas casi horizontales o verticales enderezadas; simetría.</li>
<li><b>Líneas como trazos</b> con grosor, <b>texto</b> marcado o reemplazado por texto real, y engrosado de detalles demasiado finos para imprimir.</li>
<li><b>Edición básica:</b> unir colores, borrar, recolorear y volver a trazar una zona.</li>
<li>Preajustes: Logo, Línea, Ilustración, Escaneo y Foto posterizada. Vistas de <b>contornos</b> (nodos) y <b>diferencias</b> con el original.</li>
</ul>
{fig("s07_vectorizar_contornos", "Vista de contornos: nodos y trazados.", 90)}
<p>En el banco de pruebas de logos, el vectorizador iguala o supera a VTracer en fidelidad en el 92 % de los casos, con unas 4,5 veces menos nodos y
cero huecos. La comparación con Illustrator y CorelDRAW se hará cuando haya archivos de esos programas para medir.</p>

<h1>7. Preflight</h1>
{fig("s08_preflight", "Preflight: hallazgos por severidad y correcciones.")}
<p>Revisión técnica del PDF antes de imprenta, con <b>5 perfiles</b> editables (offset, flexo, etiquetas digitales, serigrafía y básico, inspirados en
GWG 2015): fuentes incrustadas, resolución de imágenes, espacios de color, tintas duplicadas, cobertura total, líneas y texto pequeños, sobreimpresión,
sangrado y zona segura, transparencias, capas, PDF/X y compresión. Las <b>correcciones seguras</b> se aplican sobre una copia y se comprueban antes/después.
Reporte PDF con miniaturas.</p>

<h1>8. Códigos de barras</h1>
{fig("s09_codigos", "Códigos de barras: generar, verificar y lote.")}
<ul>
<li><b>Generar</b> 12 tipos en vectores: EAN-13/8, UPC-A/E, ITF-14, Code 128, GS1-128, Code 39, GS1 DataBar, DataMatrix, GS1 DataMatrix y QR.
Valida el dígito de control y los datos GS1, y permite magnificación, <b>reducción de barras (BWR)</b>, zonas de silencio y la tinta.</li>
<li><b>Verificar</b> en un PDF o imagen: lee el código, mide la magnificación, avisa de contraste insuficiente (por ejemplo rojo sobre blanco) o de la
dirección en flexo, y estima un grado A–F (orientativo, no certificado).</li>
<li><b>Lote</b> desde un CSV.</li>
</ul>

<h1>9. Herramientas</h1>
<table>
<tr><th>Herramienta</th><th>Qué hace</th></tr>
<tr><td>Trapping</td><td>Reventado por placas, con tabla de anchos por par de tintas y simulación de mal registro con y sin trap.</td></tr>
<tr><td>Step &amp; repeat</td><td>Montaje en hoja o banda con separación, rotación, desfase y marcas: registro, corte, barra de color, microdots y rótulo de cada tinta.</td></tr>
<tr><td>Distorsión flexo</td><td>Compensa el alargamiento del cliché en la dirección de impresión (D % = 2π·k/R·100, o el % del fabricante).</td></tr>
<tr><td>Braille</td><td>Texto a braille español en la tinta técnica «Braille» (medidas Marburg Medium configurables).</td></tr>
<tr><td>Gama extendida</td><td>Recetas para reproducir tintas directas con un juego fijo (por ejemplo CMYK+OGV), con semáforo de ΔE.</td></tr>
<tr><td>Prueba en pantalla</td><td>Simula el trabajo con tus tintas, el sustrato y la ganancia de punto (orientativa, no contractual).</td></tr>
<tr><td>Calibración</td><td>Gráfico de prueba para imprimir y medir, que afina el modelo de mezcla de tintas.</td></tr>
</table>
{fig("s11_step_repeat", "Step &amp; repeat con marcas.", 90)}

<h1>10. Automatizar</h1>
{fig("s13_automatizar", "Recetas: pasos en orden y ejecución.", 90)}
<p>Una <b>receta</b> encadena pasos (preflight, correcciones, unir tintas, exportar placas, step &amp; repeat, distorsión, trapping, verificar códigos,
vectorizar, separar imagen, resumen) y se ejecuta sobre un archivo, una carpeta o una <b>carpeta vigilada</b>: cada archivo nuevo se procesa solo y
termina en <code>salida/</code>, <code>errores/</code> o <code>reportes/</code>. Hay condiciones («si el preflight tiene errores, detener») y 3 recetas de ejemplo.</p>

<h1>11. Auto-trap y tolerancia de registro (3.1)</h1>
{fig("s12_trapping", "Trapping: mapa de traps y prueba de movimiento.", 90)}
<p>En la máquina las tintas nunca caen exactamente en el mismo sitio. Si dos colores solo se tocan, al moverse aparece un <b>filete blanco</b>. El
<b>auto-trap</b> mete un poco un color bajo el vecino para que, dentro de la <b>tolerancia de movimiento de tu máquina</b>, el borde siga cubierto.</p>
<ul>
<li><b>Perfiles de máquina</b> con tu tolerancia en mm (ejemplos orientativos: serigrafía automática ±0,20 mm, flexo angosta ±0,15 mm, offset
±0,08 mm). Puedes crear los tuyos.</li>
<li><b>Automático en Separar colores</b> (imagen y PDF) para serigrafía y flexo, en el <b>Vectorizador</b> (trazos en sobreimpresión) y en Herramientas.</li>
<li><b>Reglas corregidas:</b> ahora también se protegen dos colores de luminosidad parecida (trap centrado); el negro no se mueve, el blanco se contrae,
el negro enriquecido se retrae y las líneas finas se respetan.</li>
<li><b>Prueba de movimiento:</b> desplaza las placas en 8 direcciones y cuenta los filetes. Con el trap debe decir <b>«✔ Sin filetes con ±X mm»</b>.</li>
<li>Preflight («Bordes sin protección de registro») y recetas (<code>auto_trap</code>, <code>prueba_movimiento</code>).</li>
</ul>
<div class="nota">Mide el movimiento real de tu máquina con una prueba de registro y usa ese valor; confirma siempre con tu imprenta.</div>

<h1>12. Plugin de Illustrator (3.2)</h1>
{fig("p01_vectorizar", "El panel FAVERVIEW dentro de Illustrator.", 42)}
<p>Un panel para <b>Illustrator 2024, 2025 y 2026</b> que usa las herramientas de FAVERVIEW sin salir del programa (FAVERVIEW debe estar abierto):</p>
<table>
<tr><th>Pestaña</th><th>Qué hace</th></tr>
<tr><td>Vectorizar</td><td>Vectoriza la imagen seleccionada y coloca el vector exactamente encima, con muestras spot sin duplicar.</td></tr>
<tr><td>Preflight</td><td>Revisa la mesa; clic → zoom y selección; marcadores; correcciones directas en tu documento (sobreimpresión, K 100 %, unir y borrar muestras).</td></tr>
<tr><td>Separar</td><td>Tintas frente a las muestras del documento, cobertura, placas y densitómetro.</td></tr>
<tr><td>Comparar</td><td>Compara la mesa con el arte del cliente y marca las diferencias sobre tu diseño.</td></tr>
<tr><td>Códigos</td><td>Inserta códigos de barras y braille como vectores y verifica los del documento.</td></tr>
<tr><td>Trap</td><td>Analiza el registro y crea traps vectoriales en su propia capa.</td></tr>
</table>
<p>Se instala con un archivo <code>.zxp</code> firmado y el instalador oficial de Creative Cloud (ver el <b>Manual del plugin de Illustrator</b>).</p>
<div class="aviso">El plugin está probado automáticamente, pero sus <b>pruebas en Illustrator real</b> (<code>plugin/PRUEBAS_MANUALES.md</code>) están pendientes.
Hasta completarlas, úsalo con precaución.</div>

<h1>13. Actualizaciones automáticas mejoradas (3.2)</h1>
<ul>
<li>El aviso azul muestra el <b>número de la versión nueva</b> y un desplegable <b>Novedades</b> con lo que trae.</li>
<li>El aviso <b>ya no desaparece</b> si cierras y abres la app el mismo día.</li>
<li>Nuevo botón <b>Buscar actualizaciones</b> en el pie de la página: comprueba en el momento.</li>
<li><b>Actualizar</b> explica qué hacer si la carpeta tiene cambios locales o está en otra rama, en vez de fallar.</li>
<li>El plugin avisa en su pestaña <b>Ajustes</b> cuando hay un <code>.zxp</code> nuevo.</li>
</ul>
<p>Para actualizar a mano: <code>cd $HOME\\FAVERVIEW; git pull</code> y vuelve a abrir la app. Tus datos no se tocan.</p>

<h1>14. Seguridad (3.2.1)</h1>
<p>Como el código es público, se revisó a fondo que nada permita conectarse a tu equipo ni entrar a tu cuenta:</p>
<ul>
<li>La app solo acepta conexiones <b>de tu propio computador</b> (127.0.0.1); ningún otro dispositivo puede usarla.</li>
<li>Ninguna página web puede usar la app ni pulsar «Actualizar»; el plugin usa un <b>token</b> que solo existe en tu equipo.</li>
<li>Se corrigieron dos puntos donde el nombre de una tinta de una biblioteca ajena podía insertar código en la página.</li>
<li>Hay pruebas automáticas que vigilan estas protecciones en cada cambio, y el repositorio tiene activadas las alertas de seguridad de GitHub.</li>
<li>¿Encuentras un problema de seguridad? Repórtalo en privado: GitHub → <b>Security → Report a vulnerability</b> (ver <code>SECURITY.md</code>).</li>
</ul>

<h1>15. Manuales nuevos</h1>
<table>
<tr><th>Documento</th><th>Para qué</th></tr>
<tr><td>Guía de instalación y actualización</td><td>Instalar la app, Ghostscript y el plugin; actualizar; desinstalar.</td></tr>
<tr><td>Manual de uso</td><td>Todas las funciones, módulo por módulo.</td></tr>
<tr><td>Guía rápida</td><td>Los pasos esenciales de cada tarea.</td></tr>
<tr><td>Manual del plugin de Illustrator</td><td>Instalar y usar el panel.</td></tr>
<tr><td>Guía del mantenedor</td><td>Publicar versiones, firmar el plugin y probar.</td></tr>
<tr><td>Novedades (este documento)</td><td>Qué cambió desde la versión 2.</td></tr>
</table>
<p>Todos están en la carpeta <code>docs</code> de FAVERVIEW y en GitHub.</p>

<h1>16. Qué necesitas instalar para lo nuevo</h1>
<table>
<tr><th>Para usar…</th><th>Necesitas</th></tr>
<tr><td>Separar colores, Códigos de barras, trapping y EPS</td><td><b>Ghostscript</b> (paso 2b de la Guía de instalación).</td></tr>
<tr><td>Pantone y otras bibliotecas</td><td>Tus propios archivos ASE, CxF o CSV.</td></tr>
<tr><td>El plugin de Illustrator</td><td>Illustrator 2024–2026 y el <code>.zxp</code> firmado.</td></tr>
<tr><td>Todo lo demás</td><td>Nada: llega con <b>Actualizar</b> (o <code>git pull</code>).</td></tr>
</table>

<h1>17. Historial de versiones</h1>
<table>
<tr><th>Versión</th><th>Fecha</th><th>Cambios</th></tr>
<tr><td>3.2.1</td><td>27-09-2026</td><td>Revisión de seguridad y política de seguridad.</td></tr>
<tr><td>3.2.0</td><td>26-09-2026</td><td>Plugin de Illustrator, actualizaciones mejoradas y manuales nuevos.</td></tr>
<tr><td>3.1.0</td><td>26-09-2026</td><td>Auto-trap con tolerancia de registro.</td></tr>
<tr><td>3.0.0</td><td>26-09-2026</td><td>Suite de preprensa: Separar, Vectorizar, Preflight, Códigos, Herramientas, Automatizar y Tintas.</td></tr>
<tr><td>2.0.0</td><td>25-09-2026</td><td>Comparador con OCR que aprende, revisión, plantillas, versiones y lotes.</td></tr>
</table>
<p>El detalle técnico completo está en <code>CHANGELOG.md</code>. Este documento corresponde a la versión {version}.</p>
"""


# ============================================================================ GUÍA RÁPIDA
def guia_rapida(version: str) -> str:
    return f"""
<h1>FAVERVIEW en una página por tarea</h1>
<p>Abre FAVERVIEW con su acceso directo. Todas las pestañas aceptan <b>arrastrar y soltar</b>, <b>pegar con Ctrl+V</b> y el botón <b>Enviar a…</b> para pasar
el mismo archivo a otra pestaña. Rueda = zoom, arrastrar = mover. Las tareas largas muestran progreso y se pueden <b>Cancelar</b>.</p>

<h2>Comparar el arte del cliente con mi diseño</h2>
<ol><li>A = arte del cliente (imagen o PDF) · B = tu PDF.</li><li><b>Comparar</b>.</li>
<li>Semáforo: ≥ 98 % Aprobado · 90–98 % Revisar · &lt; 90 % Con errores. Colores: rojo texto · amarillo ortografía · naranja color · azul elemento · morado fuente.</li>
<li>Clic en un error → zoom. Marca cada error Pendiente / Corregido / No aplica. <b>Descargar reporte PDF</b>.</li></ol>

<h2>Separar colores de un PDF</h2>
<ol><li>Pestaña <b>Separar colores → PDF</b>, suelta el PDF.</li><li>Lista de tintas (Solo / Negativo), cobertura y <b>Mapa de cobertura</b> (TAC).</li>
<li>Pasa el cursor: densitómetro. Revisa <b>Problemas</b>.</li><li>Opcional: <b>Auto-trap</b> con tu perfil de máquina. <b>Exportar placas…</b></li></ol>

<h2>Separar una imagen en tintas</h2>
<ol><li><b>Separar colores → Imagen</b>: imagen y sustrato (papel, prenda…).</li><li>Modo: tintas planas, proceso simulado, índice o CMYK.</li>
<li>Ajustes con vista previa (auto-trap activado en serigrafía y flexo; revisa «✔ Sin filetes»).</li><li>Salida: canales, placas tramadas, PDF DeviceN.</li></ol>

<h2>Vectorizar</h2>
<ol><li>Pestaña <b>Vectorizar</b>, suelta la imagen, elige preajuste (Logo, Línea, Ilustración, Escaneo, Foto).</li>
<li>Ajusta colores, detalle mínimo y tamaño final en mm. Opcional: tintas de tu biblioteca y <b>Añadir trap</b>.</li>
<li>Revisa Contornos y Diferencias. Descarga PDF (con tintas directas), SVG, EPS o DXF.</li></ol>

<h2>Preflight</h2>
<ol><li>Pestaña <b>Preflight</b>, suelta el PDF, elige el perfil.</li><li>Clic en un hallazgo → zoom.</li><li>Aplica las correcciones seguras (sobre una copia) y descarga el reporte.</li></ol>

<h2>Códigos de barras y braille</h2>
<ol><li>Pestaña <b>Códigos de barras</b>: tipo, datos (se validan en vivo), magnificación, BWR y tinta → PDF/SVG/EPS vectorial.</li>
<li><b>Verificar</b>: suelta un PDF o imagen para decodificar y estimar el grado. Lote desde CSV.</li><li>Braille: en <b>Herramientas</b>.</li></ol>

<h2>Herramientas</h2>
<p>Trapping · Step &amp; repeat con marcas · Distorsión flexo · Braille · Gama extendida · Prueba en pantalla · Calibración.</p>

<h2>Automatizar</h2>
<ol><li>Crea una receta (pasos en orden) o usa una de ejemplo.</li><li>Ejecútala sobre un archivo, una carpeta o una <b>carpeta vigilada</b>
(entrada → salida / errores / reportes).</li></ol>

<h2>En Illustrator</h2>
<p>Ventana → Extensiones → FAVERVIEW (con FAVERVIEW abierto): Vectorizar, Preflight, Separar, Comparar, Códigos, Trap y Ajustes. Ver el Manual del plugin.</p>

<h2>Actualizar</h2>
<p>Aviso azul arriba → <b>Actualizar</b> → cierra la ventana negra y vuelve a abrir. O en el pie: <b>Buscar actualizaciones</b>. Versión actual: pie de la página (esta guía: {version}).</p>
"""


# ============================================================================ GUÍA DEL MANTENEDOR
def guia_mantenedor(version: str) -> str:
    return f"""
<h1>Contenido</h1>
<ol>
<li>Para quién es esta guía</li>
<li>Cómo está organizado el repositorio</li>
<li>Reglas del proyecto</li>
<li>Flujo de trabajo: rama, pruebas y Pull Request</li>
<li>Publicar una versión nueva (y cómo llega a los usuarios)</li>
<li>Firmar y publicar el plugin de Illustrator</li>
<li>Pruebas y bancos de pruebas</li>
<li>Regenerar los manuales y las capturas</li>
<li>Privacidad: lo que nunca se sube</li>
<li>Migración del plugin a UXP</li>
</ol>

<h1>1. Para quién es esta guía</h1>
<p>Para quien mantiene FAVERVIEW: corrige errores, agrega funciones, publica versiones y firma el plugin. Los usuarios no la necesitan.
Versión documentada: {version}. Repositorio: {REPO}</p>

<h1>2. Cómo está organizado el repositorio</h1>
<table>
<tr><th>Carpeta / archivo</th><th>Contenido</th></tr>
<tr><td><code>app/</code></td><td>Servidor FastAPI: <code>core/</code> (común), <code>modules/</code> (comparar, separar, vectorizar, preflight, códigos, herramientas, automatizar, plugin), <code>learning/</code> (OCR que aprende).</td></tr>
<tr><td><code>web/</code></td><td>Interfaz (HTML/JS sin compilación): <code>core/</code> y un archivo por módulo.</td></tr>
<tr><td><code>plugin/</code></td><td>Panel CEP para Illustrator (<code>cep/</code>), pruebas, herramientas de empaquetado, pruebas manuales y migración a UXP.</td></tr>
<tr><td><code>bench/</code></td><td>Bancos de pruebas: comparar, separación, vectorizador y trapping.</td></tr>
<tr><td><code>tests/</code></td><td>Pruebas automáticas (pytest) y casos sintéticos.</td></tr>
<tr><td><code>tools/manual/</code></td><td>Generador de los manuales PDF (incluido el de Novedades) y capturas.</td></tr>
<tr><td><code>docs/</code></td><td>Manuales PDF generados.</td></tr>
<tr><td><code>PLAN*.md</code>, <code>DECISIONES.md</code>, <code>CHANGELOG.md</code></td><td>Planes por etapas, decisiones técnicas y registro de cambios.</td></tr>
</table>

<h1>3. Reglas del proyecto</h1>
<ul>
<li>Todo local, gratis y sin IA en la nube. Licencia AGPL-3.0; solo dependencias compatibles.</li>
<li>Interfaz, mensajes y documentación en español.</li>
<li>Sin <code>.exe</code>, <code>.bat</code> ni <code>.ps1</code> propios: distribución con GitHub + winget + uv.</li>
<li>Nunca afirmar «certificado» ni «mejor que X» sin medirlo. Las estimaciones se rotulan como tales.</li>
<li>Sin bibliotecas Pantone ni otras con licencia.</li>
</ul>

<h1>4. Flujo de trabajo: rama, pruebas y Pull Request</h1>
<ol>
<li>Trabaja en una rama: <code>git switch -c mejora/nombre</code>. Los usuarios se actualizan desde <code>main</code>: <b>nunca</b> subas a <code>main</code> algo sin probar.</li>
<li>Antes de subir, ejecuta todo:
<pre>uv run pytest -q
uv run python -m bench.run --sinteticos --ci --workers 4
uv run python -m bench.separation.run --ci
uv run python -m bench.vector.run --casos 12 --ci
uv run python -m bench.trapping.run --ci
uv run python plugin/tools/build_zxp.py --sin-firma</pre></li>
<li>Sube la rama y abre el Pull Request: <code>git push -u origin mejora/nombre</code> y <code>gh pr create</code> (o desde la web de GitHub).</li>
<li>GitHub Actions ejecuta lo mismo en Windows. Solo fusiona el PR con la <b>marca verde</b>.</li>
<li>Al fusionar a <code>main</code>, todos los equipos verán el aviso de actualización (como máximo en 24 horas, o al pulsar «Buscar actualizaciones»).</li>
</ol>

<h1>5. Publicar una versión nueva</h1>
<ol>
<li>Sube el número en <code>pyproject.toml</code> (<code>version = "x.y.z"</code>): x = cambio grande o incompatible, y = función nueva, z = arreglo.
El plugin toma la misma versión al empaquetarse.</li>
<li>Escribe las novedades en <code>CHANGELOG.md</code> en una sección nueva <b>arriba del todo</b> (<code>## x.y.z — fecha</code>) con viñetas cortas:
<b>las primeras viñetas son las que ve el usuario</b> en el desplegable «Novedades» del aviso de actualización.</li>
<li>Regenera los manuales (sección 8) y ejecuta las pruebas (sección 7).</li>
<li>Pull Request → marca verde → fusionar.</li>
<li>Etiqueta la versión: <code>git switch main; git pull; git tag vx.y.z; git push --tags</code>.</li>
<li>Crea el <b>Release</b> en GitHub desde la etiqueta (<code>gh release create vx.y.z --notes-file</code> o desde la web) y adjunta el plugin firmado (sección 6).</li>
</ol>
<h3>Cómo detecta la app la versión nueva</h3>
<p><code>app/updates.py</code> hace <code>git fetch origin main</code> una vez al día (o al pulsar «Buscar actualizaciones»), cuenta los commits nuevos, lee la versión de
<code>pyproject.toml</code> y la primera sección de <code>CHANGELOG.md</code> en <code>origin/main</code>. «Actualizar» ejecuta <code>git pull --ff-only</code> solo si la carpeta está en
<code>main</code> y sin cambios locales. El plugin busca en los Releases un archivo llamado exactamente <code>FAVERVIEW-Illustrator-&lt;versión&gt;.zxp</code>.</p>

<h1>6. Firmar y publicar el plugin de Illustrator</h1>
<ol>
<li>Descarga <b>ZXPSignCmd</b> (herramienta oficial de Adobe, repositorio <code>Adobe-CEP/CEP-Resources</code>). No se incluye en el repositorio.</li>
<li>Crea <b>una sola vez</b> el certificado propio y guárdalo <b>fuera del repositorio</b> (<code>*.p12</code> está en <code>.gitignore</code>):
<pre>$env:ZXP_CERT_PASS = "una-clave-larga"
$zxp = "C:\\herramientas\\ZXPSignCmd.exe"
$cert = "C:\\seguro\\cert.p12"
uv run python plugin/tools/build_zxp.py --crear-certificado $cert --zxpsigncmd $zxp `
  --pais CO --provincia Antioquia --organizacion "Mi taller" --nombre "FAVERVIEW"</pre></li>
<li>Empaqueta, firma con sello de tiempo y verifica:
<pre>$env:ZXP_CERT_PASS = "una-clave-larga"
$zxp = "C:\\herramientas\\ZXPSignCmd.exe"
$cert = "C:\\seguro\\cert.p12"
uv run python plugin/tools/build_zxp.py --cert $cert --zxpsigncmd $zxp</pre>
Sale <code>build/zxp/FAVERVIEW-Illustrator-&lt;versión&gt;.zxp</code>.</li>
<li>Adjúntalo al Release de la versión. Con el mismo nombre de archivo, el panel de los usuarios lo detecta como actualización.</li>
<li>Guarda una copia de seguridad del certificado y su clave: si los pierdes, las versiones siguientes se firmarán con otro certificado.</li>
</ol>
<div class="aviso">El <code>.zxp</code> sin firma (<code>--sin-firma</code>, el que genera la CI) <b>no</b> sirve para instalar con el instalador de Creative Cloud.
Para desarrollo usa <code>uv run python plugin/tools/dev_install.py</code> (activa PlayerDebugMode, pide confirmación).</div>

<h1>7. Pruebas y bancos de pruebas</h1>
<table>
<tr><th>Qué</th><th>Comando</th><th>Mide</th></tr>
<tr><td>Pruebas automáticas</td><td><code>uv run pytest -q</code></td><td>Todo el servidor, la capa de Illustrator simulada y el panel.</td></tr>
<tr><td>Banco Comparar</td><td><code>uv run python -m bench.run --sinteticos --ci</code></td><td>Precisión, recall, falsos positivos, CER, tiempo.</td></tr>
<tr><td>Banco Separación</td><td><code>uv run python -m bench.separation.run --ci</code></td><td>Paleta, regiones, ΔE de simulación.</td></tr>
<tr><td>Banco Vectorizador</td><td><code>uv run python -m bench.vector.run --ci</code></td><td>Fidelidad, nodos, huecos contra VTracer/Potrace (e Illustrator/Corel si hay archivos).</td></tr>
<tr><td>Banco Trapping</td><td><code>uv run python -m bench.trapping.run --ci</code></td><td>Filetes tras la prueba de movimiento (deben ser 0).</td></tr>
<tr><td>Plugin en Illustrator</td><td><code>plugin/PRUEBAS_MANUALES.md</code></td><td>13 pruebas manuales en Illustrator real.</td></tr>
</table>
<p>Los umbrales de la CI están en <code>bench/umbral_ci.json</code> y <code>bench/*/umbral_ci.json</code>. Los reportes quedan en <code>datos_locales/bench_resultados/</code>.</p>

<h1>8. Regenerar los manuales y las capturas</h1>
<pre>uv run python tools/manual/build.py</pre>
<p>Genera todos los PDF de <code>docs/</code> con la versión de <code>pyproject.toml</code>. El contenido está en <code>tools/manual/build.py</code> (Manual de uso, parte I),
<code>capitulos_suite.py</code> (parte II) y <code>documentos.py</code> (instalación, plugin, guía rápida y esta guía). Para rehacer las capturas (con FAVERVIEW abierto y Edge instalado):</p>
<pre>uv run python tools/manual/capturas.py http://127.0.0.1:8000
uv run python tools/manual/capturas_plugin.py</pre>

<h1>9. Privacidad: lo que nunca se sube</h1>
<ul>
<li><code>data/</code>, <code>datos_locales/</code> (casos reales, aprendizaje, tintas, perfiles, plantillas, reportes), <code>.venv/</code>, <code>build/</code>, certificados <code>*.p12</code>.</li>
<li>Archivos reales de clientes: nunca en <code>samples/</code> ni en <code>tests/</code> (esas carpetas son públicas). Los casos públicos se generan sintéticamente.</li>
<li>Antes de cada push: <code>git status</code> y revisar que no aparezca nada de lo anterior.</li>
<li>Los commits usan el correo anónimo de GitHub configurado en este repositorio.</li>
</ul>

<h1>10. Migración del plugin a UXP</h1>
<p>Adobe publicará UXP para Illustrator (beta en primavera de 2027) y desactivará CEP en diciembre de 2028. El panel ya está preparado (sin Node, todo el acceso a
Illustrator detrás de un adaptador). El mapa de migración está en <code>plugin/MIGRACION_UXP.md</code>: cuando salga la beta, crear <code>PLAN_PLUGIN_UXP.md</code>
y migrar antes de diciembre de 2028.</p>
"""
