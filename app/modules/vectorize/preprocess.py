"""Preprocesado del vectorizador (S4 §8.1): escalado, limpieza de ruido JPEG y umbral B/N."""
import cv2
import numpy as np
from skimage.filters import threshold_sauvola


def upscale_if_small(rgb: np.ndarray, min_side: int = 800, max_factor: int = 4) -> tuple[np.ndarray, float]:
    s = min(rgb.shape[:2])
    if s >= min_side:
        return rgb, 1.0
    f = min(max_factor, int(np.ceil(min_side / s)))
    f = max(f, 2)
    return cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_LANCZOS4), float(f)


def denoise(rgb: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Quita el ruido JPEG y el antialias con mean-shift (preserva bordes)."""
    if strength <= 0:
        return rgb
    sp, sr = 6 + 4 * strength, 14 + 10 * strength
    if max(rgb.shape[:2]) > 3000:
        return cv2.bilateralFilter(rgb, 7, sr, sp)
    return cv2.pyrMeanShiftFiltering(rgb, sp, sr, 1)


def binarize(rgb: np.ndarray, threshold: int | None = None, window: int = 31) -> np.ndarray:
    """Devuelve una imagen de dos tonos: negro (tinta) y blanco. Sauvola por defecto; `threshold` manual (0–255)."""
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if threshold is not None:
        m = g < threshold
    else:
        w = window | 1
        m = g < threshold_sauvola(g, window_size=w, k=0.2)
    out = np.where(m, 0, 255).astype(np.uint8)
    return np.repeat(out[..., None], 3, 2)
