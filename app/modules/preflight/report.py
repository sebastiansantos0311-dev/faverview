"""Reporte PDF de preflight (S6 §10.1): resumen, lista con miniatura de la zona, perfil y fecha."""
from datetime import datetime
from html import escape

import pymupdf

SEV = {"error": ("Errores", "#b91c1c"), "advertencia": ("Advertencias", "#b45309"), "info": ("Información", "#1d4ed8")}


def _thumb(doc, page: int, bbox, dpi: int) -> bytes | None:
    try:
        pg = doc[page - 1]
        s = 72 / dpi
        x, y, w, h = bbox
        pad = max(w, h, 40) * 0.6
        r = pymupdf.Rect((x - pad) * s, (y - pad) * s, (x + w + pad) * s, (y + h + pad) * s) & pg.rect
        if r.is_empty:
            return None
        pix = pg.get_pixmap(clip=r, dpi=110)
        return pix.tobytes("png")
    except Exception:
        return None


def build_report(pdf_path, result: dict, name: str = "") -> bytes:
    doc = pymupdf.open(str(pdf_path))
    arch = pymupdf.Archive()
    parts = [f"<h1>Informe de preflight</h1><p><b>Archivo:</b> {escape(name or str(pdf_path))}<br><b>Perfil:</b> {escape(result['perfil'])}<br>"
             f"<b>Fecha:</b> {datetime.now():%Y-%m-%d %H:%M}<br><b>Páginas:</b> {result['paginas']}</p>"]
    r = result["resumen"]
    parts.append(f"<p><b>Resumen:</b> {r['error']} errores · {r['advertencia']} advertencias · {r['info']} avisos informativos.</p>")
    parts.append("<p><i>Revisión automática orientativa; no es una certificación.</i></p>")
    for n in result.get("notas", []):
        parts.append(f"<p><i>Nota: {escape(n)}</i></p>")
    k = 0
    for sev, (title, color) in SEV.items():
        items = [f for f in result["hallazgos"] if f["severidad"] == sev]
        if not items:
            continue
        parts.append(f'<h2 style="color:{color}">{title} ({len(items)})</h2>')
        for f in items[:200]:
            img = ""
            if f.get("bbox"):
                png = _thumb(doc, f["pagina"], f["bbox"], result.get("dpi", 150))
                if png:
                    k += 1
                    arch.add(png, f"t{k}.png")
                    img = f'<br><img src="t{k}.png" width="160">'
            parts.append(f"<p><b>{escape(f['nombre'])}</b> (pág. {f['pagina']}): {escape(f['mensaje'])}{img}</p>")
    if not result["hallazgos"]:
        parts.append("<p>No se encontraron problemas con este perfil.</p>")
    story = pymupdf.Story("".join(parts), archive=arch)
    out = pymupdf.open()
    writer = pymupdf.DocumentWriter(out_buf := __import__("io").BytesIO())
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (40, 40, -40, -40)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    doc.close()
    return out_buf.getvalue()
