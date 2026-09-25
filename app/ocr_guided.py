"""OCR guiado por el PDF del diseño.

El PDF dice dónde está cada línea de texto. En vez de leer toda la página con un umbral global, se recorta cada
línea del arte del cliente (ya alineado), se preprocesa localmente (canal de más contraste, umbral adaptativo
Sauvola, escala ~40 px por letra) y se lee con `--psm 7`. Después se hace una pasada de página completa sobre lo
que NO se leyó, para detectar texto que el cliente tiene y el diseño no.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytesseract
from rapidfuzz import fuzz
from skimage.filters import threshold_sauvola

from .compare_text import (OcrUnavailable, TextResult, Word, _missing_diff, compare_words, order_words, word_key)
from .config import setup_tesseract
from .loaders import TextSpan

TARGET_LETTER_PX = 60  # altura de la caja de una línea tras el reescalado
BORDER = 10


@dataclass
class Line:
    spans: list[TextSpan]
    words: list[Word]
    bbox: tuple[float, float, float, float]

    @property
    def h(self) -> float:
        return self.bbox[3] - self.bbox[1]


def lines_from_layout(spans: list[TextSpan]) -> list[Line]:
    groups: dict[tuple, list[TextSpan]] = {}
    for sp in spans:
        groups.setdefault(sp.line_id, []).append(sp)
    lines = []
    for sps in groups.values():
        words = [Word(t, tuple(b)) for sp in sps for t, b in sp.words]
        if not words:
            continue
        x0 = min(w.bbox[0] for w in words)
        y0 = min(w.bbox[1] for w in words)
        x1 = max(w.bbox[2] for w in words)
        y1 = max(w.bbox[3] for w in words)
        lines.append(Line(sps, words, (x0, y0, x1, y1)))
    return sorted(lines, key=lambda l: (round(l.bbox[1] / 4), l.bbox[0]))


# ---------------------------------------------------------------------------------- preprocesado
def best_channel(crop: np.ndarray) -> np.ndarray:
    """Canal con más contraste (no siempre la luminancia): gris, L de LAB o el mejor canal RGB."""
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)[:, :, 0]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    cands = [gray, lab, crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]]
    best, best_c = gray, -1.0
    for c in cands:
        lo, hi = np.percentile(c, (5, 95))
        if hi - lo > best_c:
            best, best_c = c, hi - lo
    return best


def binarize(chan: np.ndarray, method: str = "sauvola", k: float = 0.2) -> np.ndarray:
    """Devuelve una imagen 0/255 con texto oscuro sobre fondo claro."""
    if method == "otsu":
        _, th = cv2.threshold(chan, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        out = th
    else:
        win = max(15, (min(chan.shape[:2]) // 2) * 2 + 1)
        win = min(win, 51) | 1
        if min(chan.shape[:2]) < win:
            win = (min(chan.shape[:2]) // 2) * 2 - 1
        win = max(win, 3)
        th = threshold_sauvola(chan, window_size=win, k=k)
        out = ((chan > th) * 255).astype(np.uint8)
    if out.mean() < 127:  # fondo oscuro (texto claro) -> invertir
        out = 255 - out
    return out


def prep_crop(crop_rgb: np.ndarray, scale: float, method: str = "sauvola", channel: str = "best",
              k: float = 0.2, blur: float = 0.0) -> np.ndarray:
    chan = best_channel(crop_rgb) if channel == "best" else cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
    interp = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    chan = cv2.resize(chan, None, fx=scale, fy=scale, interpolation=interp)
    if blur > 0:
        chan = cv2.GaussianBlur(chan, (0, 0), blur)
    b = binarize(chan, method, k)
    return cv2.copyMakeBorder(b, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)


def _tess(img: np.ndarray, cfg: dict, psm: int, extra: str = ""):
    return pytesseract.image_to_data(
        img, lang=cfg["ocr_lang"], config=f"--oem 1 --psm {psm} {extra}".strip(),
        output_type=pytesseract.Output.DICT)


def _words_from_data(data, ox, oy, scale, min_conf=0) -> list[Word]:
    words = []
    for i, t in enumerate(data["text"]):
        t = (t or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not t or conf < min_conf:
            continue
        x, y, w, h = (data[k][i] for k in ("left", "top", "width", "height"))
        x0 = ox + (x - BORDER) / scale
        y0 = oy + (y - BORDER) / scale
        words.append(Word(t, (x0, y0, x0 + w / scale, y0 + h / scale), conf))
    return words


def _mean_conf(words: list[Word]) -> float:
    return float(np.mean([w.conf for w in words])) if words else 0.0


# ---------------------------------------------------------------------------------- lectura por línea
def line_zone(line: Line, lines: list[Line], quality: float, W: int, H: int,
              base: float = 0.25) -> tuple[int, int, int, int]:
    """Zona de recorte de una línea: 25% de margen (más si la alineación es mala) y, hacia los lados, todo el
    espacio libre (hasta 35% del ancho) para no cortar texto si el cliente usa una fuente más grande."""
    h = max(line.h, 8.0)
    slack = base + (0.5 * (1 - min(max(quality, 0.0), 1.0)) if quality < 0.9 else 0.0)
    left = right = slack * h
    lw = line.bbox[2] - line.bbox[0]
    free = 0.35 * lw
    for o in lines:
        if o is line:
            continue
        v = min(o.bbox[3], line.bbox[3]) - max(o.bbox[1], line.bbox[1])
        if v < 0.3 * min(o.h, line.h):
            continue  # no está en la misma banda vertical
        if o.bbox[0] >= line.bbox[2]:
            right_gap = o.bbox[0] - line.bbox[2]
            right = min(max(right, free), max(slack * h, 0.6 * right_gap)) if right_gap < free else max(right, free)
        elif o.bbox[2] <= line.bbox[0]:
            left_gap = line.bbox[0] - o.bbox[2]
            left = min(max(left, free), max(slack * h, 0.6 * left_gap)) if left_gap < free else max(left, free)
    if all(o is line or min(o.bbox[3], line.bbox[3]) - max(o.bbox[1], line.bbox[1]) < 0.3 * min(o.h, line.h)
           for o in lines):
        left = right = max(left, right, free)
    elif not any(o is not line and o.bbox[0] >= line.bbox[2]
                 and min(o.bbox[3], line.bbox[3]) - max(o.bbox[1], line.bbox[1]) >= 0.3 * min(o.h, line.h)
                 for o in lines):
        right = max(right, free)
    my = base * h
    return (max(0, int(line.bbox[0] - left)), max(0, int(line.bbox[1] - my)),
            min(W, int(line.bbox[2] + right)), min(H, int(line.bbox[3] + my)))


DEFAULT_TUNE = {"target_px": 60, "method": "sauvola", "k": 0.2, "blur": 0.0, "psm": 7, "margin": 0.25}


def read_line(img: np.ndarray, line: Line, cfg: dict, quality: float, extra: str = "",
              zone: tuple | None = None, tune: dict | None = None) -> tuple[list[Word], float]:
    t = {**DEFAULT_TUNE, **(tune or {})}
    H, W = img.shape[:2]
    h = max(line.h, 8.0)
    x0, y0, x1, y1 = zone or line_zone(line, [line], quality, W, H, t["margin"])
    crop = img[y0:y1, x0:x1]
    if crop.shape[0] < 4 or crop.shape[1] < 4:
        return [], 0.0
    scale = float(np.clip(t["target_px"] / h, 0.5, 4.0))
    expected = " ".join(w.text for w in line.words)
    other = "otsu" if t["method"] == "sauvola" else "sauvola"
    attempts = [(t["method"], "best", t["psm"], 1.0), (other, "gray", 7, 1.0), ("sauvola", "gray", 6, 1.3),
                (t["method"], "best", 7, 0.75)]
    best, best_key = ([], 0.0), None
    for k, (method, chan, psm, sm) in enumerate(attempts):
        img_p = prep_crop(crop, scale * sm, method, chan, t["k"], t["blur"])
        words = _words_from_data(_tess(img_p, cfg, psm, extra), x0, y0, scale * sm)
        conf = _mean_conf(words)
        sim = fuzz.ratio(" ".join(w.text for w in words).lower(), expected.lower()) if words else 0
        key = (round(conf / 5), sim)  # la similitud solo desempata
        if best_key is None or key > best_key:
            best, best_key = (words, conf), key
        if k == 0 and conf >= 60 and words:
            break
    return best


# ---------------------------------------------------------------------------------- pasada de página
def _fill_zones(img: np.ndarray, boxes) -> np.ndarray:
    out = img.copy()
    H, W = img.shape[:2]
    for x0, y0, x1, y1 in boxes:
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(W, int(x1)), min(H, int(y1))
        ring = np.concatenate([img[max(0, y0 - 3):y0, x0:x1].reshape(-1, 3), img[y1:y1 + 3, x0:x1].reshape(-1, 3)])
        bg = np.median(ring, axis=0) if ring.size else np.array([255, 255, 255])
        out[y0:y1, x0:x1] = bg
    return out


def ocr_page_adaptive(img: np.ndarray, cfg: dict, min_conf: float = 50, extra: str = "") -> list[Word]:
    """OCR de página completa con umbral adaptativo (mejor que Otsu global con fondos de color o degradados)."""
    if not setup_tesseract(cfg):
        raise OcrUnavailable("Tesseract no está instalado. Instálalo con: winget install UB-Mannheim.TesseractOCR")
    scale = 2.0 if img.shape[1] < 1500 else 1.0
    chan = best_channel(img)
    chan = cv2.resize(chan, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1 else chan
    b = binarize(chan, "sauvola")
    b = cv2.copyMakeBorder(b, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)
    return _words_from_data(_tess(b, cfg, 11, extra), 0, 0, scale, min_conf)


def _overlaps(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ah, by + bh) > max(ay, by)


_WIDE = [(1.0, "sauvola", "best", 7), (1.5, "sauvola", "gray", 7), (1.25, "otsu", "gray", 7), (0.8, "sauvola", "best", 7)]
_TIGHT = [(1.0, "sauvola", "best", 8), (1.5, "sauvola", "gray", 8), (2.0, "otsu", "gray", 8), (2.5, "sauvola", "best", 8)]


def _variant_hit(img: np.ndarray, bbox, target: str, cfg: dict, extra: str, wide: bool, variant) -> bool:
    H, W = img.shape[:2]
    x, y, w, h = bbox
    sm, method, chan, psm = variant
    px, py = (int(max(3 * h, 1.2 * w)), int(0.3 * h)) if wide else (int(0.35 * h), int(0.35 * h))
    x0, y0, x1, y1 = max(0, x - px), max(0, y - py), min(W, x + w + px), min(H, y + h + py)
    crop = img[y0:y1, x0:x1]
    if crop.shape[0] < 4 or crop.shape[1] < 4:
        return False
    base = float(np.clip(TARGET_LETTER_PX / max(h, 8), 0.5, 4.0))
    want = target.strip(".,;:")
    data = _tess(prep_crop(crop, base * sm, method, chan), cfg, psm, extra)
    for wd in _words_from_data(data, x0, y0, base * sm):
        cx = (wd.bbox[0] + wd.bbox[2]) / 2
        if wd.text.strip(".,;:") == want and (not wide or x - 0.6 * w <= cx <= x + 1.6 * w):
            return True
    return False


def reads_as_many(img: np.ndarray, items, cfg: dict, extra: str = "") -> list[bool]:
    """Para cada (bbox, texto) relee la zona con 8 variantes (con contexto y ajustada, distintos preprocesados y
    escalas) EN PARALELO. True si ALGUNA lectura independiente da el texto. No fuerza el resultado: si la imagen
    dice otra cosa, ninguna variante lo producirá."""
    tasks = [(i, True, v) for i in range(len(items)) for v in _WIDE] +             [(i, False, v) for i in range(len(items)) for v in _TIGHT]
    hits = [False] * len(items)

    def run(t):
        i, wide, v = t
        if hits[i]:
            return
        if _variant_hit(img, items[i][0], items[i][1], cfg, extra, wide, v):
            hits[i] = True

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(run, tasks))
    return hits


def reads_as(img: np.ndarray, bbox, target: str, cfg: dict, extra: str = "") -> bool:
    return reads_as_many(img, [(bbox, target)], cfg, extra)[0]


def is_tilde_missing(d) -> bool:
    """Diferencia que solo es una tilde: el cliente tiene acento y el diseño no."""
    if not d.expected or not d.found or d.expected == d.found:
        return False
    from .compare_text import strip_accents
    return (strip_accents(d.expected.lower()) == strip_accents(d.found.lower())
            and strip_accents(d.found) == d.found and strip_accents(d.expected) != d.expected)


def verify_diffs(img: np.ndarray, diffs, cfg: dict, extra: str = ""):
    """Confirma con relecturas los errores de texto dudosos. Devuelve (diferencias, [diferencias verificadas])."""
    cand = [d for d in diffs if d.category == "text" and d.subtype in ("cambiada", "sobrante", "mayusculas", "puntuacion")
            and d.found and not is_tilde_missing(d)]  # diseño SIN tilde y cliente CON: las relecturas pierden acentos
    hits = reads_as_many(img, [(d.bbox, d.found) for d in cand], cfg, extra) if cand else []
    verified = [d for d, h in zip(cand, hits) if h]
    ids = {id(d) for d in verified}
    keep = [d for d in diffs if id(d) not in ids]
    vbox = [d.bbox for d in verified]
    # basura del OCR que solapa una palabra ya verificada
    keep = [d for d in keep if not (d.subtype == "faltante" and any(_overlaps(d.bbox, b) for b in vbox))]
    return keep, verified


def _next_to_line(w: Word, ln: "Line") -> bool:
    """Palabra pegada al principio o al final de la línea del diseño (misma banda vertical, a menos de ~2 alturas)."""
    h = max(ln.h, 8.0)
    v = min(w.bbox[3], ln.bbox[3]) - max(w.bbox[1], ln.bbox[1])
    if v < 0.5 * min(w.h, ln.h):
        return False
    gap = max(w.bbox[0] - ln.bbox[2], ln.bbox[0] - w.bbox[2])
    return gap < 2.5 * h


def _alnum_ok(t: str) -> bool:
    return len(t) >= 2 and sum(c.isalnum() for c in t) >= max(2, len(t) * 0.6)


def compare_guided(spans: list[TextSpan], client: np.ndarray, cfg: dict, quality: float,
                   extra: str = "", tune: dict | None = None) -> TextResult:
    if not setup_tesseract(cfg):
        raise OcrUnavailable("Tesseract no está instalado. Instálalo con: winget install UB-Mannheim.TesseractOCR")
    lines = lines_from_layout(spans)
    H, W = client.shape[:2]

    with ThreadPoolExecutor(max_workers=4) as ex:
        base = float((tune or {}).get("margin", 0.25))
        zones_px = [line_zone(ln, lines, quality, W, H, base) for ln in lines]
        reads = list(ex.map(lambda a: read_line(client, a[0], cfg, quality, extra, a[1], tune),
                            zip(lines, zones_px)))

    res = TextResult()
    zones = []
    all_client: list[Word] = []
    design_keys: list[tuple[str, float, float, float]] = []
    for ln, (cwords, _conf) in zip(lines, reads):
        # el espacio extra de los lados solo admite palabras muy claras (evita basura de logos y formas)
        hh = max(ln.h, 8.0)
        cwords = [w for w in cwords
                  if (ln.bbox[0] - 0.3 * hh <= (w.bbox[0] + w.bbox[2]) / 2 <= ln.bbox[2] + 0.3 * hh)
                  or (_alnum_ok(w.text) and len(w.text) >= 3 and (w.conf >= 85 or (w.conf >= 70 and _next_to_line(w, ln))))]
        tr = compare_words(ln.words, cwords)
        res.differences += tr.differences
        res.pairs += tr.pairs
        res.matched += tr.matched
        res.total += tr.total
        res.matched_design_keys |= tr.matched_design_keys
        res.design_words += tr.design_words
        all_client += tr.client_words
        h = max(ln.h, 8.0)
        zones.append(zones_px[len(zones)])
        for w in ln.words:
            design_keys.append((word_key(w.text), *w.bbox[:2], h))

    # texto que el cliente tiene y el diseño no: OCR de página sobre lo no leído
    masked = _fill_zones(client, zones)
    extras = [w for w in ocr_page_adaptive(masked, cfg, min_conf=70, extra=extra) if _alnum_ok(w.text)]
    for w in order_words(extras):
        k = word_key(w.text)
        if not k:
            continue
        cx, cy = (w.bbox[0] + w.bbox[2]) / 2, (w.bbox[1] + w.bbox[3]) / 2
        # restos desplazados de una línea ya leída: misma palabra del diseño cerca
        if any(dk == k and abs(cx - x) < 6 * h and abs(cy - y) < 2.5 * h for dk, x, y, h in design_keys):
            continue
        res.differences.append(_missing_diff(w))
        all_client.append(w)
        res.total += 1
    res.differences, verified = verify_diffs(client, res.differences, cfg, extra)
    for d in verified:  # releído y coincide con el diseño: era un error del OCR
        res.matched += 1
        res.matched_design_keys.add(word_key(d.found))
    # palabras del cliente que no están en el diseño: exigir lectura muy segura
    res.differences = [d for d in res.differences
                       if not (d.subtype == "faltante" and ((d.ocr_confidence or 100) < 70 or len(d.expected or "") < 2))]
    res.client_words = order_words(all_client)
    return res


def read_region(img: np.ndarray, bbox, cfg: dict, extra: str = "") -> list[Word]:
    """Lee el texto de una zona suelta (p. ej. una región visual sobre papel en blanco del diseño)."""
    H, W = img.shape[:2]
    x, y, w, h = bbox
    pad = int(0.25 * h)
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    crop = img[y0:y1, x0:x1]
    if crop.shape[0] < 6 or crop.shape[1] < 6 or h > 400:
        return []
    scale = float(np.clip(TARGET_LETTER_PX / max(h * 0.7, 8), 0.5, 4.0))
    best: list[Word] = []
    best_conf = 0.0
    for method, chan, psm in (("sauvola", "best", 7), ("otsu", "gray", 7), ("sauvola", "gray", 6)):
        words = [wd for wd in _words_from_data(_tess(prep_crop(crop, scale, method, chan), cfg, psm, extra),
                                               x0, y0, scale, 60) if _alnum_ok(wd.text)]
        conf = _mean_conf(words)
        if words and conf > best_conf:
            best, best_conf = words, conf
    return best if best_conf >= 70 else []
