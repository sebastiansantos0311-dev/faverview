"""Diferencias de color con Delta E (CIEDE2000) sobre el espacio LAB."""
import cv2
import numpy as np
from skimage.color import deltaE_ciede2000, rgb2lab

from .loaders import TextSpan
from .models import Difference

CELL = 32


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def delta_e(rgb1, rgb2) -> float:
    a = rgb2lab(np.array(rgb1, dtype=np.float64).reshape(1, 1, 3) / 255.0)
    b = rgb2lab(np.array(rgb2, dtype=np.float64).reshape(1, 1, 3) / 255.0)
    return float(deltaE_ciede2000(a, b)[0, 0])


def delta_e_hex(h1: str, h2: str) -> float:
    return delta_e(hex_to_rgb(h1), hex_to_rgb(h2))


def ink_color(img: np.ndarray, bbox, pad: int = 3):
    """Color mediano de la 'tinta' (píxeles más alejados del fondo local) dentro del bbox.
    Devuelve (rgb, bg_rgb) o None si no hay tinta suficiente."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in bbox)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    ex0, ey0, ex1, ey1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    ring_mask = np.ones((ey1 - ey0, ex1 - ex0), bool)
    ring_mask[y0 - ey0:y1 - ey0, x0 - ex0:x1 - ex0] = False
    region = img[ey0:ey1, ex0:ex1]
    ring = region[ring_mask]
    if ring.size < 30:
        ring = region.reshape(-1, 3)
    bg = np.median(ring.reshape(-1, 3), axis=0)
    crop = img[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
    dist = np.linalg.norm(crop - bg, axis=1)
    if dist.max() < 40:
        return None
    n = max(3, int(len(dist) * 0.25))
    idx = np.argsort(dist)[-n:]
    if dist[idx].min() < 25:
        idx = idx[dist[idx] >= 25]
        if len(idx) < 3:
            return None
    return np.median(crop[idx], axis=0), bg


def text_color_diffs(design: np.ndarray, client: np.ndarray, spans: list[TextSpan],
                     tol: float, skip_boxes: list[tuple[int, int, int, int]] | None = None):
    """Compara el color de tinta de cada span en el diseño vs el cliente."""
    diffs: list[Difference] = []
    skip_boxes = skip_boxes or []
    for sp in spans:
        x0, y0, x1, y1 = sp.bbox
        if _overlaps_any((x0, y0, x1 - x0, y1 - y0), skip_boxes, 0.0):
            continue
        cink = ink_color(client, sp.bbox)
        dink = ink_color(design, sp.bbox)
        if cink is None or dink is None:
            continue
        # Se decide con la misma medición en ambas imágenes (cancela el efecto de antialiasing)
        cvec, bgc = cink[0], cink[1]
        # cliente borroso/reducido: la tinta se diluye hacia el fondo; se compensa el contraste
        sh_c, sh_d = _sharp(client, sp.bbox), _sharp(design, sp.bbox)
        nd, nc = np.linalg.norm(dink[0] - dink[1]), np.linalg.norm(cvec - bgc)
        if sh_d > 1e-6 and sh_c / sh_d < 0.6 and 0 < nc < nd:
            cvec = bgc + (cvec - bgc) * (nd / nc)
            cvec = np.clip(cvec, 0, 255)
        de = delta_e(cvec, dink[0])
        # el texto fino pierde contraste al re-muestrear: se tolera más en cuerpos pequeños
        tol_sp = tol * max(1.0, 24.0 / max(sp.size, 1.0))
        if de > tol_sp:
            diffs.append(Difference(
                category="color", subtype="texto",
                bbox=(int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0))),
                severity="alta" if de > 3 * tol else "media",
                message=f"Color de texto distinto (ΔE {de:.1f}): «{sp.text[:40]}»",
                expected=sp.text[:60],
                expected_hex=rgb_to_hex(cink[0]), found_hex=rgb_to_hex(dink[0]),
                delta_e=round(de, 1)))
    return diffs


def _sharp(img: np.ndarray, bbox, pad: int = 4) -> float:
    H, W = img.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in bbox)
    crop = img[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
    return float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()) if crop.size else 0.0


def _overlaps_any(box, boxes, min_frac=0.5) -> bool:
    x, y, w, h = box
    area = max(1.0, w * h)
    for bx, by, bw, bh in boxes:
        iw = min(x + w, bx + bw) - max(x, bx)
        ih = min(y + h, by + bh) - max(y, by)
        if iw > 0 and ih > 0 and iw * ih / area > min_frac:
            return True
    return False


def _cell_medians(img: np.ndarray, hc: int, wc: int) -> np.ndarray:
    c = img[:hc * CELL, :wc * CELL].reshape(hc, CELL, wc, CELL, 3)
    return np.median(c, axis=(1, 3))


def grid_color_diffs(design: np.ndarray, client: np.ndarray, text_boxes: list, tol: float,
                     valid: np.ndarray | None = None):
    """Compara el color mediano por celdas de 32x32 y une celdas vecinas.
    Devuelve (diferencias, área_con_error_px)."""
    H, W = design.shape[:2]
    hc, wc = H // CELL, W // CELL
    if hc == 0 or wc == 0:
        return [], 0
    md = _cell_medians(design, hc, wc)
    mc = _cell_medians(client, hc, wc)
    lab_d = rgb2lab(md / 255.0)
    lab_c = rgb2lab(mc / 255.0)
    de = deltaE_ciede2000(lab_d, lab_c)

    text_mask = np.zeros((H, W), np.uint8)
    for x, y, w, h in text_boxes:
        cv2.rectangle(text_mask, (int(x), int(y)), (int(x + w), int(y + h)), 1, -1)
    tm = text_mask[:hc * CELL, :wc * CELL].reshape(hc, CELL, wc, CELL).mean(axis=(1, 3))

    ok = (tm < 0.1)
    # celdas con borde (mucha variación interna): su color mediano es inestable; se ignoran
    sd = design[:hc * CELL, :wc * CELL].reshape(hc, CELL, wc, CELL, 3).astype(np.float32).std(axis=(1, 3)).max(axis=2)
    ok &= sd < 25
    if valid is not None:  # celdas con relleno de la alineación (sin contenido del cliente) no cuentan
        vm = valid[:hc * CELL, :wc * CELL].reshape(hc, CELL, wc, CELL).mean(axis=(1, 3))
        ok &= vm > 0.98
    bad = ((de > tol) & ok).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bad, connectivity=8)
    diffs, area = [], 0
    for i in range(1, n):
        cx, cy, cw, ch, cnt = stats[i]
        cells = labels == i
        mean_de = float(de[cells].mean())
        if cnt < 2 and mean_de < 2 * tol:
            continue
        exp = mc[cells].mean(axis=0)
        fnd = md[cells].mean(axis=0)
        area += int(cnt) * CELL * CELL
        diffs.append(Difference(
            category="color", subtype="zona",
            bbox=(int(cx * CELL), int(cy * CELL), int(cw * CELL), int(ch * CELL)),
            severity="alta" if mean_de > 3 * tol else "media",
            message=f"Color distinto en la zona (ΔE {mean_de:.1f})",
            expected_hex=rgb_to_hex(exp), found_hex=rgb_to_hex(fnd), delta_e=round(mean_de, 1)))
    return diffs, area
