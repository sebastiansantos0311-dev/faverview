"""Exportación de placas (S2 §6.5): TIFF 8 bits o 1 bit, PDF de placas e informe de separaciones."""
import csv
import io
import zipfile
from datetime import datetime

import cv2
import numpy as np
import pymupdf
from PIL import Image

from app.modules.separate.pdf_render import Plates


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_ ." else "_" for c in name).strip() or "tinta"


def plate_tiff(arr: np.ndarray, dpi: float, one_bit: bool = False, threshold: int = 128) -> bytes:
    """TIFF de una placa con convención de película: negro = tinta. En 1 bit se umbraliza (sin tramado)."""
    img = 255 - arr
    if one_bit:
        im = Image.fromarray(((arr < threshold) * 255).astype(np.uint8)).convert("1")
        comp = "group4"
    else:
        im = Image.fromarray(img, "L")
        comp = "tiff_lzw"
    buf = io.BytesIO()
    im.save(buf, format="TIFF", dpi=(dpi, dpi), compression=comp)
    return buf.getvalue()


def plates_pdf(plates: Plates, title: str = "") -> bytes:
    """PDF con una página por placa (en gris, negro = tinta), con el nombre y la cobertura."""
    doc = pymupdf.open()
    for n in plates.names:
        w_pt, h_pt = plates.width * 72 / plates.dpi, plates.height * 72 / plates.dpi
        page = doc.new_page(width=w_pt, height=h_pt + 24)
        ok, png = cv2.imencode(".png", 255 - plates.arrays[n])
        page.insert_image(pymupdf.Rect(0, 24, w_pt, h_pt + 24), stream=png.tobytes())
        page.insert_text((6, 16), f"{n} — {plates.pct(n):.2f} % de cobertura", fontsize=10)
        cx, cy = w_pt - 14, 12
        page.draw_line((cx - 6, cy), (cx + 6, cy), width=0.4)
        page.draw_line((cx, cy - 6), (cx, cy + 6), width=0.4)
    doc.set_metadata({"title": title or "Placas FAVERVIEW"})
    out = doc.tobytes(deflate=True)
    doc.close()
    return out


def report_rows(plates: Plates, meta: dict) -> list[dict]:
    rows = []
    for n in plates.names:
        m = meta.get(n) or {}
        rows.append({"tinta": n, "tipo": m.get("tipo", ""), "cobertura_pct": round(plates.pct(n), 3),
                     "vacia": "sí" if plates.empty(n) else "no"})
    return rows


def report_csv(rows: list[dict]) -> bytes:
    s = io.StringIO()
    w = csv.DictWriter(s, fieldnames=["tinta", "tipo", "cobertura_pct", "vacia"], delimiter=";")
    w.writeheader()
    w.writerows(rows)
    return ("﻿" + s.getvalue()).encode("utf-8")


def export_zip(plates: Plates, meta: dict, formato: str, findings: list[dict], threshold: int = 128) -> bytes:
    """ZIP con las placas en el formato pedido (`tiff8`, `tiff1`, `pdf`) más el informe."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if formato in ("tiff8", "tiff1"):
            for n in plates.names:
                if plates.empty(n):
                    continue
                z.writestr(f"{_safe(n)}.tif", plate_tiff(plates.arrays[n], plates.dpi, formato == "tiff1", threshold))
        elif formato == "pdf":
            z.writestr("placas.pdf", plates_pdf(plates))
        rows = report_rows(plates, meta)
        z.writestr("informe_separaciones.csv", report_csv(rows))
        lines = [f"Informe de separaciones — {datetime.now():%Y-%m-%d %H:%M}",
                 f"Resolución: {plates.dpi:g} dpi. Valores orientativos.", ""]
        lines += [f"{r['tinta']}: {r['cobertura_pct']} %" for r in rows]
        lines += ["", "Problemas detectados:"] + ([f"- [{f['severidad']}] {f['mensaje']}" for f in findings] or ["- ninguno"])
        z.writestr("informe_separaciones.txt", "\n".join(lines))
    return buf.getvalue()
