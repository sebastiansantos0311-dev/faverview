"""Corrección de iluminación irregular del arte del cliente (fotos, escaneos)."""
import cv2
import numpy as np


def normalize_illumination(design: np.ndarray, client: np.ndarray, valid: np.ndarray | None = None):
    """Estima cómo varía la iluminación sobre el 'papel' (el color dominante del diseño) y la compensa.

    Solo se corrige la parte que VARÍA en la imagen (el degradado); el tono global no se toca, así un cambio real
    del color de fondo sigue siendo visible. Devuelve (cliente_corregido, aplicado)."""
    H, W = design.shape[:2]
    q = (design >> 5).astype(np.int32)
    key = (q[..., 0] << 6) | (q[..., 1] << 3) | q[..., 2]
    mode = np.bincount(key.ravel(), minlength=512).argmax()
    mask = key == mode
    if valid is not None:
        mask &= valid.astype(bool)
    if mask.mean() < 0.08:
        return client, False

    f = 4
    sh, sw = H // f, W // f
    m = cv2.resize(mask.astype(np.float32), (sw, sh), interpolation=cv2.INTER_AREA)
    d = cv2.resize(design, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.float32)
    c = cv2.resize(client, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.float32)

    def ratio(sigma, min_den):
        den = cv2.GaussianBlur(m, (0, 0), sigma)[..., None]
        cn = cv2.GaussianBlur(c * m[..., None], (0, 0), sigma) / np.maximum(den, 1e-6)
        dn = cv2.GaussianBlur(d * m[..., None], (0, 0), sigma) / np.maximum(den, 1e-6)
        return cn / np.maximum(dn, 1.0), den[..., 0] > min_den

    g_fine, ok_fine = ratio(12, 0.03)
    g_coarse, ok_coarse = ratio(45, 0.004)
    med = np.median(g_coarse[ok_coarse], axis=0) if ok_coarse.any() else np.ones(3)
    gain = np.where(ok_fine[..., None], g_fine, np.where(ok_coarse[..., None], g_coarse, med))
    med_g = np.maximum(np.median(gain[m > 0.5], axis=0), 1e-3)
    # variación espacial: se corrige toda; exposición global: solo hasta ±12% (más sería un cambio real de fondo)
    scalar = float(np.clip(med_g.mean(), 0.88, 1.12))
    gain = np.clip(gain / med_g * scalar, 0.5, 1.6)
    if float(gain.max() - gain.min()) < 0.04:
        return client, False
    gain = cv2.GaussianBlur(gain, (0, 0), 3)
    gain_full = cv2.resize(gain, (W, H), interpolation=cv2.INTER_LINEAR)
    out = np.clip(client.astype(np.float32) / gain_full, 0, 255).astype(np.uint8)
    return out, True
