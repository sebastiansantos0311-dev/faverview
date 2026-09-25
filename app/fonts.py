"""Fuentes del PDF de diseño (exactas) y estimación de diferencias en el arte del cliente."""
from collections import OrderedDict

import cv2
import numpy as np

from .compare_text import Word
from .loaders import TextSpan
from .models import Difference


def fonts_in_design(spans: list[TextSpan]) -> list[dict]:
    agg: "OrderedDict[tuple, dict]" = OrderedDict()
    for sp in spans:
        name = sp.font.split("+")[-1]
        key = (name, round(sp.size, 1), sp.bold, sp.italic)
        e = agg.setdefault(key, {"font": name, "size_pt": round(sp.size, 1), "bold": sp.bold,
                                 "italic": sp.italic, "spans": 0, "example": sp.text[:40]})
        e["spans"] += 1
    return sorted(agg.values(), key=lambda e: -e["spans"])


def _ink_mask(crop: np.ndarray) -> np.ndarray | None:
    g = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    if g.size < 16 or g.std() < 8:
        return None
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = (th == 0) if th.mean() > 127 else (th == 255)
    return ink.astype(np.uint8)


def _metrics(img: np.ndarray, bbox, pad: int):
    """(ancho, alto, trazo, inclinación) de la tinta dentro de bbox (con margen)."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, int(x0) - pad), max(0, int(y0) - pad)
    x1, y1 = min(W, int(x1) + pad), min(H, int(y1) + pad)
    crop = img[y0:y1, x0:x1]
    ink = _ink_mask(crop)
    if ink is None or ink.sum() < 12:
        return None
    ys, xs = np.where(ink > 0)
    w, h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    if h < 4 or w < 4:
        return None
    cnts, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    perim = sum(cv2.arcLength(c, True) for c in cnts)
    stroke = 2.0 * float(ink.sum()) / max(perim, 1.0)
    m = cv2.moments(ink, binaryImage=True)
    slant = -m["mu11"] / m["mu02"] if m["mu02"] > 1e-6 else 0.0
    return float(w), float(h), stroke, slant


def compare_fonts(design: np.ndarray, client: np.ndarray, spans: list[TextSpan],
                  pairs: list[tuple[Word, Word]], tol_pct: float) -> tuple[list[Difference], int]:
    """Devuelve (diferencias, total de spans evaluados).
    Compara la misma palabra en ambas imágenes con la misma medición, así el sesgo se cancela."""
    diffs: list[Difference] = []
    evaluated = 0
    tol = tol_pct / 100.0
    for sp in spans:
        sx0, sy0, sx1, sy1 = sp.bbox
        ratios, stroke_r, slant_d = [], [], []
        for dw, cw in pairs:
            cx, cy = (dw.bbox[0] + dw.bbox[2]) / 2, (dw.bbox[1] + dw.bbox[3]) / 2
            if not (sx0 <= cx <= sx1 and sy0 <= cy <= sy1):
                continue
            if len(dw.text) < 3:
                continue
            md = _metrics(design, dw.bbox, 2)
            mc = _metrics(client, cw.bbox, 4)
            if md is None or mc is None:
                continue
            ratios.append(mc[0] / md[0])
            ratios.append(mc[1] / md[1])
            stroke_r.append((mc[2] / mc[1]) / max(md[2] / md[1], 1e-6))
            slant_d.append(mc[3] - md[3])
        if len(ratios) < 2:
            continue
        evaluated += 1
        ratio = float(np.median(ratios))
        details = []
        if abs(ratio - 1.0) > tol:
            cl_pt = sp.size * ratio
            details.append(f"tamaño aprox. {cl_pt:.0f}pt en el cliente vs {sp.size:.0f}pt en tu diseño")
        sr = float(np.median(stroke_r))
        if sr > 1.35:
            details.append("el cliente parece más grueso (¿negrita?)")
        elif sr < 0.72:
            details.append("el cliente parece más delgado (¿sin negrita?)")
        sl = float(np.median(slant_d))
        if abs(sl) > 0.15:
            details.append("distinta inclinación (¿cursiva?)")
        if details:
            diffs.append(Difference(
                category="font", subtype="tamano" if abs(ratio - 1.0) > tol else "estilo",
                bbox=(int(sx0), int(sy0), max(1, int(sx1 - sx0)), max(1, int(sy1 - sy0))),
                severity="media" if abs(ratio - 1.0) > 2 * tol else "baja",
                message="Posible diferencia de fuente: " + "; ".join(details),
                expected=sp.text[:60], found=f"{sp.font.split('+')[-1]} {sp.size:.0f}pt"))
    return diffs, evaluated
