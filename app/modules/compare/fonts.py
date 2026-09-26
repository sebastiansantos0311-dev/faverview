"""Fuentes del PDF de diseño (exactas) y estimación de diferencias en el arte del cliente."""
from collections import OrderedDict

import cv2
import numpy as np

from app.modules.compare.compare_text import Word
from app.loaders import TextSpan
from app.modules.compare.models import Difference


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
    return float(w), float(h), stroke, slant, (x0 + int(xs.min()), y0 + int(ys.min()),
                                                x0 + int(xs.max()) + 1, y0 + int(ys.max()) + 1)


def _sharpness(img: np.ndarray, bbox, pad: int = 4) -> float:
    H, W = img.shape[:2]
    x0, y0, x1, y1 = bbox
    crop = img[max(0, int(y0) - pad):min(H, int(y1) + pad), max(0, int(x0) - pad):min(W, int(x1) + pad)]
    if crop.size == 0:
        return 0.0
    return float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var())


def _exact(dw: Word, cw: Word) -> bool:
    """Solo se usan palabras leídas igual en ambos lados: nunca las marcadas como cambiada/faltante/sobrante."""
    return dw.text.strip(".,;:") == cw.text.strip(".,;:")


MIN_WORDS = 3  # mínimo de palabras coincidentes en un span para concluir algo


def compare_fonts(design: np.ndarray, client: np.ndarray, spans: list[TextSpan],
                  pairs: list[tuple[Word, Word]], tol_pct: float) -> tuple[list[Difference], int]:
    """Devuelve (diferencias, total de spans evaluados).
    Compara la MISMA palabra en ambas imágenes con la misma medición (el sesgo se cancela). El cliente ya viene
    alineado y escalado al marco del diseño, así que los tamaños son directamente comparables. Solo se reporta si la
    diferencia supera la tolerancia y es consistente en la mayoría de las palabras del span."""
    diffs: list[Difference] = []
    evaluated = 0
    tol = tol_pct / 100.0
    exact_pairs = [(d, c) for d, c in pairs if _exact(d, c)]
    for sp in spans:
        sx0, sy0, sx1, sy1 = sp.bbox
        size_r, size_abs, stroke_r, slant_d, sharp = [], [], [], [], []
        for dw, cw in exact_pairs:
            cx, cy = (dw.bbox[0] + dw.bbox[2]) / 2, (dw.bbox[1] + dw.bbox[3]) / 2
            if not (sx0 <= cx <= sx1 and sy0 <= cy <= sy1) or len(dw.text) < 3:
                continue
            md = _metrics(design, dw.bbox, 2)
            if md is None:
                continue
            # el cliente se mide en la zona de la TINTA del diseño (ampliada 35%/30%): así no entran las líneas
            # vecinas ni las cajas infladas del OCR
            ix0, iy0, ix1, iy1 = md[4]
            ew, eh = 0.08 * (ix1 - ix0), 0.35 * (iy1 - iy0)
            mc = _metrics(client, (ix0 - ew, iy0 - eh, ix1 + ew, iy1 + eh), 0)
            if mc is None:
                continue
            size_r.append(float(mc[1] / md[1]))  # la altura no depende de las palabras vecinas
            size_abs.append(mc[1] - md[1])
            if md[1] >= 28:  # con letras muy pequeñas grosor e inclinación no son medibles
                stroke_r.append((mc[2] / mc[1]) / max(md[2] / md[1], 1e-6))
                slant_d.append(mc[3] - md[3])
            sd = _sharpness(design, dw.bbox)
            sharp.append(_sharpness(client, cw.bbox) / sd if sd > 1e-6 else 1.0)
        if len(size_r) < MIN_WORDS:
            continue
        evaluated += 1
        details = []
        r = np.array(size_r)
        ratio = float(np.median(r))
        # consistente: ≥70% de las palabras se desvían más que la tolerancia y en el mismo sentido
        big = (r > 1 + tol) if ratio > 1 else (r < 1 - tol)
        # además de ser relativa, la diferencia debe medir al menos 3 px (el redondeo del raster no cuenta)
        size_diff = abs(ratio - 1.0) > tol and float(big.mean()) >= 0.7 and abs(float(np.median(size_abs))) >= 3
        if size_diff:
            details.append(f"tamaño aprox. {sp.size * ratio:.0f}pt en el cliente vs {sp.size:.0f}pt en tu diseño")
        # grosor e inclinación solo si el cliente está tan nítido como el diseño (con desenfoque no se puede medir)
        if stroke_r and float(np.median(sharp)) >= 0.5:
            s_arr = np.array(stroke_r)
            if np.median(s_arr) > 1.35 and float((s_arr > 1.25).mean()) >= 0.7:
                details.append("el cliente parece más grueso (¿negrita?)")
            elif np.median(s_arr) < 0.72 and float((s_arr < 0.8).mean()) >= 0.7:
                details.append("el cliente parece más delgado (¿sin negrita?)")
            sl = np.array(slant_d)
            if abs(float(np.median(sl))) > 0.2 and float((np.abs(sl) > 0.12).mean()) >= 0.7:
                details.append("distinta inclinación (¿cursiva?)")
        if details:
            diffs.append(Difference(
                category="font", subtype="tamano" if size_diff else "estilo",
                bbox=(int(sx0), int(sy0), max(1, int(sx1 - sx0)), max(1, int(sy1 - sy0))),
                severity="media" if abs(ratio - 1.0) > 2 * tol else "baja",
                message="Posible diferencia de fuente: " + "; ".join(details),
                expected=sp.text[:60], found=f"{sp.font.split('+')[-1]} {sp.size:.0f}pt"))
    return diffs, evaluated
