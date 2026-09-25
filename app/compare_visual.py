"""Diferencia visual: SSIM + diferencia absoluta + contornos."""
from dataclasses import dataclass
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

from .models import Difference


def save_png(path, rgb: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not ok:
        raise RuntimeError("No se pudo guardar la imagen")
    Path(path).write_bytes(buf.tobytes())


@dataclass
class VisualResult:
    score: float  # 0..1
    differences: list[Difference]
    diff_strength: np.ndarray  # 0..1 por píxel


def _crop(img, bbox, pad=0):
    x, y, w, h = bbox
    H, W = img.shape[:2]
    return img[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)]


def _phash_dist(a: np.ndarray, b: np.ndarray) -> int:
    def prep(c):
        g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)
        g = cv2.resize(g, (64, 64), interpolation=cv2.INTER_AREA)
        return Image.fromarray(g)
    return imagehash.phash(prep(a)) - imagehash.phash(prep(b))


def classify_region(design: np.ndarray, client: np.ndarray, bbox) -> tuple[str, str]:
    """Devuelve (subtype, mensaje) para una región visual."""
    d = _crop(design, bbox, 2)
    c = _crop(client, bbox, 2)
    if d.size == 0 or c.size == 0:
        return "diferencia_visual", "Diferencia visual"
    sd = float(cv2.cvtColor(d, cv2.COLOR_RGB2GRAY).std())
    sc = float(cv2.cvtColor(c, cv2.COLOR_RGB2GRAY).std())
    if sc < 6 and sd >= 10:
        return ("elemento_sobrante",
                "Elemento visual (logo/imagen/forma) presente en tu diseño pero ausente en el arte del cliente")
    if sd < 6 and sc >= 10:
        return ("elemento_faltante",
                "Elemento visual (logo/imagen/forma) del cliente que falta en tu diseño")
    dist = _phash_dist(d, c)
    if dist > 10:
        return "elemento_cambiado", "Imagen o logo distinto, o movido de posición"
    md = np.median(d.reshape(-1, 3), axis=0)
    mc = np.median(c.reshape(-1, 3), axis=0)
    if float(np.abs(md - mc).max()) > 25:
        return "color_distinto", "Misma forma con distinto color"
    return "diferencia_visual", "Diferencia visual leve"


def tolerant_excess(d: np.ndarray, c: np.ndarray, k: int = 5) -> np.ndarray:
    """Cuánto se sale el cliente del rango [mín, máx] local del diseño (ventana k×k).
    Ignora desajustes de 1–2 px en los bordes, desenfoque y ruido; conserva diferencias reales de contenido."""
    kern = np.ones((k, k), np.uint8)
    dmax = cv2.dilate(d, kern).astype(np.int16)
    dmin = cv2.erode(d, kern).astype(np.int16)
    ci = c.astype(np.int16)
    ex = np.maximum(np.maximum(ci - dmax, dmin - ci), 0)
    return ex.max(axis=2).astype(np.uint8)


def compare_visual(design: np.ndarray, client: np.ndarray, cfg: dict, valid: np.ndarray | None = None) -> VisualResult:
    d = cv2.GaussianBlur(design, (3, 3), 0)
    c = cv2.GaussianBlur(client, (3, 3), 0)
    gd = cv2.cvtColor(d, cv2.COLOR_RGB2GRAY)
    gc = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)
    score, dmap = structural_similarity(gd, gc, full=True, data_range=255)
    ex = tolerant_excess(d, c)

    # el deslizador "umbral SSIM" sube o baja la exigencia: 0,85 = umbral de píxeles configurado
    ssim_thr = float(cfg["ssim_threshold"])
    thr = float(cfg["pixel_diff_threshold"]) * float(np.clip(1.0 - (ssim_thr - 0.85) * 4.0, 0.4, 2.5))
    mask = (ex > thr).astype(np.uint8) * 255
    if valid is not None:  # el relleno blanco de la alineación no cuenta como diferencia
        inner = cv2.erode(valid.astype(np.uint8), np.ones((9, 9), np.uint8))
        mask[inner == 0] = 0
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.dilate(mask, k, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = design.shape[:2]
    diffs: list[Difference] = []
    for cnt in contours:
        if cv2.contourArea(cnt) < float(cfg["min_region_area"]):
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        frac = (w * h) / float(W * H)
        region_strength = float(ex[y:y + h, x:x + w].mean())
        if frac > 0.02 or region_strength > 90:
            sev = "alta"
        elif frac > 0.003 or region_strength > 40:
            sev = "media"
        else:
            sev = "baja"
        sub, msg = classify_region(design, client, (x, y, w, h))
        diffs.append(Difference(category="visual", subtype=sub, bbox=(x, y, w, h), severity=sev, message=msg))

    strength = np.maximum(ex.astype(np.float32) / 255.0 * 2.0, 1.0 - np.clip(dmap, 0, 1) * 1.0 - 0.6)
    strength = np.clip(strength, 0, 1)
    if valid is not None:
        strength = strength * cv2.erode(valid.astype(np.uint8), np.ones((9, 9), np.uint8))
    return VisualResult(float(score), diffs, strength.astype(np.float32))


def make_outputs(design, client, strength, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    save_png(out_dir / "design.png", design)
    save_png(out_dir / "client_aligned.png", client)

    s = np.clip(strength * 2.0, 0, 1)
    heat = cv2.applyColorMap((s * 255).astype(np.uint8), cv2.COLORMAP_JET)
    heat = cv2.cvtColor(heat, cv2.COLOR_BGR2RGB)
    base = cv2.cvtColor(cv2.cvtColor(design, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    base = (255 - (255 - base.astype(np.float32)) * 0.35)
    alpha = np.clip(s * 1.5, 0, 0.85)[..., None]
    out = base * (1 - alpha) + heat.astype(np.float32) * alpha
    save_png(out_dir / "diff_heatmap.png", out.astype(np.uint8))

    overlay = cv2.addWeighted(design, 0.5, client, 0.5, 0)
    save_png(out_dir / "overlay.png", overlay)
    return {"design": "design.png", "client": "client_aligned.png",
            "diff": "diff_heatmap.png", "overlay": "overlay.png"}
