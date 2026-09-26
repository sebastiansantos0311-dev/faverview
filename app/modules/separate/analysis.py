"""Análisis de placas (S2 §6.3): densitómetro, TAC, cobertura por tinta y chequeos de separación."""
from dataclasses import dataclass

import cv2
import numpy as np
import pikepdf
import pymupdf

from app.core import inks as inkmod
from app.core.units import pt_to_mm
from app.modules.separate.pdf_inks import PAINT_FILL, PAINT_STROKE, PAINT_TEXT, _Walker
from app.modules.separate.pdf_render import Plates

# límites de TAC (%) por perfil de impresión; el usuario puede indicar cualquier valor
TAC_PROFILES = {"offset": 300, "flexo": 280, "digital": 320, "papel_prensa": 240}
COUNTED_KINDS = ("process", "spot")   # el blanco, el barniz y las tintas técnicas no suman al TAC


def coverage_pct(plates: Plates) -> dict[str, float]:
    """% del área de la página cubierto por cada tinta (para estimar el consumo)."""
    return {n: round(plates.pct(n), 3) for n in plates.names}


def probe(plates: Plates, x: float, y: float, radius: int = 3) -> dict:
    """Densitómetro: % de cada tinta y TAC en un radio de `radius` px alrededor de (x, y) (px de la placa)."""
    x0, x1 = max(0, int(x) - radius), min(plates.width, int(x) + radius + 1)
    y0, y1 = max(0, int(y) - radius), min(plates.height, int(y) + radius + 1)
    if x1 <= x0 or y1 <= y0:
        return {"fuera": True, "tintas": {}, "tac": 0.0}
    vals = {n: round(float(plates.arrays[n][y0:y1, x0:x1].mean()) / 255 * 100, 1) for n in plates.names}
    return {"fuera": False, "tintas": vals, "tac": round(sum(vals.values()), 1)}


def tac_map(plates: Plates, meta: dict | None = None) -> np.ndarray:
    """Mapa de cobertura total (%) sumando las tintas de proceso y directas."""
    meta = meta or {}
    acc = np.zeros((plates.height, plates.width), np.float32)
    for n in plates.names:
        kind = (meta.get(n) or {}).get("tipo", "process" if n in ("Cyan", "Magenta", "Yellow", "Black") else "spot")
        if kind in COUNTED_KINDS:
            acc += plates.arrays[n].astype(np.float32)
    return acc / 255.0 * 100.0


def tac_stats(tac: np.ndarray) -> dict:
    return {"max": round(float(tac.max()), 1), "p995": round(float(np.percentile(tac, 99.5)), 1),
            "media": round(float(tac.mean()), 2)}


def tac_regions(tac: np.ndarray, limit: float, dpi: float, min_mm2: float = 1.0) -> list[dict]:
    """Zonas donde el TAC supera el límite (recuadros como en Comparar)."""
    mask = (tac > limit).astype(np.uint8) * 255
    k = max(3, int(dpi / 50) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    px_mm = 25.4 / dpi
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w * h * px_mm * px_mm < min_mm2:
            continue
        out.append({"bbox": [x, y, w, h], "max": round(float(tac[y:y + h, x:x + w].max()), 1)})
    return sorted(out, key=lambda r: -r["max"])


def tac_heatmap(tac: np.ndarray, limit: float) -> np.ndarray:
    """PNG sRGB: gris = cobertura, rojo = por encima del límite."""
    g = np.clip(255 - tac / max(limit, 1) * 200, 0, 255).astype(np.uint8)
    img = np.stack([g, g, g], axis=-1)
    over = tac > limit
    img[over] = (220, 30, 30)
    return img


# ---------------------------------------------------------------- chequeos
@dataclass
class Finding:
    id: str
    severidad: str          # error | advertencia | info
    mensaje: str
    bbox: list | None = None   # [x, y, w, h] en px de la placa (None = de toda la página)
    pagina: int = 1

    def to_dict(self) -> dict:
        return {"id": self.id, "severidad": self.severidad, "mensaje": self.mensaje, "bbox": self.bbox, "pagina": self.pagina}


def _plate_bbox(plates: Plates, name: str, thr: int = 8) -> list | None:
    ys, xs = np.where(plates.arrays[name] > thr)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]


def _text_spans(pdf_path, page: int, dpi: float):
    doc = pymupdf.open(pdf_path)
    try:
        pg = doc[page]
        s = dpi / 72.0
        ox, oy = pg.cropbox.x0, pg.cropbox.y0
        for b in pg.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    if sp["text"].strip():
                        x0, y0, x1, y1 = sp["bbox"]
                        yield sp["size"], sp["text"], [int((x0 - ox) * s), int((y0 - oy) * s),
                                                       max(1, int((x1 - x0) * s)), max(1, int((y1 - y0) * s))]
    finally:
        doc.close()


def _region(plates, bbox):
    x, y, w, h = bbox
    return slice(max(0, y), min(plates.height, y + h)), slice(max(0, x), min(plates.width, x + w))


def check_text(plates: Plates, pdf_path, page: int, rich_pt: float = 12.0, small_pt: float = 6.0) -> list[Finding]:
    """Negro enriquecido en texto pequeño y texto diminuto en más de una tinta (problemas de registro)."""
    out: list[Finding] = []
    black = plates.arrays.get("Black")
    for size, text, bbox in _text_spans(pdf_path, page, plates.dpi):
        ys, xs = _region(plates, bbox)
        if size < rich_pt and black is not None:
            k = black[ys, xs] >= 150
            if k.sum() >= 4:
                cmy = sum(plates.arrays[n][ys, xs][k].mean() / 255 * 100 for n in ("Cyan", "Magenta", "Yellow") if n in plates.arrays)
                if cmy > 20:
                    out.append(Finding("negro_enriquecido", "advertencia",
                                       f"Negro enriquecido en texto pequeño ({size:.0f} pt): «{text[:30]}». Usa 100 % K para evitar problemas de registro.", bbox))
        if size < small_pt:
            cover = np.stack([plates.arrays[n][ys, xs] for n in plates.names
                              if (n in ("Cyan", "Magenta", "Yellow", "Black") or True)], axis=-1)
            mask = cover.max(axis=-1) > 80
            if mask.sum() >= 4:
                n_inks = int(((cover[mask].mean(axis=0) / 255) > 0.25).sum())
                if n_inks >= 2:
                    out.append(Finding("texto_pequeno_multitinta", "error",
                                       f"Texto de {size:.1f} pt en {n_inks} tintas: «{text[:30]}». Un pequeño desajuste de registro lo hará ilegible.", bbox))
    return out


def scan_overprint(pdf_path, page: int, inventory_inks) -> list[dict]:
    """Recorre el contenido y anota, por cada pintado con una tinta directa, si estaba en sobreimpresión."""
    events: list[dict] = []
    w = _Walker()
    with pikepdf.open(str(pdf_path)) as pdf:
        pg = pdf.pages[page].obj
        stack_forms: set = set()

        def run(obj, res):
            res = res if res is not None else pikepdf.Dictionary()
            try:
                ops = pikepdf.parse_content_stream(obj)
            except Exception:
                return
            st = {"fill": ("DeviceGray", []), "stroke": ("DeviceGray", []), "op": False, "OP": False}
            saved = []
            for operands, op in ops:
                o = str(op)
                if o == "q":
                    saved.append(dict(st))
                elif o == "Q" and saved:
                    st = saved.pop()
                elif o == "gs":
                    egs = (res.get("/ExtGState") or {}).get(operands[0])
                    if egs is not None:
                        if "/op" in egs:
                            st["op"] = bool(egs["/op"])
                        if "/OP" in egs:
                            st["OP"] = bool(egs["/OP"])
                            if "/op" not in egs:
                                st["op"] = bool(egs["/OP"])   # por la especificación, OP aplica también a op si no hay op
                elif o in ("cs", "CS"):
                    st["fill" if o == "cs" else "stroke"] = w.describe_cs(operands[0], res)
                elif o in ("g", "G", "rg", "RG", "k", "K"):
                    kind = {"g": "DeviceGray", "rg": "DeviceRGB", "k": "DeviceCMYK"}[o.lower()]
                    st["fill" if o.islower() else "stroke"] = (kind, [])
                elif o in PAINT_FILL | PAINT_STROKE | PAINT_TEXT:
                    targets = []
                    if o in PAINT_FILL or o in PAINT_TEXT:
                        targets.append((st["fill"], st["op"]))
                    if o in PAINT_STROKE:
                        targets.append((st["stroke"], st["OP"]))
                    for (t, inks), ov in targets:
                        for ink in inks:
                            if ink is not None:
                                events.append({"norm": ink.norm, "kind": ink.kind, "name": ink.name, "overprint": ov})
                elif o == "Do":
                    xo = (res.get("/XObject") or {}).get(operands[0])
                    if xo is not None and str(xo.get("/Subtype")) == "/Form" and xo.objgen not in stack_forms:
                        stack_forms.add(xo.objgen)
                        run(xo, xo.get("/Resources"))
                        stack_forms.discard(xo.objgen)

        run(pg, pg.get("/Resources"))
    return events


def check_overprint(plates: Plates, pdf_path, page: int, inv, meta: dict | None = None) -> list[Finding]:
    """Blanco/barniz/tintas técnicas y su sobreimpresión; objetos en color de registro."""
    out: list[Finding] = []
    seen = {}
    for e in scan_overprint(pdf_path, page, inv.inks):
        seen.setdefault(e["norm"], []).append(e)
    for norm, evs in seen.items():
        ink = evs[0]
        name, kind = ink["name"], ink["kind"]
        knock = any(not e["overprint"] for e in evs)
        over = any(e["overprint"] for e in evs)
        plate = next((n for n in plates.names if inkmod.normalize_name(n) == norm), None)
        bbox = _plate_bbox(plates, plate) if plate else None
        if kind == "varnish" and knock:
            out.append(Finding("barniz_knockout", "error", f"El barniz «{name}» está en knockout: quitaría las tintas de debajo. Debe sobreimprimir.", bbox))
        if kind == "white" and over:
            out.append(Finding("blanco_sobreimpreso", "advertencia",
                               f"El blanco «{name}» está sobreimpreso: no taparía nada y desaparecería. Suele ir en knockout.", bbox))
        if kind == "technical" and norm != "ALL" and knock:
            out.append(Finding("tecnica_sin_sobreimpresion", "error",
                               f"La tinta técnica «{name}» no está en sobreimpresión: se imprimiría y borraría lo de debajo.", bbox))
        if norm == "ALL":
            out.append(Finding("registro_en_arte", "advertencia",
                               "Hay objetos en color de registro (All): aparecerán en todas las placas. Debe usarse solo en marcas.", bbox))
    return out


def check_spaces(inv) -> list[Finding]:
    out = []
    for k, label in (("DeviceRGB", "RGB"), ("ICC-RGB", "RGB (ICC)"), ("Lab", "Lab"), ("DeviceGray", None)):
        if inv.process_used.get(k) and label:
            out.append(Finding("espacio_sin_convertir", "advertencia",
                               f"Hay {inv.process_used[k]} objeto(s) en {label} sin convertir a las tintas de impresión: el resultado dependerá de la conversión del RIP."))
    return out


def check_thin_lines(plates: Plates, pdf_path, page: int, min_mm: float = 0.1) -> list[Finding]:
    """Líneas más finas que `min_mm` en varias tintas a la vez."""
    out = []
    doc = pymupdf.open(pdf_path)
    try:
        pg = doc[page]
        s = plates.dpi / 72.0
        ox, oy = pg.cropbox.x0, pg.cropbox.y0
        for d in pg.get_drawings():
            w = d.get("width")
            if not w or d.get("type") not in ("s", "fs") or pt_to_mm(w) >= min_mm:
                continue
            r = d["rect"]
            bbox = [int((r.x0 - ox) * s) - 2, int((r.y0 - oy) * s) - 2, max(3, int(r.width * s) + 4), max(3, int(r.height * s) + 4)]
            ys, xs = _region(plates, bbox)
            n = sum(1 for nm in plates.names if plates.arrays[nm][ys, xs].max() / 255 > 0.2)
            if n >= 2:
                out.append(Finding("linea_fina_multitinta", "advertencia",
                                   f"Línea de {pt_to_mm(w):.3f} mm en {n} tintas (mínimo recomendado {min_mm} mm).", bbox))
    finally:
        doc.close()
    return out[:50]


def run_checks(plates: Plates, pdf_path, page: int, inv, meta: dict | None = None, tac_limit: float = 300.0,
               min_line_mm: float = 0.1) -> list[Finding]:
    found: list[Finding] = []
    for r in tac_regions(tac_map(plates, meta), tac_limit, plates.dpi):
        found.append(Finding("tac", "error", f"Cobertura total {r['max']:.0f} % (límite {tac_limit:g} %).", r["bbox"]))
    found += check_text(plates, pdf_path, page)
    found += check_overprint(plates, pdf_path, page, inv, meta)
    found += check_spaces(inv)
    found += check_thin_lines(plates, pdf_path, page, min_line_mm)
    for f in found:
        f.pagina = page + 1
    return found
