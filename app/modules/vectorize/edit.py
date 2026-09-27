"""Edición básica del vector (S5 §9): fusionar dos colores, recolorear, borrar una región y volver a trazar una zona."""
import numpy as np
from scipy import ndimage as ndi

from app.core import colorscience as cs
from app.core.errors import UserError
from app.modules.separate import raster
from app.modules.vectorize import pipeline, preprocess, quantize


def _compact(labels, pal):
    used = np.unique(labels)
    remap = np.zeros(int(used.max()) + 1, np.int32)
    remap[used] = np.arange(len(used))
    return remap[labels], [pal[i] for i in used]


def _check(res, *idx):
    for i in idx:
        if not 0 <= i < len(res.palette):
            raise UserError("Ese color no existe.")


def merge(res, a: int, b: int):
    """Une el color `b` con el `a` (el resultado conserva el color de `a`)."""
    _check(res, a, b)
    if a == b:
        raise UserError("Elige dos colores distintos.")
    lab = np.where(res.labels == b, a, res.labels)
    lab, pal = _compact(lab, res.palette)
    return pipeline.retrace(res, lab, pal)


def delete_region(res, k: int):
    """Borra un color: sus píxeles pasan a la región vecina más cercana."""
    _check(res, k)
    if len(res.palette) < 2:
        raise UserError("No se puede borrar el único color.")
    mask = res.labels == k
    _, (iy, ix) = ndi.distance_transform_edt(mask, return_indices=True)
    lab = res.labels[iy, ix]
    lab, pal = _compact(lab, res.palette)
    return pipeline.retrace(res, lab, pal)


def recolor(res, k: int, hex_color: str):
    _check(res, k)
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise UserError("El color debe ser #rrggbb.")
    rgb = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) / 255
    pal = list(res.palette)
    pal[k] = raster.Ink(pal[k].name, tuple(float(x) for x in cs.srgb_to_lab(rgb)), pal[k].opacity)
    return pipeline.retrace(res, res.labels.copy(), pal)


def retrace_zone(res, rgb_work: np.ndarray, rect: tuple[int, int, int, int], *, k_max: int | None = None, merge_de: float = 6.0,
                 denoise: float = 1.0):
    """Recalcula las etiquetas dentro de `rect` (x, y, w, h en px del vector) con otros parámetros; si `k_max` es mayor que el
    número de colores actuales, la zona puede usar colores nuevos (se añaden a la paleta)."""
    x, y, w, h = rect
    x0, y0 = max(int(x), 0), max(int(y), 0)
    x1, y1 = min(int(x + w), res.labels.shape[1]), min(int(y + h), res.labels.shape[0])
    if x1 - x0 < 4 or y1 - y0 < 4:
        raise UserError("La zona es demasiado pequeña.")
    crop = preprocess.denoise(rgb_work[y0:y1, x0:x1], denoise)
    if k_max and k_max > len(res.palette):
        sub_lab, sub_pal = quantize.quantize(crop, res.dpi, None, k_max, merge_de, 4)
        pal = list(res.palette)
        remap = {}
        for i, ink in enumerate(sub_pal):
            d = [float(cs.delta_e2000(ink.lab, p.lab)) for p in pal]
            j = int(np.argmin(d))
            if d[j] < merge_de:
                remap[i] = j
            else:
                pal.append(raster.Ink(f"Color {len(pal) + 1}", ink.lab))
                remap[i] = len(pal) - 1
        new = np.vectorize(remap.get)(sub_lab)
    else:
        pal = list(res.palette)
        lab = raster.rgb_to_lab(crop)
        new = raster._nearest(lab, np.array([p.lab for p in pal], np.float32))
    labels = res.labels.copy()
    labels[y0:y1, x0:x1] = new
    labels, pal = _compact(labels, pal)
    return pipeline.retrace(res, labels, pal)
