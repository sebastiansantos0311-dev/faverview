import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
IMG = HERE / "img"
OUT = HERE.parents[1] / "docs"
OUT.mkdir(exist_ok=True)

CSS = """
body { font-family: sans-serif; font-size: 10.5pt; color: #1f2937; }
h1 { font-size: 22pt; color: #1d4ed8; margin-top: 18pt; margin-bottom: 6pt; }
h2 { font-size: 14pt; color: #1d4ed8; margin-top: 14pt; margin-bottom: 4pt; }
h3 { font-size: 11.5pt; color: #111827; margin-top: 10pt; margin-bottom: 2pt; }
p { margin-top: 3pt; margin-bottom: 3pt; }
li { margin-top: 2pt; margin-bottom: 2pt; }
code { font-family: monospace; background-color: #e5e7eb; }
pre { font-family: monospace; font-size: 9.5pt; border: 1px solid #6b7280; padding: 6pt; }
.nota { border: 1px solid #60a5fa; padding: 6pt; margin-top: 6pt; margin-bottom: 6pt; }
.aviso { border: 1px solid #f59e0b; padding: 6pt; margin-top: 6pt; margin-bottom: 6pt; }
.cap { font-size: 9pt; color: #6b7280; text-align: center; margin-bottom: 8pt; }
table { border-collapse: collapse; width: 100%; margin-top: 4pt; margin-bottom: 6pt; }
th { background-color: #dbeafe; text-align: left; padding: 3pt; border: 1px solid #9ca3af; }
td { padding: 3pt; border: 1px solid #d1d5db; }
"""


def build(html: str, path: Path, title: str, cover: tuple[str, str]):
    story = pymupdf.Story(html=f"<body>{html}</body>", user_css=CSS, archive=pymupdf.Archive(str(IMG)))
    W, H = pymupdf.paper_size("a4")
    where = pymupdf.Rect(50, 60, W - 50, H - 60)
    raw = path.with_name(path.stem + "_raw.pdf")
    writer = pymupdf.DocumentWriter(str(raw))
    more = 1
    while more:
        dev = writer.begin_page(pymupdf.Rect(0, 0, W, H))
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    # portada + pie de página
    doc = pymupdf.open(raw)
    cov = doc.new_page(0, width=W, height=H)
    cov.draw_rect(pymupdf.Rect(0, 0, W, 260), color=None, fill=(0.114, 0.306, 0.847))
    cov.insert_text((50, 130), cover[0], fontsize=34, fontname="hebo", color=(1, 1, 1))
    cov.insert_text((50, 170), cover[1], fontsize=16, fontname="helv", color=(0.86, 0.92, 1))
    cov.insert_text((50, 330), "FAVERVIEW versión 3.0", fontsize=13, fontname="hebo")
    cov.insert_textbox(pymupdf.Rect(50, 350, W - 50, 460),
                       "Suite de preprensa: compara el arte con tu diseño, separa colores, vectoriza, revisa (preflight), genera códigos "
                       "de barras y automatiza tareas. Todo corre en tu equipo, sin internet y sin costo.",
                       fontsize=12, fontname="helv", color=(0.2, 0.2, 0.25))
    for i in range(1, doc.page_count):
        pg = doc[i]
        pg.insert_text((50, H - 30), f"FAVERVIEW · {title}", fontsize=8, color=(0.45, 0.45, 0.5))
        pg.insert_text((W - 70, H - 30), f"Página {i}", fontsize=8, color=(0.45, 0.45, 0.5))
    doc.set_metadata({"title": title, "author": "FAVERVIEW"})
    doc.save(str(path), garbage=3, deflate=True)
    n = doc.page_count
    doc.close()
    try:
        raw.unlink(missing_ok=True)
    except OSError:
        pass
    print(path.name, n, "paginas")


def fig(name, caption, w=100):
    return f'<p><img src="{name}.png" width="{w}%"></p><p class="cap">{caption}</p>'


# =============================================================================== MANUAL
manual = f"""
<h1>Contenido</h1>
<ol>
<li>Qué hace FAVERVIEW y cómo pensar en «A» y «B»</li>
<li>Abrir la aplicación</li>
<li>La pantalla de inicio</li>
<li>Leer el resultado</li>
<li>Las cuatro vistas del visor</li>
<li>La lista de errores</li>
<li>Sensibilidad y recalcular</li>
<li>Alinear manualmente</li>
<li>Zonas a ignorar y plantillas por cliente</li>
<li>Checklist de aprobación</li>
<li>El reporte PDF</li>
<li>Comparar versiones de mi diseño</li>
<li>Verificar correcciones</li>
<li>Comparar todas las páginas</li>
<li>Modo revisión y casos de prueba</li>
<li>Aprendizaje del OCR</li>
<li>Banco de pruebas (uso avanzado)</li>
<li>Historial, actualizaciones y datos guardados</li>
<li>Problemas frecuentes</li>
<li>Glosario y atajos</li>
<li><b>Parte II · La suite:</b> organización y funciones comunes</li>
<li>Bibliotecas de tintas (Pantone y otras)</li>
<li>Separar colores · PDF</li>
<li>Separar colores · Imagen</li>
<li>Vectorizar</li>
<li>Preflight</li>
<li>Códigos de barras</li>
<li>Herramientas</li>
<li>Automatizar</li>
<li>Instalar Ghostscript</li>
<li>Reventado (trapping) y tolerancia de registro</li>
<li>FAVERVIEW en Illustrator</li>
<li>Glosario de preprensa</li>
<li>Qué es exacto y qué es una estimación</li>
</ol>

<h1>1. Qué hace FAVERVIEW</h1>
<p>FAVERVIEW compara dos archivos y te dice, con recuadros de colores y porcentajes, qué es distinto:</p>
<ul>
<li><b>A · Arte del cliente:</b> lo que el cliente quiere (JPG, PNG, WEBP, BMP, TIFF o PDF). Es la <b>referencia</b> de lo que debería decir.</li>
<li><b>B · Mi diseño:</b> tu diseño exportado en PDF. Es lo que hay que <b>corregir</b>.</li>
</ul>
<p>Siempre verás mensajes del tipo «Cliente dice: X · Tu diseño dice: Y». Todo se procesa en tu computador; no se sube nada a internet.</p>
<h3>Los cinco tipos de error</h3>
<table>
<tr><th>Color del recuadro</th><th>Categoría</th><th>Qué significa</th></tr>
<tr><td>Rojo</td><td>Texto</td><td>Palabra cambiada, faltante en tu diseño o sobrante (por ejemplo un precio, una fecha o un teléfono distinto).</td></tr>
<tr><td>Amarillo</td><td>Ortografía</td><td>Posible falta de ortografía en tu diseño, incluida una tilde que falta.</td></tr>
<tr><td>Naranja</td><td>Color</td><td>Un color de texto o de una zona es distinto (medido con Delta E; por defecto se marca por encima de 10).</td></tr>
<tr><td>Azul</td><td>Elemento visual</td><td>Un logo, imagen o forma que falta, sobra, cambió o se movió.</td></tr>
<tr><td>Morado</td><td>Fuente</td><td>Posible diferencia de tamaño, negrita o cursiva. Es una estimación: nunca afirma cuál es la fuente exacta del cliente.</td></tr>
</table>
<h3>El semáforo</h3>
<table>
<tr><th>Similitud total</th><th>Estado</th></tr>
<tr><td>98 % o más</td><td>Aprobado (verde)</td></tr>
<tr><td>90 % a 98 %</td><td>Revisar (amarillo)</td></tr>
<tr><td>Menos de 90 %</td><td>Con errores (rojo)</td></tr>
</table>
<p>La similitud total es un promedio ponderado: visual 30 %, texto 35 %, color 15 %, ortografía 10 %, fuente 10 %.</p>

<h1>2. Abrir la aplicación</h1>
<ol>
<li>Haz doble clic en el acceso directo <b>FAVERVIEW</b> del Escritorio (o ejecuta <code>uv run faverview</code> dentro de la carpeta).</li>
<li>Se abre una ventana negra (el servidor) y, unos segundos después, el navegador con la aplicación.</li>
<li><b>No cierres la ventana negra</b> mientras trabajas. Para salir, ciérrala.</li>
</ol>
<p class="nota">Si el puerto 8000 está ocupado, la app usa automáticamente el siguiente libre (8001, 8002…). La dirección aparece en la ventana negra.</p>

<h1>3. La pantalla de inicio</h1>
{fig("01_inicio", "Pantalla de inicio: dos zonas para soltar archivos y el botón Comparar.")}
<h3>Cargar los archivos</h3>
<ul>
<li>Arrastra el <b>arte del cliente</b> a la zona A y tu <b>diseño</b> a la zona B, o haz clic en cada zona para elegirlos.</li>
<li><b>Pegar con Ctrl+V:</b> si copiaste una imagen (captura de pantalla, WhatsApp Web, correo), pégala en la página. Si ya hay un arte cargado, te pregunta si es para A o para B.</li>
<li><b>Arrastrar desde el navegador:</b> también puedes arrastrar una imagen desde WhatsApp Web o un correo. Si el sitio no lo permite, guarda la imagen y arrástrala desde el Explorador.</li>
<li>Tamaño máximo por archivo: 50 MB. Si el formato no sirve o el PDF está dañado o con contraseña, verás un mensaje en español.</li>
</ul>
<h3>Varias páginas</h3>
<p>Si un PDF (o TIFF) tiene varias páginas aparece el selector <b>Página</b> para elegir cuál comparar. Con varias páginas también aparece el botón <b>Comparar todas las páginas</b> (sección 14).</p>
<h3>Plantilla de zonas</h3>
<p>El selector <b>Plantilla de zonas</b> aplica zonas a ignorar guardadas para ese cliente. Si el nombre del archivo o el tamaño coinciden con una plantilla, la app la sugiere sola (sección 9).</p>
<h3>Qué quieres comparar</h3>
{fig("02_versiones", "Con «Versiones de mi diseño» las zonas pasan a llamarse versión 1 y versión 2.")}
<p>El selector superior cambia entre <b>Arte del cliente vs. mi diseño</b> (uso normal) y <b>Versiones de mi diseño (v1 vs. v2)</b> (sección 12).</p>
<h3>Comparar</h3>
<p>Pulsa <b>Comparar</b>. Aparece una barra de progreso por etapas: cargar, alinear, comparar visualmente, leer el texto (OCR), ortografía, colores y fuentes. Una página tarda normalmente entre 8 y 15 segundos.</p>

<h1>4. Leer el resultado</h1>
{fig("03_resultado", "Resultado: resumen arriba, visor a la izquierda y lista de errores a la derecha.")}
<h3>El resumen</h3>
<ul>
<li><b>Porcentaje grande y semáforo:</b> similitud total y estado. Al lado, el % de diferencia.</li>
<li><b>Cinco cajas:</b> % visual, texto, color, ortografía y fuente, cada una con el color de su categoría.</li>
<li><b>A la derecha:</b> nombres de los archivos, espacio de color de cada uno (sRGB o CMYK), calidad de la alineación (buena, regular, mala o manual), número de errores, tiempo y el estado del checklist («N pendientes» o «Listo para enviar»).</li>
</ul>
<h3>Avisos</h3>
<p>Debajo del resumen pueden aparecer avisos amarillos, por ejemplo: proporciones distintas entre los archivos, el diseño sin texto vectorial (se usa OCR y la precisión baja), o un arte CMYK sin perfil de color (los colores pueden variar).</p>
<div class="aviso"><b>Ojo:</b> si la alineación sale «regular» o «mala», los recuadros pueden ser menos confiables. Prueba «Alinear manualmente» (sección 8).</div>

<h1>5. Las cuatro vistas del visor</h1>
<p>Sobre el visor hay cuatro pestañas. En todas: <b>rueda del ratón = zoom</b>, <b>arrastrar = mover</b> y el botón <b>Ajustar</b> vuelve a encajar la página completa.</p>
<table>
<tr><th>Vista</th><th>Para qué sirve</th></tr>
<tr><td>Lado a lado</td><td>Arte del cliente a la izquierda y tu diseño a la derecha, con zoom y movimiento sincronizados y los mismos recuadros en ambos.</td></tr>
<tr><td>Deslizador</td><td>Una sola imagen: arrastra la barra blanca para ver tu diseño a un lado y el cliente al otro. Ideal para ver cambios pequeños de posición.</td></tr>
<tr><td>Diferencia</td><td>Mapa de calor: lo más claro es igual y los colores cálidos son las zonas distintas.</td></tr>
<tr><td>Superpuesto</td><td>Mezcla al 50 % de ambas imágenes; los fantasmas delatan lo que no coincide.</td></tr>
</table>
{fig("05_deslizador", "Vista Deslizador.", 90)}
{fig("06_diferencia", "Vista Diferencia (mapa de calor).", 90)}
{fig("07_superpuesto", "Vista Superpuesto.", 90)}

<h1>6. La lista de errores</h1>
<p>La lista de la derecha agrupa los errores por categoría y numera cada uno con el mismo número que lleva su recuadro en el visor.</p>
{fig("04_zoom_error", "Al hacer clic en un error el visor se acerca a la zona y el recuadro parpadea.", 90)}
<ul>
<li><b>Clic en un error:</b> hace zoom en esa zona en ambos lados y parpadea el recuadro. También puedes hacer clic directamente en un recuadro del visor.</li>
<li><b>Filtros:</b> las casillas de arriba muestran u ocultan cada categoría (entre paréntesis, cuántos errores hay).</li>
<li><b>Ignorar:</b> oculta ese error solo durante la sesión (no cambia los porcentajes). «Mostrar N ignorados» o «Restaurar todos» los recupera.</li>
<li><b>Agregar al diccionario</b> (solo en errores de ortografía): sirve para marcas, nombres y términos del cliente. La palabra deja de marcarse en adelante.</li>
<li><b>Color:</b> cada error de color muestra dos muestras con su código HEX: el del cliente y el de tu diseño.</li>
<li><b>Ortografía:</b> muestra sugerencias. Una <i>tilde faltante</i> tiene una sola sugerencia y severidad alta.</li>
<li><b>Posible error de lectura del OCR</b> (severidad baja): el OCR pudo confundirse (aprendido de tus revisiones). Míralo, pero probablemente no sea un error real.</li>
<li><b>Fuentes del diseño:</b> al final hay una tabla desplegable con todas las fuentes, tamaños y estilos del PDF; sirve para verificar que la tipografía es la correcta.</li>
</ul>
<div class="nota"><b>Recuerda:</b> el OCR no es perfecto. Confirma siempre mirando el recuadro. Si el diseño tiene una tilde y el OCR no la ve en el arte, no se reporta; si tu diseño NO la tiene y el arte sí, se reporta como falta de ortografía.</div>

<h1>7. Sensibilidad y recalcular</h1>
{fig("08_sensibilidad", "Panel de sensibilidad con los tres deslizadores.", 90)}
<p>El botón <b>Sensibilidad</b> abre tres controles:</p>
<ul>
<li><b>Umbral SSIM:</b> más alto = más exigente para marcar diferencias visuales.</li>
<li><b>Tolerancia de color (ΔE):</b> cuánto puede diferir un color antes de marcarse (10 por defecto; 1 es muy estricto).</li>
<li><b>Área mínima de región (px):</b> ignora diferencias más pequeñas que esto.</li>
</ul>
<p>Pulsa <b>Recalcular</b> para repetir el análisis con esos valores. Los valores por defecto están en <code>config.json</code>. Si ves muchos falsos positivos, sube la tolerancia y el área mínima; si se te escapan errores, bájalas.</p>

<h1>8. Alinear manualmente</h1>
{fig("13_alinear_manual", "Ventana de alineación manual: 4 puntos en cada imagen.", 90)}
<p>La alineación automática funciona casi siempre, incluso con fotos torcidas, capturas con marco de celular o escaneos. Si sale «mala» o «regular»:</p>
<ol>
<li>Pulsa <b>Alinear manualmente</b>.</li>
<li>Marca <b>4 puntos equivalentes</b> en la imagen del cliente (izquierda) y los mismos 4 en tu diseño (derecha), <b>en el mismo orden</b> (por ejemplo las cuatro esquinas de un recuadro).</li>
<li>Pulsa <b>Aplicar y recalcular</b>. La calidad pasa a «manual».</li>
</ol>

<h1>9. Zonas a ignorar y plantillas por cliente</h1>
{fig("10_zonas", "Una zona ignorada (rayada) y el panel «Zonas ignoradas».", 90)}
<p>Hay cosas que siempre difieren y no importan (una fecha variable, un código QR, un pie legal). Ignóralas así:</p>
<ol>
<li>Elige el modo junto a <b>Ignorar zona</b>: <i>todo</i>, <i>solo color</i> o <i>solo texto</i> (incluye ortografía y fuente).</li>
<li>Pulsa <b>Ignorar zona</b> y dibuja un rectángulo sobre el visor.</li>
<li>Pulsa <b>Aplicar y recalcular</b>. Lo que caiga dentro queda marcado como ignorado y <b>no cuenta</b> en los porcentajes.</li>
</ol>
<h3>Plantillas</h3>
<p>Con zonas dibujadas pulsa <b>Guardar como plantilla…</b> y ponle un nombre (por ejemplo «Cliente Pérez – volante»). Las zonas se guardan en coordenadas relativas, así que valen aunque cambie la resolución. La próxima vez elígela en <b>Plantilla de zonas</b> antes de comparar; la app también la sugiere sola por el nombre del archivo o el tamaño. Las plantillas viven en <code>datos_locales/plantillas/</code> y no se suben a GitHub.</p>

<h1>10. Checklist de aprobación</h1>
{fig("11_checklist", "Cada error tiene su estado y comentario; arriba aparece «Listo para enviar».", 90)}
<p>Cada error tiene un selector: <b>Pendiente</b>, <b>Corregido ✔</b> o <b>No aplica</b>, y un campo de comentario opcional. Todo se guarda en el resultado y en el historial.</p>
<p>Cuando ya no queda ningún error pendiente, el resumen muestra <b>✔ Listo para enviar</b>. El reporte PDF incluye el estado y los comentarios de cada error.</p>

<h1>11. El reporte PDF</h1>
<p>El botón <b>Descargar reporte PDF</b> genera un informe con:</p>
<ul>
<li><b>Portada:</b> fecha, nombres de archivo, % total, semáforo, % por categoría y si está listo para enviar.</li>
<li><b>Imágenes:</b> cliente y diseño lado a lado con todos los errores marcados y numerados.</li>
<li><b>Tabla de errores:</b> número, categoría, «Cliente dice», «Diseño dice», una miniatura de la zona y el estado con su comentario.</li>
</ul>
<p>Los errores en zonas ignoradas no aparecen en el reporte.</p>

<h1>12. Comparar versiones de mi diseño</h1>
<p>Para saber qué cambió entre dos versiones tuyas (por ejemplo tras una ronda de correcciones):</p>
<ol>
<li>En <b>Qué quieres comparar</b> elige <b>Versiones de mi diseño (v1 vs. v2)</b>.</li>
<li>Carga el PDF de la versión 1 en A y el de la versión 2 (la nueva) en B.</li>
<li>Pulsa <b>Comparar versiones</b>.</li>
</ol>
<p>Como ambos son PDF vectoriales, el texto se compara <b>exacto, sin OCR</b> («v1 dice / v2 dice»); además se comparan fuentes, tamaños, colores de cada texto y el aspecto visual. Si alguna versión tiene el texto convertido a curvas, solo se compara el aspecto y se avisa.</p>

<h1>13. Verificar correcciones</h1>
<p>Después de corregir tu diseño según el resultado, no tienes que rehacer todo:</p>
<ol>
<li>Con el resultado anterior abierto, pulsa <b>Verificar correcciones…</b>.</li>
<li>Sube el <b>PDF corregido</b>. La app lo compara con el <b>mismo arte del cliente</b>.</li>
<li>Arriba aparece un cuadro verde: <i>N corregidos · N siguen · N nuevos</i>. Despliega la lista de corregidos ✔ y de los que siguen ✘ (con enlace a cada uno).</li>
</ol>
<p>El estado del checklist de los errores que siguen (por ejemplo «No aplica») se conserva.</p>

<h1>14. Comparar todas las páginas</h1>
<p>Si los archivos tienen varias páginas, pulsa <b>Comparar todas las páginas</b>. La app empareja las páginas por orden; si el número de páginas difiere, las empareja por parecido visual y te dice cuáles quedaron sin pareja. Trabaja en segundo plano con progreso por página.</p>
<p>Al terminar verás una tabla por página (porcentaje, estado, errores y pendientes) con un botón <b>Abrir</b> para ver el detalle de cada una, y un enlace <b>Reporte PDF de todo el lote</b> con un solo documento.</p>

<h1>15. Modo revisión y casos de prueba</h1>
{fig("09_revision", "Modo revisión: botones ✔ Real / ✘ Falso positivo en cada error.", 90)}
<p>El <b>Modo revisión</b> convierte tus comparaciones en «casos» que sirven para medir la precisión y para que el OCR aprenda (sección 16). Todo se guarda en <code>datos_locales/</code>, que <b>nunca se sube a GitHub</b>.</p>
<ol>
<li>Compara normalmente y pulsa <b>Modo revisión</b>.</li>
<li>En cada error marca <b>✔ Real</b> (la app acertó) o <b>✘ Falso positivo</b> (la app se equivocó). Los que no marques se guardan como reales.</li>
<li>Si hay algo que la app <b>no detectó</b>, pulsa <b>Marcar error no detectado</b>, dibuja un rectángulo sobre esa zona, elige la categoría y escribe lo que dice el cliente.</li>
<li>Elige el <b>tipo de arte</b> (exportado, WhatsApp, foto, escaneo, captura, CMYK, curvas) y, si quieres medir el OCR, transcribe el <b>texto exacto</b> del cliente.</li>
<li>Pulsa <b>Guardar como caso de prueba</b>. Se crea <code>datos_locales/casos/caso_NNN/</code>.</li>
</ol>
<h3>Qué casos reunir (meta: 20)</h3>
<table>
<tr><th>Tipo de arte del cliente</th><th>Casos</th></tr>
<tr><td>PNG/JPG exportado limpio (sin errores)</td><td>3</td></tr>
<tr><td>PNG/JPG exportado con errores de texto (precio, fecha, nombre, teléfono)</td><td>3</td></tr>
<tr><td>Captura de WhatsApp</td><td>3</td></tr>
<tr><td>Foto con el celular (torcida, con luz)</td><td>3</td></tr>
<tr><td>Escaneo</td><td>2</td></tr>
<tr><td>PDF del cliente en CMYK</td><td>2</td></tr>
<tr><td>Texto pequeño, fondo de color o texto claro sobre oscuro</td><td>2</td></tr>
<tr><td>PDF de varias páginas</td><td>1</td></tr>
<tr><td>Diseño con el texto convertido a curvas</td><td>1</td></tr>
</table>
<p>Idealmente cada caso tiene entre 0 y 8 errores conocidos de categorías variadas.</p>

<h1>16. Aprendizaje del OCR</h1>
{fig("12_aprendizaje", "Panel «Aprendizaje» (botón en la barra superior).", 90)}
<p>Cada caso revisado enseña algo a la app, siempre en tu equipo:</p>
<table>
<tr><th>Nivel</th><th>Qué aprende</th><th>Efecto</th></tr>
<tr><td>1. Vocabulario y patrones</td><td>Marcas y nombres de tus diseños; formas de precios, teléfonos y fechas.</td><td>Esas palabras dejan de marcarse como error; se pasan a Tesseract.</td></tr>
<tr><td>2. Confusiones</td><td>Letras que el OCR suele confundir (rn→m, l→i, e→é), a partir de tus «✘ Falso positivo».</td><td>Una diferencia explicada solo por confusiones vistas 3 o más veces se muestra como «posible error de lectura». <b>Nunca</b> se oculta un cambio de números (10.000 → 12.000).</td></tr>
<tr><td>3. Ajuste por tipo de imagen</td><td>El mejor preprocesado del OCR para cada tipo (exportado, WhatsApp, foto, escaneo, captura).</td><td>Cada 5 casos, en segundo plano. Solo se adopta si mejora en casos que no vio y no empeora el resultado completo.</td></tr>
<tr><td>4. Re-entrenamiento (opcional)</td><td>Ajusta el modelo de español de Tesseract con 300 o más líneas revisadas.</td><td>Solo se activa si mejora la prueba A/B; se puede volver al modelo original.</td></tr>
</table>
<h3>El panel</h3>
<ul>
<li>Resumen: casos revisados, palabras aprendidas, confusiones y líneas acumuladas para entrenar (x/300).</li>
<li><b>Ajustar OCR ahora</b> y <b>Re-entrenar modelo</b> (se habilita con 300 líneas), con el registro de la tarea en curso.</li>
<li>Lista de confusiones y de vocabulario, cada elemento con opción de <b>borrar</b>.</li>
<li><b>Exportar / Importar:</b> llevas lo aprendido a otro equipo en un ZIP. Por defecto <b>no</b> incluye imágenes de clientes; «con recortes» sí (avisa que son datos privados).</li>
</ul>
<h3>Por línea de comandos</h3>
<pre>uv run faverview-aprender --resumen
uv run faverview-aprender --ajustar
uv run faverview-aprender --entrenar
uv run faverview-aprender --original
uv run faverview-aprender --exportar aprendizaje.zip
uv run faverview-aprender --importar aprendizaje.zip</pre>
<div class="nota">Con pocos casos no verás mejoras: el aprendizaje rinde cuando los errores del OCR se repiten (mismas fuentes, mismo tipo de imagen). Es normal que al principio no cambie nada.</div>

<h1>17. Banco de pruebas (uso avanzado)</h1>
<p>Mide con números qué tan bien funciona la app y si un cambio mejora o empeora:</p>
<pre>uv run python -m bench.run --etiqueta "mi prueba"</pre>
<p>Opciones: <code>--real</code>, <code>--sinteticos</code>, <code>--caso caso_007</code>, <code>--workers 3</code>, <code>--contra "otra etiqueta"</code>. Genera un reporte (<code>.md</code> y <code>.html</code>) en <code>datos_locales/bench_resultados/</code> con precisión, recall, F1, falsos positivos por caso, CER del OCR y tiempos, comparado con la corrida anterior, más la lista de falsos positivos y negativos con miniaturas.</p>
<ul>
<li><code>uv run python -m bench.synth</code> regenera los 78 casos sintéticos.</li>
<li><code>uv run python -m bench.comparar "etiqueta A" "etiqueta B"</code> produce la tabla «antes vs después» por métrica y por tipo de imagen.</li>
<li><code>uv run python -m bench.learn_sim</code> simula la curva de aprendizaje.</li>
</ul>
<p>Metas de referencia: recall de texto ≥ 95 %, precisión de texto ≥ 90 %, recall de color y visual ≥ 90 %, máximo 1 falso positivo por caso, CER ≤ 3 %, idénticos siempre «Aprobado» y ≤ 15 s por página.</p>

<h1>18. Historial, actualizaciones y datos guardados</h1>
<h3>Historial</h3>
<p>El selector <b>Historial</b> (arriba a la derecha) reabre cualquiera de las últimas 50 comparaciones, incluidos lotes. Los resultados se conservan 30 días.</p>
<h3>Actualizaciones</h3>
<p>Una vez al día, si hay internet, la app comprueba si hay una versión nueva y muestra un aviso azul con el botón <b>Actualizar</b> (equivale a <code>git pull</code>; después cierra la ventana negra y vuelve a abrir la app). Nunca bloquea el arranque. La versión actual aparece al pie de la página.</p>
<h3>Dónde se guarda todo</h3>
<table>
<tr><th>Carpeta</th><th>Contenido</th><th>¿Se sube a GitHub?</th></tr>
<tr><td><code>data/results</code>, <code>data/uploads</code></td><td>Resultados y archivos subidos (temporales)</td><td>No</td></tr>
<tr><td><code>data/diccionario_personal.txt</code></td><td>Palabras que agregaste al diccionario</td><td>No</td></tr>
<tr><td><code>datos_locales/casos</code></td><td>Tus casos de prueba reales</td><td>No</td></tr>
<tr><td><code>datos_locales/aprendizaje</code></td><td>Lo que aprendió el OCR</td><td>No</td></tr>
<tr><td><code>datos_locales/plantillas</code></td><td>Plantillas de zonas por cliente</td><td>No</td></tr>
<tr><td><code>datos_locales/bench_resultados</code></td><td>Reportes del banco de pruebas</td><td>No</td></tr>
</table>

<h1>19. Problemas frecuentes</h1>
<table>
<tr><th>Síntoma</th><th>Qué hacer</th></tr>
<tr><td>Aviso «no se encontró Tesseract» o no se compara el texto</td><td>Instálalo: <code>winget install UB-Mannheim.TesseractOCR</code> y reinicia la app.</td></tr>
<tr><td>Muchos errores «visuales» en una foto torcida</td><td>Mira la calidad de alineación; usa «Alinear manualmente». Sube el área mínima en Sensibilidad.</td></tr>
<tr><td>Marca colores distintos en un arte de WhatsApp o foto</td><td>Sube la tolerancia de color (ΔE) a 12–15.</td></tr>
<tr><td>Marca faltas de ortografía en marcas o nombres</td><td>Usa «Agregar al diccionario». Si viene del arte del cliente, aparece igual y no se marca.</td></tr>
<tr><td>«Los archivos originales de este análisis ya no están disponibles»</td><td>Los archivos subidos se borran al reiniciar la app. Vuelve a subirlos para recalcular.</td></tr>
<tr><td>El diseño no tiene texto vectorial</td><td>Exporta el PDF sin convertir el texto a curvas; si no, se usa OCR también sobre el diseño (menos preciso).</td></tr>
<tr><td>Colores raros con un arte CMYK</td><td>Si el CMYK no tiene perfil, la conversión es aproximada. Pide una versión sRGB al cliente.</td></tr>
<tr><td>El navegador no se abre</td><td>Abre a mano la dirección de la ventana negra (por ejemplo http://127.0.0.1:8000).</td></tr>
<tr><td>Tarda más de 15 segundos</td><td>Es normal en equipos con 4 núcleos o menos: el OCR trabaja en paralelo.</td></tr>
<tr><td>El PDF del cliente tiene contraseña o está dañado</td><td>La app lo indica; quítale la contraseña o vuelve a exportarlo.</td></tr>
</table>

<h1>20. Glosario y atajos</h1>
<table>
<tr><th>Término</th><th>Significado</th></tr>
<tr><td>OCR</td><td>Lectura automática del texto de una imagen (usa Tesseract).</td></tr>
<tr><td>CER</td><td>Tasa de error por carácter del OCR (menos es mejor).</td></tr>
<tr><td>SSIM</td><td>Medida de parecido visual entre dos imágenes (100 % = idénticas).</td></tr>
<tr><td>Delta E (ΔE)</td><td>Distancia entre dos colores; alrededor de 2 apenas se nota, más de 10 es evidente.</td></tr>
<tr><td>Falso positivo</td><td>Algo que la app marcó y no era un error real.</td></tr>
<tr><td>Falso negativo</td><td>Un error real que la app no marcó.</td></tr>
<tr><td>CMYK / sRGB</td><td>Espacios de color de impresión / de pantalla.</td></tr>
<tr><td>PDF vectorial</td><td>PDF con texto real (seleccionable), no convertido a imagen ni a curvas.</td></tr>
</table>
<table>
<tr><th>Atajo</th><th>Acción</th></tr>
<tr><td>Ctrl+V</td><td>Pegar una imagen como arte del cliente (o diseño)</td></tr>
<tr><td>Rueda del ratón</td><td>Zoom en el visor</td></tr>
<tr><td>Arrastrar</td><td>Mover la página en el visor</td></tr>
<tr><td>Clic en un error o recuadro</td><td>Zoom a la zona y parpadeo</td></tr>
</table>
"""
from capitulos_suite import suite
manual += suite(fig)

# =============================================================================== INSTALACIÓN
guia = """
<h1>Contenido</h1>
<ol>
<li>Antes de empezar</li>
<li>Instalación paso a paso</li>
<li>Comprobar que todo funciona</li>
<li>Uso diario y acceso directo</li>
<li>Instalar en varios equipos</li>
<li>Actualizar, desinstalar y llevar tus datos</li>
<li>Si algo falla</li>
</ol>

<h1>1. Antes de empezar</h1>
<h3>Qué necesitas</h3>
<ul>
<li>Un computador con <b>Windows 10 u 11</b> (64 bits).</li>
<li><b>Internet</b>, solo durante la instalación y para actualizar. La app funciona sin conexión.</li>
<li>Unos <b>2 GB libres</b> de disco y 5 a 10 minutos.</li>
<li>No hace falta ser administrador.</li>
</ul>
<h3>Qué se instala</h3>
<table>
<tr><th>Programa</th><th>Para qué sirve</th></tr>
<tr><td>uv</td><td>Descarga Python y las librerías de la app automáticamente.</td></tr>
<tr><td>Git</td><td>Descarga FAVERVIEW desde GitHub y permite actualizarlo.</td></tr>
<tr><td>Tesseract OCR</td><td>Lee el texto de las imágenes.</td></tr>
<tr><td>Ghostscript (opcional)</td><td>Separa PDF en placas y habilita trapping, cobertura y EPS (paso 2b).</td></tr>
</table>
<div class="nota"><b>¿Por qué no hay un instalador .exe?</b> Windows y los antivirus marcan como sospechosos los ejecutables sin firma digital. FAVERVIEW se instala con <b>winget</b> (el instalador oficial de Windows) y paquetes firmados, así que no aparecen avisos de virus.</div>

<h1>2. Instalación paso a paso</h1>
<p>Solo se hace <b>una vez</b> por computador.</p>
<h2>Paso 1 – Abrir PowerShell</h2>
<p>Menú Inicio → escribe <b>PowerShell</b> → ábrelo. No hace falta abrirlo como administrador.</p>
<h2>Paso 2 – Instalar las herramientas</h2>
<p>Copia y pega este comando y presiona Enter. Acepta los permisos si Windows los pide.</p>
<pre>winget install -e --id astral-sh.uv; winget install -e --id Git.Git; winget install -e --id UB-Mannheim.TesseractOCR</pre>
<p><b>Cierra PowerShell y ábrelo de nuevo</b> para que Windows reconozca los programas nuevos.</p>
<h2>Paso 2b – Instalar Ghostscript (para los módulos de preprensa)</h2>
<p>No está en winget. Copia este comando en PowerShell: descarga la versión oficial de Artifex, <b>verifica su firma</b> y solo entonces la instala (pide permiso de administrador). Sin Ghostscript la app funciona, pero no separa PDF en placas.</p>
<pre>$r = Invoke-RestMethod https://api.github.com/repos/ArtifexSoftware/ghostpdl-downloads/releases/latest; $a = $r.assets | ? name -like '*w64.exe'; $f = "$env:TEMP\\$($a.name)"; Invoke-WebRequest $a.browser_download_url -OutFile $f; $s = Get-AuthenticodeSignature $f; if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'Artifex') { Start-Process $f -ArgumentList '/S' -Verb RunAs -Wait; Write-Host 'Ghostscript instalado' } else { Write-Host "Firma NO valida: $($s.Status). No se instalo." }</pre>
<p>Verifica con <code>&amp; (Get-ChildItem "C:\\Program Files\\gs\\*\\bin\\gswin64c.exe" | Select -Last 1).FullName --version</code>. Si dice «Firma NO valida» no se instala nada: descarga Ghostscript desde ghostscript.com y comprueba la firma antes de ejecutarlo.</p>
<h2>Paso 3 – Descargar FAVERVIEW</h2>
<p>Esto crea la carpeta <code>FAVERVIEW</code> en tu carpeta de usuario:</p>
<pre>git clone https://github.com/sebastiansantos0311-dev/faverview.git $HOME\\FAVERVIEW</pre>
<p>Si el repositorio es privado, Git abrirá una ventana para iniciar sesión en GitHub; hazlo con tu cuenta.</p>
<h2>Paso 4 – Primer arranque</h2>
<pre>cd $HOME\\FAVERVIEW; uv run faverview</pre>
<p>La primera vez descarga Python y las librerías (unos minutos). Después se abre el navegador con la aplicación.</p>
<h2>Paso 5 – Acceso directo con el logo (automático)</h2>
<p>En el <b>primer arranque</b> (paso 4) FAVERVIEW crea solo el acceso directo <b>FAVERVIEW</b> (con el logo del calvito con gafas) en tu Escritorio <b>y en la carpeta principal de la app</b>. Desde entonces basta con hacer doble clic en cualquiera de los dos. Si lo borras y quieres recrearlo:</p>
<pre>cd $HOME\FAVERVIEW; uv run faverview --acceso-directo</pre>

<h1>3. Comprobar que todo funciona</h1>
<ol>
<li>Con la app abierta, arrastra <code>samples\\cliente_errores.png</code> a la zona A y <code>samples\\diseno.pdf</code> a la zona B (están dentro de la carpeta FAVERVIEW).</li>
<li>Pulsa <b>Comparar</b>.</li>
<li>Debes ver cerca de <b>96 % «Revisar»</b> con 4 errores: un precio cambiado (12.000 vs 10.000), la palabra «especiales» sobrante, un rectángulo de otro color y un logo que falta.</li>
<li>Con <code>samples\\cliente_ok.png</code> contra el mismo diseño debe dar <b>100 % «Aprobado»</b>.</li>
</ol>
<p>Opcional, para verificar la instalación completa (unos 2 minutos):</p>
<pre>cd $HOME\\FAVERVIEW; uv run pytest</pre>

<h1>4. Uso diario y acceso directo</h1>
<ol>
<li>Doble clic en el acceso directo <b>FAVERVIEW</b> (o <code>uv run faverview</code> dentro de la carpeta).</li>
<li>Se abre una ventana negra (el servidor) y el navegador. <b>No cierres la ventana negra</b> mientras usas la app.</li>
<li>Para salir, cierra la ventana negra.</li>
</ol>
<p>La app solo es accesible desde tu propio equipo (127.0.0.1), no desde la red.</p>

<h1>5. Instalar en varios equipos</h1>
<ul>
<li>Repite los <b>pasos 1 a 5</b> en cada computador. No copies la carpeta <code>.venv</code> de otro equipo.</li>
<li>Para llevar lo que el OCR aprendió: en el equipo de origen abre <b>Aprendizaje → Exportar</b> (o <code>uv run faverview-aprender --exportar aprendizaje.zip</code>) y en el nuevo <b>Importar</b> (o <code>--importar</code>). Por defecto no incluye imágenes de clientes.</li>
<li>Tus casos de prueba, plantillas y el diccionario personal están en <code>datos_locales</code> y <code>data</code>; cópialos a mano si los quieres en el otro equipo.</li>
<li>Si descargaste un ZIP en vez de usar <code>git clone</code>: antes de descomprimir, clic derecho en el ZIP → <b>Propiedades</b> → marca <b>Desbloquear</b> → Aceptar. Con ZIP no funcionará el aviso de actualización.</li>
</ul>

<h1>6. Actualizar, desinstalar y llevar tus datos</h1>
<h3>Actualizar</h3>
<p>La app avisa (una vez al día, con internet) cuando hay una versión nueva; pulsa <b>Actualizar</b> o hazlo a mano:</p>
<pre>cd $HOME\\FAVERVIEW; git pull</pre>
<p>La próxima vez que abras la app, uv instalará lo que haga falta.</p>
<h3>Desinstalar</h3>
<ol>
<li>Cierra la app y borra la carpeta <code>FAVERVIEW</code> (antes copia <code>datos_locales</code> si quieres conservar tus casos y lo aprendido).</li>
<li>Borra el acceso directo del Escritorio.</li>
<li>Si ya no los necesitas: <code>winget uninstall astral-sh.uv</code>, <code>winget uninstall Git.Git</code> y <code>winget uninstall UB-Mannheim.TesseractOCR</code>.</li>
</ol>

<h1>7. Si algo falla</h1>
<table>
<tr><th>Problema</th><th>Solución</th></tr>
<tr><td>«winget no se reconoce»</td><td>Instala <b>App Installer</b> desde Microsoft Store y vuelve a abrir PowerShell.</td></tr>
<tr><td>«uv» o «git» no se reconoce después del paso 2</td><td>Cierra y vuelve a abrir PowerShell. Si sigue igual, reinicia el equipo.</td></tr>
<tr><td>Aviso «no se encontró Tesseract»</td><td>Ejecuta <code>winget install UB-Mannheim.TesseractOCR</code> y reinicia la app.</td></tr>
<tr><td>Aviso «falta Ghostscript» en Separar, Preflight o Herramientas</td><td>Sigue el paso 2b y reinicia la app.</td></tr>
<tr><td>El navegador no se abre</td><td>Abre a mano la dirección que aparece en la ventana negra (por ejemplo <code>http://127.0.0.1:8000</code>).</td></tr>
<tr><td>Puerto en uso</td><td>La app usa automáticamente el siguiente puerto libre (8001, 8002…); mira la ventana negra.</td></tr>
<tr><td>La primera vez tarda mucho</td><td>Es normal: descarga Python y las librerías (varios cientos de MB). Las siguientes veces abre en segundos.</td></tr>
<tr><td>El antivirus o SmartScreen avisa</td><td>FAVERVIEW no trae ejecutables propios; el aviso suele venir de PowerShell o de un programa recién descargado. Si usas <code>git clone</code> y winget, no debería aparecer.</td></tr>
<tr><td>Error de certificados o de red al instalar</td><td>Comprueba tu conexión o proxy de la empresa y repite el comando.</td></tr>
<tr><td>«Permiso denegado» al crear el acceso directo</td><td>Ejecuta el comando desde una carpeta tuya (<code>$HOME\\FAVERVIEW</code>) y sin abrir PowerShell como administrador.</td></tr>
</table>
<div class="nota">¿Sigues con problemas? Anota el mensaje exacto de la ventana negra o de PowerShell; casi siempre dice qué falta.</div>
"""

build(manual, OUT / "Manual_de_uso_FAVERVIEW.pdf", "Manual de uso", ("Manual de uso", "Guía completa de la aplicación"))
build(guia, OUT / "Guia_de_instalacion_FAVERVIEW.pdf", "Guía de instalación", ("Guía de instalación", "Cómo instalar FAVERVIEW en un computador"))
