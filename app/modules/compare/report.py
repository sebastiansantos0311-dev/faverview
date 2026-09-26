"""Reporte PDF (PyMuPDF): portada, imágenes con recuadros y tabla de errores con miniaturas."""
from pathlib import Path

import cv2
import numpy as np
import pymupdf

from app.modules.compare.compare_visual import save_png  # noqa: F401  (reutilizable)
from app.modules.compare.models import Result

CAT_RGB = {"text": (220, 38, 38), "spelling": (234, 179, 8), "color": (249, 115, 22),
           "visual": (37, 99, 235), "font": (147, 51, 234)}
CAT_NAME = {"text": "Texto", "spelling": "Ortografía", "color": "Color",
            "visual": "Elemento visual", "font": "Fuente"}
STATUS = {"aprobado": ("Aprobado", (22, 163, 74)), "revisar": ("Revisar", (202, 138, 4)),
          "con_errores": ("Con errores", (220, 38, 38))}


from app.core.reports import clean_text as _clean  # noqa: E402
from app.core.reports import jpg_bytes as _png  # noqa: E402
from app.core.reports import load_rgb as _load  # noqa: E402
from app.core.reports import norm_color as _norm  # noqa: E402


def _draw_boxes(img: np.ndarray, diffs) -> np.ndarray:
    out = img.copy()
    th = max(2, img.shape[1] // 400)
    for d in diffs:
        x, y, w, h = d.bbox
        c = CAT_RGB[d.category]
        cv2.rectangle(out, (x, y), (x + w, y + h), c, th)
        cv2.putText(out, str(d.id), (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX,
                    max(0.5, img.shape[1] / 1800), c, max(1, th - 1), cv2.LINE_AA)
    return out


def _sides(d):
    if d.category == "text":
        return d.expected or "(nada)", d.found or "(nada)"
    if d.category == "spelling":
        return "-", f"{d.found}" + (f"  ->  {', '.join(d.suggestions)}" if d.suggestions else "")
    if d.category == "color":
        return d.expected_hex or "-", d.found_hex or "-"
    return "-", d.message


def _thumb(design, client, bbox) -> np.ndarray:
    from app.core.reports import thumb_pair
    return thumb_pair(client, design, bbox)


def build_report(result: Result, results_dir: Path, out_path: Path) -> Path:
    design = _load(results_dir / result.images["design"])
    client = _load(results_dir / result.images["client"])
    diffs = [d for d in result.differences if not d.ignored_by_zone]
    doc = pymupdf.open()

    # ---- portada
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 80), "FAVERVIEW - Reporte de comparación", fontsize=22, fontname="hebo")
    p.insert_text((50, 110), f"Fecha: {result.created.replace('T', ' ')}", fontsize=11)
    p.insert_text((50, 130), f"Arte del cliente: {_clean(result.client_name)}", fontsize=11)
    p.insert_text((50, 146), f"Mi diseño: {_clean(result.design_name)}", fontsize=11)
    label, col = STATUS[result.status]
    p.draw_circle((80, 220), 28, color=None, fill=_norm(col))
    p.insert_text((125, 215), f"{result.scores['total']:.1f}% de similitud", fontsize=28, fontname="hebo")
    p.insert_text((125, 240), f"{label}  -  {100 - result.scores['total']:.1f}% de diferencia",
                  fontsize=13, fontname="helv", color=_norm(col))
    y = 300
    p.insert_text((50, y), "Porcentaje por categoría", fontsize=14, fontname="hebo")
    y += 24
    for key, name in (("visual", "Visual (SSIM)"), ("text", "Texto"), ("color", "Color"),
                      ("spelling", "Ortografía"), ("font", "Fuente")):
        v = result.scores.get(key, 0)
        cat = "visual" if key == "visual" else key
        p.insert_text((50, y + 10), f"{name}", fontsize=11)
        p.draw_rect(pymupdf.Rect(180, y, 480, y + 12), color=(0.8, 0.8, 0.8), fill=(0.93, 0.93, 0.93))
        p.draw_rect(pymupdf.Rect(180, y, 180 + 300 * v / 100, y + 12), color=None, fill=_norm(CAT_RGB[cat]))
        p.insert_text((490, y + 10), f"{v:.1f}%", fontsize=11)
        y += 26
    y += 14
    vivos = [d for d in result.differences if not d.ignored_by_zone]
    pend = sum(d.status == "pendiente" for d in vivos)
    ok = (pend == 0)
    p.insert_text((50, y), "Listo para enviar" if ok else f"{pend} error(es) pendiente(s) de corregir",
                  fontsize=14, fontname="hebo", color=(0.09, 0.64, 0.29) if ok else (0.8, 0.15, 0.15))
    y += 22
    if result.fix_report:
        p.insert_text((50, y), "Verificación de correcciones: " + result.fix_report["resumen"], fontsize=11)
        y += 18
    p.insert_text((50, y), f"Errores encontrados: {len(diffs)}", fontsize=14, fontname="hebo")
    y += 22
    for cat, n in sorted(result.counts.items()):
        p.draw_rect(pymupdf.Rect(50, y - 9, 60, y + 1), color=None, fill=_norm(CAT_RGB[cat]))
        p.insert_text((68, y), f"{CAT_NAME[cat]}: {n}", fontsize=11)
        y += 18
    for w in result.warnings:
        y += 10
        p.insert_textbox(pymupdf.Rect(50, y, 545, y + 60), "Aviso: " + _clean(w), fontsize=10,
                         color=(0.6, 0.35, 0))
        y += 40

    # ---- imágenes lado a lado (horizontal)
    pg = doc.new_page(width=842, height=595)
    pg.insert_text((30, 28), "Arte del cliente (izquierda) vs Mi diseño (derecha), con los errores marcados",
                   fontsize=12, fontname="hebo")
    H, W = design.shape[:2]
    avail_w, avail_h = 842 / 2 - 40, 595 - 80
    s = min(avail_w / W, avail_h / H)
    iw, ih = W * s, H * s
    tgt_w = int(min(W, 1400))
    k = tgt_w / W
    for i, im in enumerate((client, design)):
        marked = _draw_boxes(im, diffs)
        marked = cv2.resize(marked, (tgt_w, int(H * k)), interpolation=cv2.INTER_AREA)
        x0 = 30 + i * (iw + 20)
        pg.insert_image(pymupdf.Rect(x0, 45, x0 + iw, 45 + ih), stream=_png(marked))

    # ---- tabla de errores
    row_h, top = 72, 60
    per_page = int((842 - top - 40) // row_h)
    for start in range(0, max(1, len(diffs)), per_page):
        tp = doc.new_page(width=595, height=842)
        tp.insert_text((40, 36), "Lista de errores", fontsize=14, fontname="hebo")
        heads = [(40, "#"), (62, "Categoría"), (128, "Cliente dice"), (222, "Diseño dice"), (318, "Zona (cliente | diseño)"),
                 (470, "Estado / comentario")]
        for x, t in heads:
            tp.insert_text((x, 54), t, fontsize=9, fontname="hebo")
        if not diffs:
            tp.insert_text((40, 90), "No se encontraron diferencias.", fontsize=12)
        for n, d in enumerate(diffs[start:start + per_page]):
            y0 = top + 6 + n * row_h
            c = CAT_RGB[d.category]
            tp.draw_line((40, y0 - 2), (555, y0 - 2), color=(0.85, 0.85, 0.85), width=0.5)
            tp.draw_rect(pymupdf.Rect(40, y0 + 2, 54, y0 + 16), color=None, fill=_norm(c))
            tp.insert_text((42, y0 + 13), str(d.id), fontsize=8, color=(1, 1, 1))
            lbl = CAT_NAME[d.category] + ("\n" + d.subtype.replace("_", " ") if d.subtype else "")
            tp.insert_textbox(pymupdf.Rect(62, y0, 124, y0 + row_h - 4), lbl, fontsize=8)
            left, right = _sides(d)
            tp.insert_textbox(pymupdf.Rect(128, y0, 218, y0 + row_h - 4), _clean(left), fontsize=8)
            tp.insert_textbox(pymupdf.Rect(222, y0, 314, y0 + row_h - 4), _clean(right), fontsize=8)
            th = _thumb(design, client, d.bbox)
            tw = min(140.0, th.shape[1] * 0.75)
            tp.insert_image(pymupdf.Rect(318, y0, 318 + tw, y0 + tw * th.shape[0] / th.shape[1]),
                            stream=_png(th))
            est = {"pendiente": "Pendiente", "corregido": "Corregido", "no_aplica": "No aplica"}[d.status]
            tp.insert_textbox(pymupdf.Rect(470, y0, 556, y0 + row_h - 4),
                              est + ("\n" + _clean(d.comment) if d.comment else ""), fontsize=8,
                              color=(0.09, 0.5, 0.25) if d.status == "corregido" else (0, 0, 0))
        if not diffs:
            break

    doc.save(out_path)
    doc.close()
    return out_path
