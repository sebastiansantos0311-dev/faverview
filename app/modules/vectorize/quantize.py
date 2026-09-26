"""Cuantización a un mapa de etiquetas con paleta controlada (reutiliza el modo «tintas planas» de S3)."""
import cv2
import numpy as np
from scipy import ndimage as ndi

from app.modules.separate import raster


def quantize(rgb: np.ndarray, dpi: float | None = None, palette: list[raster.Ink] | None = None, k_max: int = 8,
             merge_de: float = 6.0, min_area_px: int = 4, thin_px: int = 0) -> tuple[np.ndarray, list[raster.Ink]]:
    """Devuelve (etiquetas HxW int32, paleta). Sin paleta se calcula con k-means en Lab."""
    lab = raster.rgb_to_lab(rgb)
    if palette:
        pal_lab = np.array([p.lab for p in palette], np.float32)
        inks = list(palette)
    else:
        pal_lab = raster.auto_palette(lab, k_max, merge_de).astype(np.float32)
        inks = [raster.Ink(f"Color {i + 1}", tuple(float(x) for x in c)) for i, c in enumerate(pal_lab)]
    idx = raster._nearest(lab, pal_lab)
    if not palette and len(pal_lab) > 2:
        area = np.bincount(idx.ravel(), minlength=len(pal_lab)) / idx.size
        keep = raster.prune_edge_colors(pal_lab, area, 0.002)
        if not keep.all() and keep.any():
            pal_lab = pal_lab[keep]
            inks = [raster.Ink(f"Color {i + 1}", tuple(float(x) for x in c)) for i, c in enumerate(pal_lab)]
            idx = raster._nearest(lab, pal_lab)
    idx = raster._remove_islands(idx, max(min_area_px, 1))
    if thin_px >= 2:
        idx = _remove_thin(idx, thin_px)
    return _compact(idx, inks)


def _compact(idx: np.ndarray, inks):
    used = np.unique(idx)
    remap = np.zeros(int(used.max()) + 1, np.int32)
    remap[used] = np.arange(len(used))
    return remap[idx], [inks[i] for i in used]


def _remove_thin(idx: np.ndarray, width: int) -> np.ndarray:
    """Quita las estructuras más finas que `width` px (anillos de antialias): sus píxeles pasan a la región vecina más cercana."""
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (width | 1, width | 1))
    lost = np.zeros(idx.shape, bool)
    for k in np.unique(idx):
        m = (idx == k).astype(np.uint8)
        lost |= (m > 0) & (cv2.morphologyEx(m, cv2.MORPH_OPEN, ker) == 0)
    if not lost.any() or lost.all():
        return idx
    _, (iy, ix) = ndi.distance_transform_edt(lost, return_indices=True)
    return idx[iy, ix]
