"""OCR del arte del cliente y comparación palabra por palabra con el texto del diseño."""
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import cv2
import numpy as np
import pytesseract
from rapidfuzz import fuzz

from .config import setup_tesseract
from .loaders import TextSpan
from .models import Difference


@dataclass
class Word:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    conf: float = 100.0

    @property
    def cy(self):
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def h(self):
        return self.bbox[3] - self.bbox[1]


@dataclass
class TextResult:
    differences: list[Difference] = field(default_factory=list)
    pairs: list[tuple[Word, Word]] = field(default_factory=list)  # (diseño, cliente) emparejadas
    matched: int = 0
    total: int = 0
    design_words: list[Word] = field(default_factory=list)
    client_words: list[Word] = field(default_factory=list)
    matched_design_keys: set[str] = field(default_factory=set)


class OcrUnavailable(RuntimeError):
    pass


def ocr_words(img: np.ndarray, cfg: dict) -> list[Word]:
    if not setup_tesseract(cfg):
        raise OcrUnavailable("Tesseract no está instalado. Instálalo con: winget install UB-Mannheim.TesseractOCR")
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    scale = 2.0 if img.shape[1] < 1500 else 1.0
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if th.mean() < 127:  # texto claro sobre fondo oscuro -> invertir
        th = 255 - th
    data = pytesseract.image_to_data(
        th, lang=cfg["ocr_lang"], config="--oem 1 --psm 11",
        output_type=pytesseract.Output.DICT)
    words = []
    for i, t in enumerate(data["text"]):
        t = (t or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not t or conf < 50:
            continue
        x, y, w, h = (data[k][i] / scale for k in ("left", "top", "width", "height"))
        words.append(Word(t, (x, y, x + w, y + h), conf))
    return words


def order_words(words: list[Word]) -> list[Word]:
    """Orden de lectura: líneas de arriba abajo, palabras de izquierda a derecha."""
    if not words:
        return []
    med_h = float(np.median([w.h for w in words])) or 10.0
    ws = sorted(words, key=lambda w: w.cy)
    lines: list[list[Word]] = []
    for w in ws:
        if lines:
            cur = lines[-1]
            mean_cy = sum(x.cy for x in cur) / len(cur)
            if abs(w.cy - mean_cy) <= 0.6 * med_h:
                cur.append(w)
                continue
        lines.append([w])
    out = []
    for ln in lines:
        out.extend(sorted(ln, key=lambda w: w.bbox[0]))
    return out


def layout_words(spans: list[TextSpan]) -> list[Word]:
    return [Word(t, tuple(b)) for sp in spans for t, b in sp.words]


_PUNCT = re.compile(r"[^\w]", re.UNICODE)


def strip_punct(t: str) -> str:
    return _PUNCT.sub("", t.replace("_", ""))


def word_key(t: str) -> str:
    return strip_punct(unicodedata.normalize("NFC", t)).lower()


def _bbox_xywh(b) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = b
    return int(round(x0)), int(round(y0)), max(1, int(round(x1 - x0))), max(1, int(round(y1 - y0)))


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _pair_diff(cw: Word, dw: Word) -> Difference:
    """Diferencia entre dos palabras emparejadas (cliente, diseño) con la misma clave o distinta."""
    bbox = _bbox_xywh(dw.bbox)
    if word_key(cw.text) == word_key(dw.text):
        if strip_punct(cw.text) == strip_punct(dw.text):
            sub, sev, name = "puntuacion", "baja", "Cambia la puntuación"
        else:
            sub, sev, name = "mayusculas", "baja", "Cambia el uso de mayúsculas"
    else:
        sub, sev, name = "cambiada", "alta", "Texto cambiado"
    return Difference(
        category="text", subtype=sub, bbox=bbox, severity=sev,
        message=f"{name}. Cliente dice: «{cw.text}» · Tu diseño dice: «{dw.text}»",
        expected=cw.text, found=dw.text)


def strip_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _maybe_pair_diff(cw: Word, dw: Word) -> Difference | None:
    """Como _pair_diff, pero si la única diferencia son tildes y el DISEÑO las tiene mientras la lectura del
    cliente no, es una limitación del OCR (pierde acentos con facilidad): no se reporta (devuelve None).
    Lo contrario (el diseño no tiene la tilde que el cliente sí muestra) sí es un error real."""
    kc, kd = word_key(cw.text), word_key(dw.text)
    if kc != kd and strip_accents(kc) == strip_accents(kd):
        acc_c = sum(a != b for a, b in zip(kc, strip_accents(kc)))
        acc_d = sum(a != b for a, b in zip(kd, strip_accents(kd)))
        if acc_d > 0 and acc_c == 0:
            return None
    d = _pair_diff(cw, dw)
    d.ocr_confidence = cw.conf
    return d


def _missing_diff(cw: Word) -> Difference:
    return Difference(
        category="text", subtype="faltante", bbox=_bbox_xywh(cw.bbox), severity="alta",
        message=f"Palabra faltante en tu diseño. Cliente dice: «{cw.text}» · Tu diseño dice: (nada)",
        expected=cw.text, found="", ocr_confidence=cw.conf)


def _extra_diff(dw: Word) -> Difference:
    return Difference(
        category="text", subtype="sobrante", bbox=_bbox_xywh(dw.bbox), severity="media",
        message=f"Palabra sobrante en tu diseño. Cliente dice: (nada) · Tu diseño dice: «{dw.text}»",
        expected="", found=dw.text)


def _pair_unequal(cs: list[Word], ds: list[Word]):
    """Empareja greedy por similitud dentro de un bloque 'replace' de distinto tamaño."""
    cands = []
    for i, c in enumerate(cs):
        for j, d in enumerate(ds):
            r = fuzz.ratio(word_key(c.text), word_key(d.text))
            if r >= 50:
                cands.append((r, i, j))
    cands.sort(reverse=True)
    used_c, used_d, pairs = set(), set(), []
    for _, i, j in cands:
        if i in used_c or j in used_d:
            continue
        used_c.add(i)
        used_d.add(j)
        pairs.append((i, j))
    left_c = [i for i in range(len(cs)) if i not in used_c]
    left_d = [j for j in range(len(ds)) if j not in used_d]
    return pairs, left_c, left_d


def compare_words(design_words: list[Word], client_words: list[Word]) -> TextResult:
    """El cliente (A) es lo que debería decir; el diseño (B) es lo que se corrige."""
    dws = [w for w in order_words(design_words) if word_key(w.text)]
    cws = [w for w in order_words(client_words) if word_key(w.text)]
    res = TextResult(design_words=dws, client_words=cws)
    dk = [word_key(w.text) for w in dws]
    ck = [word_key(w.text) for w in cws]
    sm = SequenceMatcher(None, ck, dk, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                res.pairs.append((dws[j], cws[i]))
                res.matched_design_keys.add(dk[j])
                if cws[i].text.strip(".,;:") == dws[j].text.strip(".,;:"):
                    res.matched += 1
                else:
                    res.differences.append(_pair_diff(cws[i], dws[j]))
        elif tag == "delete":
            res.differences.extend(_missing_diff(cws[i]) for i in range(i1, i2))
        elif tag == "insert":
            res.differences.extend(_extra_diff(dws[j]) for j in range(j1, j2))
        else:  # replace
            cs, ds = cws[i1:i2], dws[j1:j2]
            if len(cs) == len(ds):
                pairs, lc, ld = list(zip(range(len(cs)), range(len(ds)))), [], []
            else:
                pairs, lc, ld = _pair_unequal(cs, ds)
            for i, j in pairs:
                d = _maybe_pair_diff(cs[i], ds[j])
                if d is None:  # el OCR perdió una tilde: cuenta como coincidencia
                    res.matched += 1
                    res.pairs.append((ds[j], cs[i]))
                    res.matched_design_keys.add(word_key(ds[j].text))
                else:
                    res.differences.append(d)
            res.differences.extend(_missing_diff(cs[i]) for i in lc)
            res.differences.extend(_extra_diff(ds[j]) for j in ld)
    res.total = max(len(dws), len(cws))
    return res


def compare_text(design_words: list[Word], client_img: np.ndarray, cfg: dict) -> TextResult:
    client_words = ocr_words(client_img, cfg)
    return compare_words(design_words, client_words)
