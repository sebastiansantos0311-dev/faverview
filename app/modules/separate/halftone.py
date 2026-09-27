"""Tramado (S3 §7.7): AM (matriz umbral girada) y FM (ruido azul generado con void-and-cluster).

Todas las funciones reciben una cobertura uint8 (255 = 100 %) a la resolución de salida y devuelven un bool (True = tinta)."""
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[3] / "tools"
DEFAULTS = {"serigrafia": {"lpi": 55, "angulos": [22.5] * 8}, "offset": {"lpi": 150, "angulos": [15, 75, 0, 45, 45, 45, 45, 45]}}


def _spot(fu, fv, shape: str):
    cu, cv = fu - 0.5, fv - 0.5
    if shape == "cuadrado":
        return -np.maximum(np.abs(cu), np.abs(cv))
    if shape == "elipse":
        return np.cos(2 * np.pi * cu) + 0.6 * np.cos(2 * np.pi * cv)
    return np.cos(2 * np.pi * cu) + np.cos(2 * np.pi * cv)        # redondo


def _rank_table(shape: str, n: int = 256):
    g = np.linspace(0, 1, n, endpoint=False) + 0.5 / n
    gg = np.sort(_spot(*np.meshgrid(g, g), shape).ravel())        # ascendente
    return gg


def am_halftone(cov: np.ndarray, dpi: float, lpi: float = 55, angle: float = 22.5, shape: str = "redondo",
                min_dot: float = 0.0, max_dot: float = 1.0, tile: int = 1024) -> np.ndarray:
    """Tramado AM: el punto crece desde el centro de cada celda; cobertura media ≈ nominal."""
    table = _rank_table(shape)
    th = np.deg2rad(angle)
    cth, sth = np.cos(th), np.sin(th)
    k = lpi / dpi
    h, w = cov.shape
    out = np.zeros((h, w), bool)
    xs = np.arange(w, dtype=np.float32)
    for y0 in range(0, h, tile):
        ys = np.arange(y0, min(h, y0 + tile), dtype=np.float32)[:, None]
        u = (xs[None, :] * cth + ys * sth) * k
        v = (-xs[None, :] * sth + ys * cth) * k
        g = _spot(u - np.floor(u), v - np.floor(v), shape)
        # posición de g en la distribución (0 = último en encenderse, 1 = primero)
        thr = 1.0 - np.searchsorted(table, g) / len(table)
        c = cov[y0:y0 + tile].astype(np.float32) / 255.0
        c = np.where(c < min_dot, 0.0, np.where(c > max_dot, 1.0, c))
        out[y0:y0 + tile] = (c > thr) & (c > 0)
    return out


def blue_noise(size: int = 64, seed: int = 7) -> np.ndarray:
    """Máscara de umbrales (0–1) de ruido azul con el algoritmo void-and-cluster (Ulichney). Se guarda en tools/."""
    f = TOOLS / f"blue_noise_{size}.npy"
    if f.exists():
        return np.load(f)
    rng = np.random.default_rng(seed)
    n = size * size
    sigma = 1.5
    ax = np.arange(size)
    d = np.minimum(ax, size - ax)
    kern = np.exp(-(d[:, None] ** 2 + d[None, :] ** 2) / (2 * sigma ** 2))
    kf = np.fft.rfft2(kern)

    def energy(b):
        return np.fft.irfft2(np.fft.rfft2(b.astype(float)) * kf, s=b.shape)

    pat = np.zeros((size, size), bool)
    pat.ravel()[rng.choice(n, n // 10, replace=False)] = True
    for _ in range(2000):                               # relajar: mover el punto más apretado al hueco más grande
        e = energy(pat)
        c = np.unravel_index(np.argmax(np.where(pat, e, -1)), pat.shape)
        pat[c] = False
        e = energy(pat)
        v = np.unravel_index(np.argmin(np.where(~pat, e, 1e9)), pat.shape)
        pat[v] = True
        if v == c:
            break
    rank = np.zeros((size, size))
    ones = int(pat.sum())
    work = pat.copy()
    for r in range(ones - 1, -1, -1):                   # fase 1: quitar el punto más apretado
        e = energy(work)
        c = np.unravel_index(np.argmax(np.where(work, e, -1)), work.shape)
        work[c] = False
        rank[c] = r
    work = pat.copy()
    for r in range(ones, n):                            # fases 2 y 3: añadir en el mayor hueco
        e = energy(work)
        v = np.unravel_index(np.argmin(np.where(~work, e, 1e9)), work.shape)
        work[v] = True
        rank[v] = r
    m = ((rank + 0.5) / n).astype(np.float32)
    TOOLS.mkdir(exist_ok=True)
    np.save(f, m)
    return m


def fm_halftone(cov: np.ndarray, min_dot: float = 0.0, max_dot: float = 1.0) -> np.ndarray:
    m = blue_noise(64)
    h, w = cov.shape
    thr = np.tile(m, (h // 64 + 1, w // 64 + 1))[:h, :w]
    c = cov.astype(np.float32) / 255.0
    c = np.where(c < min_dot, 0.0, np.where(c > max_dot, 1.0, c))
    return (c > thr) & (c > 0)


def halftone(cov: np.ndarray, dpi: float, kind: str = "am", index: int = 0, profile: str = "serigrafia", **kw) -> np.ndarray:
    if kind == "fm":
        return fm_halftone(cov, kw.get("min_dot", 0.03), kw.get("max_dot", 0.97))
    d = DEFAULTS.get(profile, DEFAULTS["serigrafia"])
    return am_halftone(cov, dpi, kw.get("lpi") or d["lpi"], kw.get("angle") if kw.get("angle") is not None else d["angulos"][index % 8],
                       kw.get("shape", "redondo"), kw.get("min_dot", 0.03), kw.get("max_dot", 0.97))
