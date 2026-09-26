"""Cuantización a un mapa de etiquetas con paleta controlada (reutiliza el modo «tintas planas» de S3)."""
import numpy as np

from app.modules.separate import raster


def quantize(rgb: np.ndarray, dpi: float | None = None, palette: list[raster.Ink] | None = None, k_max: int = 8,
             merge_de: float = 6.0, min_area_px: int = 4) -> tuple[np.ndarray, list[raster.Ink]]:
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
        keep = area >= 0.002
        if not keep.all() and keep.any():
            pal_lab = pal_lab[keep]
            inks = [raster.Ink(f"Color {i + 1}", tuple(float(x) for x in c)) for i, c in enumerate(pal_lab)]
            idx = raster._nearest(lab, pal_lab)
    idx = raster._remove_islands(idx, max(min_area_px, 1))
    return _compact(idx, inks)


def _compact(idx: np.ndarray, inks):
    used = np.unique(idx)
    remap = np.zeros(int(used.max()) + 1, np.int32)
    remap[used] = np.arange(len(used))
    return remap[idx], [inks[i] for i in used]
