"""Separación de imágenes en tintas (S3 §7): tintas planas, proceso simulado, índice y CMYK.

Convención: canales uint8 con 255 = 100 % de tinta (igual que las placas del PDF)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from app.core import colorscience as cs
from app.core.errors import UserError

PAPER = (95.0, 0.0, -2.0)
SUBSTRATES = {"Papel blanco": PAPER, "Prenda negra": (12.0, 0.0, 0.0), "Prenda gris": (50.0, 0.0, 0.0),
              "Prenda roja": (40.0, 55.0, 35.0), "Prenda azul marino": (20.0, 5.0, -25.0), "Kraft": (65.0, 12.0, 28.0)}


@dataclass
class Ink:
    name: str
    lab: tuple
    opacity: float = 0.0     # 1 = opaca (blanco, metálica)

    def as_model(self) -> dict:
        return {"lab": tuple(self.lab), "opacity": self.opacity}


@dataclass
class SepResult:
    names: list[str]
    channels: dict[str, np.ndarray]
    sim: np.ndarray                      # sRGB uint8 simulado sobre el sustrato
    de_map: np.ndarray | None = None     # ΔE por píxel (proceso simulado)
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    palette: list[Ink] = field(default_factory=list)


# ---------------------------------------------------------------- carga y utilidades
def load_image(path, max_mpx: float = 60.0) -> tuple[np.ndarray, tuple[float, float] | None]:
    """Imagen RGB uint8 (con alfa compuesto sobre blanco) y dpi si el archivo lo trae."""
    try:
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(path)
        dpi = im.info.get("dpi")
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            im = bg
        im = im.convert("RGB")
    except Exception:
        raise UserError("No se pudo abrir la imagen (¿está dañada o es un formato no admitido?).")
    w, h = im.size
    if w * h > max_mpx * 1e6:
        f = (max_mpx * 1e6 / (w * h)) ** 0.5
        im = im.resize((int(w * f), int(h * f)), Image.LANCZOS)
    return np.array(im), (tuple(float(x) for x in dpi) if dpi else None)


def rgb_to_lab(rgb: np.ndarray, band: int = 256) -> np.ndarray:
    out = np.empty(rgb.shape, np.float32)
    for y in range(0, rgb.shape[0], band):
        out[y:y + band] = cs.srgb_to_lab(rgb[y:y + band].astype(np.float64) / 255.0)
    return out


def _lab_to_rgb_u8(lab) -> np.ndarray:
    return np.clip(np.rint(np.asarray(cs.lab_to_srgb(lab)) * 255), 0, 255).astype(np.uint8)


def simulate(names_inks: list[Ink], covs: list[np.ndarray], substrate=PAPER, n: float = 1.7) -> np.ndarray:
    """PNG sRGB de la mezcla de canales (0–255) sobre el sustrato."""
    if not names_inks:
        return np.zeros((1, 1, 3), np.uint8)
    h, w = covs[0].shape
    out = np.empty((h, w, 3), np.uint8)
    for y in range(0, h, 512):
        c = [a[y:y + 512].astype(np.float32) / 255.0 for a in covs]
        rgb = cs.mix_inks(substrate, [i.as_model() for i in names_inks], c, n=n, output="srgb")
        out[y:y + 512] = np.clip(np.rint(np.asarray(rgb) * 255), 0, 255)
    return out


def _nearest(lab: np.ndarray, pal: np.ndarray, band: int = 512) -> np.ndarray:
    idx = np.empty(lab.shape[:2], np.int32)
    for y in range(0, lab.shape[0], band):
        d = ((lab[y:y + band, :, None, :] - pal[None, None, :, :]) ** 2).sum(-1)
        idx[y:y + band] = d.argmin(-1)
    return idx


# ---------------------------------------------------------------- tintas planas
def auto_palette(lab: np.ndarray, k_max: int = 12, merge_de: float = 6.0, min_frac: float = 0.004) -> np.ndarray:
    flat = lab.reshape(-1, 3)
    if len(flat) > 200_000:
        flat = flat[np.random.default_rng(0).choice(len(flat), 200_000, replace=False)]
    k = int(min(max(k_max, 2), 12))
    _, labels, centers = cv2.kmeans(flat.astype(np.float32), k, None,
                                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    cnt = np.bincount(labels, minlength=k).astype(float)
    cents = [c.astype(float) for c in centers]
    # fusionar los que están a menos de merge_de (ΔE2000), el menor hacia el mayor
    changed = True
    while changed and len(cents) > 1:
        changed = False
        for i in range(len(cents)):
            for j in range(i + 1, len(cents)):
                if float(cs.delta_e2000(cents[i], cents[j])) < merge_de:
                    w = cnt[i] + cnt[j]
                    cents[i] = (cents[i] * cnt[i] + cents[j] * cnt[j]) / max(w, 1)
                    cnt[i] = w
                    del cents[j]
                    cnt = np.delete(cnt, j)
                    changed = True
                    break
            if changed:
                break
    keep = [c for c, n in zip(cents, cnt) if n / cnt.sum() >= min_frac]
    order = np.argsort(-np.array([n for n in cnt if n / cnt.sum() >= min_frac]))
    return np.array([keep[i] for i in order])


def _remove_islands(idx: np.ndarray, min_px: int) -> np.ndarray:
    if min_px <= 1:
        return idx
    out = idx.copy()
    bad = np.zeros(idx.shape, bool)
    for k in np.unique(idx):
        n, lab, st, _ = cv2.connectedComponentsWithStats((idx == k).astype(np.uint8), connectivity=4)
        small = np.where(st[1:, cv2.CC_STAT_AREA] < min_px)[0] + 1
        if len(small):
            bad |= np.isin(lab, small)
    if bad.any() and not bad.all():
        _, (iy, ix) = ndi.distance_transform_edt(bad, return_indices=True)
        out = idx[iy, ix]
    return out


def separate_flat(rgb: np.ndarray, dpi: float | None, palette: list[Ink] | None = None, k_max: int = 8,
                  merge_de: float = 6.0, min_area_mm2: float = 0.05, soft_edges: bool = False,
                  smooth: bool = True, substrate=PAPER) -> SepResult:
    warns = []
    src = cv2.bilateralFilter(rgb, 5, 30, 5) if smooth and max(rgb.shape[:2]) < 3000 else rgb
    lab = rgb_to_lab(src)
    if palette:
        pal_lab = np.array([p.lab for p in palette], np.float32)
        inks = list(palette)
    else:
        pal_lab = auto_palette(lab, k_max, merge_de).astype(np.float32)
        inks = [Ink(f"Tinta {i + 1}", tuple(float(x) for x in c)) for i, c in enumerate(pal_lab)]
    idx = _nearest(lab, pal_lab)
    if not palette and len(pal_lab) > 2:      # descarta colores de borde/ruido que ocupan casi nada y reasigna
        area = np.bincount(idx.ravel(), minlength=len(pal_lab)) / idx.size
        keep = area >= 0.004
        for c in range(len(pal_lab)):        # mezclas de borde: caen sobre el segmento entre dos colores mayores
            if not keep[c] or area[c] > 0.03:
                continue
            for a in range(len(pal_lab)):
                for b in range(a + 1, len(pal_lab)):
                    if c in (a, b) or area[a] < 0.03 or area[b] < 0.03:
                        continue
                    v = pal_lab[b] - pal_lab[a]
                    t = np.clip(np.dot(pal_lab[c] - pal_lab[a], v) / max(float(np.dot(v, v)), 1e-6), 0, 1)
                    if np.linalg.norm(pal_lab[a] + t * v - pal_lab[c]) < 10:
                        keep[c] = False
        if not keep.all() and keep.any():
            pal_lab = pal_lab[keep]
            inks = [Ink(f"Tinta {i + 1}", tuple(float(x) for x in c)) for i, c in enumerate(pal_lab)]
            idx = _nearest(lab, pal_lab)
    px_mm2 = (25.4 / dpi) ** 2 if dpi else None
    min_px = int(round(min_area_mm2 / px_mm2)) if px_mm2 else 4
    idx = _remove_islands(idx, max(min_px, 1))
    chans = {i.name: ((idx == k) * 255).astype(np.uint8) for k, i in enumerate(inks)}
    if soft_edges and len(inks) > 1:
        k1 = idx
        d = ((lab[:, :, None, :] - pal_lab[None, None]) ** 2).sum(-1) if lab.size < 3e7 else None
        if d is not None:
            d[np.arange(idx.shape[0])[:, None], np.arange(idx.shape[1])[None, :], k1] = np.inf
            k2 = d.argmin(-1)
            c1, c2 = pal_lab[k1], pal_lab[k2]
            v = c2 - c1
            a = np.clip(((lab - c1) * v).sum(-1) / np.maximum((v * v).sum(-1), 1e-6), 0, 1)
            edge = (cv2.dilate(idx.astype(np.uint8), np.ones((3, 3), np.uint8)) != cv2.erode(idx.astype(np.uint8), np.ones((3, 3), np.uint8)))
            for k, i in enumerate(inks):
                soft = np.where(edge & (k1 == k), 1 - a, np.where(edge & (k2 == k), a, chans[i.name] / 255.0))
                chans[i.name] = np.rint(soft * 255).astype(np.uint8)
        else:
            warns.append("Imagen muy grande: los bordes suaves se omitieron (se usaron bordes duros).")
    sim = simulate(inks, [chans[i.name] for i in inks], substrate) if len(inks) < 12 else _lab_to_rgb_u8(pal_lab[idx])
    de = float(np.mean([cs.delta_e2000(lab[::8, ::8].reshape(-1, 3)[j], pal_lab[idx[::8, ::8].ravel()[j]])
                        for j in range(0, min(2000, lab[::8, ::8].reshape(-1, 3).shape[0]), 1)]))
    return SepResult([i.name for i in inks], chans, _lab_to_rgb_u8(pal_lab[idx]), None,
                     {"modo": "planas", "tintas": len(inks), "de_paleta_medio": round(de, 2)}, warns, inks)


# ---------------------------------------------------------------- proceso simulado
def _samples(n_inks: int, rng) -> np.ndarray:
    levels = {1: 21, 2: 13, 3: 9, 4: 7, 5: 5, 6: 4, 7: 4, 8: 3}[min(n_inks, 8)]
    axes = np.linspace(0, 1, levels)
    grid = np.array(np.meshgrid(*[axes] * n_inks, indexing="ij")).reshape(n_inks, -1).T
    rnd = rng.random((30000, n_inks)) ** 1.5
    rnd *= (rng.random((30000, n_inks)) < 0.6)     # muchas muestras con pocas tintas
    return np.vstack([grid, rnd]).astype(np.float32)


def separate_process(rgb: np.ndarray, inks: list[Ink], substrate=PAPER, lam: float = 4.0, n: float = 1.7,
                     min_dot: float = 0.03, max_dot: float = 1.0, gamma: float = 1.0, choke_px: int = 0,
                     white_index: int | None = None, top_k: int = 24) -> SepResult:
    """Para cada color (cuantizado a 5 bits por canal) busca la combinación de coberturas cuya mezcla simulada se acerca más."""
    if not inks:
        raise UserError("Elige al menos una tinta.")
    if len(inks) > 8:
        raise UserError("El modo de proceso simulado admite hasta 8 tintas.")
    rng = np.random.default_rng(1)
    samp = _samples(len(inks), rng)
    slab = np.asarray(cs.mix_inks(substrate, [i.as_model() for i in inks], [samp[:, k] for k in range(len(inks))], n=n))
    tree = cKDTree(slab)
    q = (rgb >> 3).astype(np.int32)
    code = (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
    uniq, inv = np.unique(code, return_inverse=True)
    urgb = np.stack([((uniq >> 10) & 31), ((uniq >> 5) & 31), (uniq & 31)], -1).astype(np.float64) * 8 + 4
    ulab = np.asarray(cs.srgb_to_lab(urgb / 255.0))
    dist, nb = tree.query(ulab, k=min(top_k, len(samp)))
    cost = dist + lam * samp[nb].sum(-1) * 0.5          # ΔE + penalización por tinta total (ahorro de tinta)
    best = nb[np.arange(len(nb)), cost.argmin(1)]
    ucov = samp[best]
    ude = np.linalg.norm(slab[best] - ulab, axis=1)
    cov = ucov[inv.reshape(code.shape)]
    de_map = ude[inv.reshape(code.shape)].astype(np.float32)
    chans = {}
    for k, ink in enumerate(inks):
        c = cov[..., k]
        c = np.clip(c, 0, 1) ** gamma
        c = np.where(c < min_dot, 0.0, c)
        c = np.minimum(c, max_dot)
        a = np.rint(c * 255).astype(np.uint8)
        if choke_px > 0 and (white_index == k or ink.opacity >= 1):
            a = cv2.erode(a, np.ones((2 * choke_px + 1,) * 2, np.uint8))
        chans[ink.name] = a
    sim = simulate(inks, [chans[i.name] for i in inks], substrate, n)
    tot = sum(chans[i.name].astype(np.float32) for i in inks) / 255 * 100
    stats = {"modo": "proceso", "de_medio": round(float(de_map.mean()), 2), "de_p95": round(float(np.percentile(de_map, 95)), 2),
             "cobertura_total_media": round(float(tot.mean()), 1), "tintas": len(inks)}
    return SepResult([i.name for i in inks], chans, sim, de_map, stats, [], inks)


def de_heatmap(de: np.ndarray, top: float = 15.0) -> np.ndarray:
    v = np.clip(de / top, 0, 1)
    return cv2.applyColorMap((v * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)[..., ::-1]


# ---------------------------------------------------------------- índice
def separate_index(rgb: np.ndarray, palette: list[Ink] | None = None, k: int = 6, dither: str = "fs",
                   substrate=PAPER) -> SepResult:
    warns = ["El modo índice no se puede reescalar después: la trama de difusión depende de la resolución."]
    if palette:
        pal = np.array([p.lab for p in palette], np.float32)
        inks = list(palette)
    else:
        pal = auto_palette(rgb_to_lab(cv2.resize(rgb, None, fx=0.25, fy=0.25) if max(rgb.shape[:2]) > 1200 else rgb), k, 3.0).astype(np.float32)
        inks = [Ink(f"Tinta {i + 1}", tuple(float(x) for x in c)) for i, c in enumerate(pal)]
    if len(inks) > 255:
        raise UserError("La paleta admite hasta 255 colores.")
    pal_rgb = _lab_to_rgb_u8(pal)
    pim = Image.new("P", (1, 1))
    flat = pal_rgb.reshape(-1).tolist() + pal_rgb[-1].tolist() * (256 - len(pal_rgb))
    pim.putpalette(flat)
    q = Image.fromarray(rgb).quantize(palette=pim, dither=Image.Dither.FLOYDSTEINBERG if dither == "fs" else Image.Dither.NONE)
    idx = np.array(q)
    chans = {i.name: ((idx == k) * 255).astype(np.uint8) for k, i in enumerate(inks)}
    return SepResult([i.name for i in inks], chans, pal_rgb[idx], None, {"modo": "indice", "tintas": len(inks)}, warns, inks)


# ---------------------------------------------------------------- CMYK con ICC
def find_cmyk_profiles() -> dict[str, str]:
    dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "spool" / "drivers" / "color",
            Path("/usr/share/color/icc"), Path.home() / "Library" / "ColorSync" / "Profiles",
            Path(__file__).resolve().parents[3] / "datos_locales" / "perfiles_icc"]
    found = {}
    for d in dirs:
        if d.exists():
            for f in list(d.glob("*.icc")) + list(d.glob("*.icm")):
                try:
                    from PIL import ImageCms
                    p = ImageCms.getOpenProfile(str(f))
                    if p.profile.xcolor_space.strip() == "CMYK":
                        found[f.stem] = str(f)
                except Exception:
                    pass
    return found


def limit_tac(cmyk: np.ndarray, limit: float) -> np.ndarray:
    """Reduce CMY proporcionalmente para no pasar del TAC, manteniendo K (GCR simple)."""
    f = cmyk.astype(np.float32) / 255.0 * 100.0
    total = f.sum(-1)
    cmy = f[..., :3].sum(-1)
    scale = np.where(total > limit, np.maximum(limit - f[..., 3], 0) / np.maximum(cmy, 1e-6), 1.0)
    f[..., :3] *= np.clip(scale, 0, 1)[..., None]
    return np.rint(f / 100.0 * 255).astype(np.uint8)


def separate_cmyk(rgb: np.ndarray, profile: str | None = None, intent: str = "relativa", tac: float = 300.0,
                  black_only_shadows: bool = False) -> SepResult:
    from PIL import ImageCms
    profs = find_cmyk_profiles()
    path = profile if profile and Path(profile).exists() else profs.get(profile or "") or (next(iter(profs.values())) if profs else None)
    if not path:
        raise UserError("No hay ningún perfil ICC CMYK. Copia uno (FOGRA39/51, GRACoL…) en «datos_locales/perfiles_icc» "
                        "o instálalo en Windows. Se pueden descargar gratis de eci.org.")
    srgb = ImageCms.createProfile("sRGB")
    prof = ImageCms.getOpenProfile(path)
    it = ImageCms.Intent.PERCEPTUAL if intent == "perceptual" else ImageCms.Intent.RELATIVE_COLORIMETRIC
    flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if it == ImageCms.Intent.RELATIVE_COLORIMETRIC else 0
    t = ImageCms.buildTransform(srgb, prof, "RGB", "CMYK", it, flags)
    out = np.array(ImageCms.applyTransform(Image.fromarray(rgb), t))
    # PIL/LittleCMS entrega CMYK con 255 = 100 % de tinta
    if black_only_shadows:
        lum = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        out[..., 3] = (out[..., 3] * np.clip((0.35 - lum) / 0.35, 0, 1)).astype(np.uint8)
    out = limit_tac(out, tac)
    names = ["Cyan", "Magenta", "Yellow", "Black"]
    back = ImageCms.buildTransform(prof, srgb, "CMYK", "RGB", ImageCms.Intent.RELATIVE_COLORIMETRIC)
    sim = np.array(ImageCms.applyTransform(Image.fromarray(out, "CMYK"), back))
    tot = out.astype(np.float32).sum(-1) / 255 * 100
    return SepResult(names, {n: out[..., i] for i, n in enumerate(names)}, sim, None,
                     {"modo": "cmyk", "perfil": Path(path).stem, "tac_max": round(float(tot.max()), 1), "tac_medio": round(float(tot.mean()), 1)},
                     [], [])
