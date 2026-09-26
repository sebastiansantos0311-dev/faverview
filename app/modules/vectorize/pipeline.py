"""Pipeline del vectorizador v1 (S4): preprocess → quantize → regions → boundaries → fit → export."""
import time
from dataclasses import dataclass, field

import numpy as np

from app.core import colorscience as cs
from app.modules.separate import raster
from app.modules.vectorize import boundaries, fit, preprocess, quantize, regions

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
    source_scale: float = 1.0        # px del vector por px de la imagen original


def vectorize(rgb: np.ndarray, dpi: float | None = None, *, preset: str | None = None, palette=None, k_max: int = 8,
              merge_de: float = 6.0, min_detail_mm: float = 0.15, fit_tol: float = 0.8, corner_angle: float = 60.0,
              smooth: float = 1.6, denoise: float = 1.0, bn: bool = False, bn_threshold: int | None = None,
              mode: str = "sin_solapes", upscale: bool = True, primitives=None) -> VectorResult:
    """Vectoriza `rgb` en regiones de color con fronteras compartidas. Las coordenadas quedan en px de la imagen de trabajo."""
    t0 = time.time()
    p = {**PRESETS.get(preset or "", {})}
    k_max = p.get("k_max", k_max); merge_de = p.get("merge_de", merge_de); fit_tol = p.get("fit_tol", fit_tol)
    denoise = p.get("denoise", denoise); bn = p.get("bn", bn); min_detail_mm = p.get("min_detail_mm", min_detail_mm)
    scale = 1.0
    work = rgb
    if upscale:
        work, scale = preprocess.upscale_if_small(rgb)
    if bn:
        work = preprocess.binarize(work, bn_threshold)
    else:
        work = preprocess.denoise(work, denoise)
    wdpi = dpi * scale if dpi else None
    min_px = 4
    if wdpi and min_detail_mm:
        min_px = max(4, int(round((min_detail_mm / 25.4 * wdpi) ** 2)))
    labels, pal = quantize.quantize(work, wdpi, palette, k_max, merge_de, min_px)
    chains = boundaries.build_chains(labels)
    fitted = []
    for c in chains:
        if c.closed:
            fitted.append(fit.fit_closed(c.pts, fit_tol * scale, corner_angle, smooth, scale))
        else:
            fitted.append(fit.fit_polyline(c.pts, fit_tol * scale, corner_angle, smooth, scale))
    meta = {i: (cs.lab_to_hex(ink.lab), tuple(ink.lab)) for i, ink in enumerate(pal)}
    regs = regions.assemble(chains, fitted, meta)
    if primitives:
        regs = primitives(regs, chains, labels)
    if mode == "apilado":
        regs = sorted(regs, key=lambda r: -r.filled_area())
    else:  # sin solapes: la región de mayor área primero (solo para el orden del archivo)
        regs = sorted(regs, key=lambda r: -r.filled_area())
    nodes = sum(len(l.segs) for r in regs for l in r.loops)
    stats = {"trazados": sum(len(r.loops) for r in regs), "nodos": nodes, "colores": len(pal), "segundos": round(time.time() - t0, 2),
             "escala": scale}
    h, w = labels.shape
    return VectorResult(w, h, wdpi, pal, regs, stats, mode, scale)
