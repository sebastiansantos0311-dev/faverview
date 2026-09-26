"""Pipeline del vectorizador (S4 v1 + S5 v2): preprocess → quantize → regions → boundaries → fit → geometría → export."""
import time
from dataclasses import dataclass, field

import numpy as np

from app.core import colorscience as cs
from app.modules.separate import raster
from app.modules.vectorize import boundaries, fit, geometry, preprocess, quantize, regions
from app.modules.vectorize.fit import seg_points

PRESETS = {
    "logo": {"k_max": 6, "merge_de": 8, "fit_tol": 0.7, "denoise": 1.0, "min_detail_mm": 0.15},
    "linea": {"k_max": 2, "bn": True, "fit_tol": 0.7, "denoise": 0.5, "min_detail_mm": 0.1},
    "ilustracion": {"k_max": 10, "merge_de": 5, "fit_tol": 0.9, "denoise": 1.0, "min_detail_mm": 0.15},
    "escaneo": {"k_max": 4, "merge_de": 8, "fit_tol": 1.0, "denoise": 1.5, "min_detail_mm": 0.2, "bn": False},
    "foto": {"k_max": 12, "merge_de": 3, "fit_tol": 1.2, "denoise": 1.0, "min_detail_mm": 0.3},
}


@dataclass
class VectorResult:
    width: float
    height: float
    dpi: float | None
    palette: list
    regions: list
    stats: dict = field(default_factory=dict)
    mode: str = "sin_solapes"
    source_scale: float = 1.0
    labels: np.ndarray | None = None
    opts: dict = field(default_factory=dict)          # opciones de trazado (para volver a trazar tras editar)
    strokes: list = field(default_factory=list)       # [{label, color, segs, width}]
    text_zones: list = field(default_factory=list)
    texts: list = field(default_factory=list)         # texto real que reemplaza a zonas (modo «reemplazar»)
    symmetry: str | None = None
    work: np.ndarray | None = None                   # imagen de trabajo (escalada y limpia) para volver a trazar zonas


def _loop_bbox(loop):
    p = np.vstack([seg_points(s, 6) for s in loop.segs])
    return p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()


def trace(labels, pal, *, fit_tol=0.8, corner_angle=60.0, smooth=1.6, scale=1.0, prims=False, clean=False, mode="sin_solapes",
          strokes=False):
    """Del mapa de etiquetas a regiones con fronteras compartidas."""
    chains = boundaries.build_chains(labels)
    fitted = []
    for c in chains:
        if c.closed:
            fitted.append(fit.fit_closed(c.pts, fit_tol * scale, corner_angle, smooth, scale, prims))
        else:
            fitted.append(fit.fit_polyline(c.pts, fit_tol * scale, corner_angle, smooth, scale, prims))
    if clean:
        fitted = geometry.straighten(chains, fitted, 2.0, 1.5 * scale)
    fitted = geometry.dedupe_segments(fitted)
    meta = {i: (cs.lab_to_hex(ink.lab), tuple(ink.lab)) for i, ink in enumerate(pal)}
    regs = regions.assemble(chains, fitted, meta)
    stroke_list = []
    if strokes:
        for s in geometry.find_strokes(labels, pal):
            segs = geometry.stroke_segments(s["pts"], fit_tol * scale, corner_angle, smooth, scale)
            stroke_list.append({"label": s["label"], "color": meta[s["label"]][0], "lab": meta[s["label"]][1], "segs": segs, "width": s["width"]})
        drop = {s["label"] for s in stroke_list}
        regs = [r for r in regs if r.label not in drop]
    regs = sorted(regs, key=lambda r: -r.filled_area())
    return regs, stroke_list


def vectorize(rgb: np.ndarray, dpi: float | None = None, *, preset: str | None = None, palette=None, k_max: int = 8,
              merge_de: float = 6.0, min_detail_mm: float = 0.15, fit_tol: float = 0.8, corner_angle: float = 60.0,
              smooth: float = 1.6, denoise: float = 1.0, bn: bool = False, bn_threshold: int | None = None,
              mode: str = "sin_solapes", upscale: bool = True, primitives: bool = False, geometria_limpia: bool = False,
              simetria: bool = False, trazos: bool = False, engrosar_mm: float = 0.0, texto: str = "normal",
              fuente: str = "Arial") -> VectorResult:
    """Vectoriza `rgb` en regiones de color con fronteras compartidas. Coordenadas en px de la imagen de trabajo.
    v2: `primitives` (arcos/círculos/elipses), `geometria_limpia` (enderezado), `simetria`, `trazos` (líneas con grosor),
    `engrosar_mm` (detalles mínimos) y `texto` = normal | marcar | reemplazar."""
    t0 = time.time()
    p = {**PRESETS.get(preset or "", {})}
    k_max = p.get("k_max", k_max); merge_de = p.get("merge_de", merge_de); fit_tol = p.get("fit_tol", fit_tol)
    denoise = p.get("denoise", denoise); bn = p.get("bn", bn); min_detail_mm = p.get("min_detail_mm", min_detail_mm)
    scale = 1.0
    work = rgb
    if upscale:
        work, scale = preprocess.upscale_if_small(rgb)
    zones = geometry.detect_text(work) if texto in ("marcar", "reemplazar") else []
    if bn:
        work = preprocess.binarize(work, bn_threshold)
    else:
        work = preprocess.denoise(work, denoise)
    wdpi = dpi * scale if dpi else None
    min_px = 4
    if wdpi and min_detail_mm:
        min_px = max(4, int(round((min_detail_mm / 25.4 * wdpi) ** 2)))
    labels, pal = quantize.quantize(work, wdpi, palette, k_max, merge_de, min_px, int(round(1.5 * scale)) if scale > 1 else 2)
    if engrosar_mm and wdpi:
        labels = geometry.thicken_thin(labels, engrosar_mm / 25.4 * wdpi)
    sym = None
    if simetria:
        labels, sym = geometry.symmetrize(labels)
    opts = dict(fit_tol=fit_tol, corner_angle=corner_angle, smooth=smooth, scale=scale, prims=primitives,
                clean=geometria_limpia, mode=mode, strokes=trazos)
    regs, strokes = trace(labels, pal, **opts)
    texts = []
    if texto == "reemplazar" and zones:
        regs, texts = _replace_text(regs, zones, work, fuente)
    nodes = sum(len(l.segs) for r in regs for l in r.loops) + sum(len(s["segs"]) for s in strokes)
    stats = {"trazados": sum(len(r.loops) for r in regs) + len(strokes), "nodos": nodes, "colores": len(pal),
             "segundos": round(time.time() - t0, 2), "escala": scale}
    if sym:
        stats["simetria"] = sym
    if zones:
        stats["zonas_texto"] = len(zones)
    h, w = labels.shape
    return VectorResult(w, h, wdpi, pal, regs, stats, mode, scale, labels, opts, strokes, zones, texts, sym, work)


def _replace_text(regs, zones, work, font):
    """Quita los trazados de primer plano contenidos en una zona de texto y los sustituye por texto real."""
    texts = []
    for z in zones:
        x0, y0, x1, y1 = z["x"] - 2, z["y"] - 2, z["x"] + z["w"] + 2, z["y"] + z["h"] + 2
        inside = 0
        for r in regs[1:]:                                 # regs[0] es el fondo (mayor área)
            keep = []
            for l in r.loops:
                bx0, by0, bx1, by1 = _loop_bbox(l)
                if bx0 >= x0 and by0 >= y0 and bx1 <= x1 and by1 <= y1:
                    inside += 1
                else:
                    keep.append(l)
            r.loops = keep
        if inside:
            patch = work[max(z["y"], 0):z["y"] + z["h"], max(z["x"], 0):z["x"] + z["w"]].reshape(-1, 3)
            col = patch[np.argmin(patch.sum(1))] if len(patch) else np.zeros(3)
            texts.append({"x": z["x"], "y": z["y"] + z["h"] * 0.82, "size": z["h"] * 0.95, "text": z["text"], "font": font,
                          "color": "#%02x%02x%02x" % tuple(int(v) for v in col)})
    return [r for r in regs if r.loops], texts


def retrace(res: VectorResult, labels: np.ndarray, pal: list) -> VectorResult:
    """Vuelve a trazar tras una edición del mapa de etiquetas (fusionar, borrar, recolorear, zona)."""
    t0 = time.time()
    regs, strokes = trace(labels, pal, **res.opts)
    nodes = sum(len(l.segs) for r in regs for l in r.loops) + sum(len(s["segs"]) for s in strokes)
    stats = dict(res.stats, trazados=sum(len(r.loops) for r in regs) + len(strokes), nodos=nodes, colores=len(pal),
                 segundos=round(time.time() - t0, 2))
    h, w = labels.shape
    return VectorResult(w, h, res.dpi, pal, regs, stats, res.mode, res.source_scale, labels, res.opts, strokes,
                        res.text_zones, [], res.symmetry, res.work)
