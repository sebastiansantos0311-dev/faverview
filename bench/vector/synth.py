"""Logos sintéticos con vector verdadero (SVG) y degradaciones (S4 §8.4)."""
import cv2
import fitz
import numpy as np

W, H = 400, 300


def _palette(rng, n):
    while True:
        cols = rng.integers(20, 236, (n, 3))
        d = [np.abs(cols[i] - cols[j]).sum() for i in range(n) for j in range(i)]
        if not d or min(d) > 150:
            return ["#%02x%02x%02x" % tuple(c) for c in cols]


def _blob(rng, cx, cy, r):
    n = int(rng.integers(5, 8))
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = [(cx + r * (0.7 + 0.5 * rng.random()) * np.cos(a), cy + r * (0.7 + 0.5 * rng.random()) * np.sin(a)) for a in ang]
    d = f"M{(pts[0][0] + pts[-1][0]) / 2:.1f} {(pts[0][1] + pts[-1][1]) / 2:.1f}"
    for i in range(n):
        nx = pts[(i + 1) % n]
        d += f" Q{pts[i][0]:.1f} {pts[i][1]:.1f} {(pts[i][0] + nx[0]) / 2:.1f} {(pts[i][1] + nx[1]) / 2:.1f}"
    return d + " Z"


def logo_svg(seed: int, rot: float = 0.0) -> tuple[str, int]:
    rng = np.random.default_rng(seed)
    n = 2 + seed % 7
    cols = _palette(rng, n)
    body = [f'<rect width="{W}" height="{H}" fill="{cols[0]}"/>']
    for k in range(1, n):
        kind = (seed + k) % 5
        cx, cy = float(rng.integers(80, W - 80)), float(rng.integers(70, H - 70))
        c = cols[k]
        if kind == 0:
            body.append(f'<circle cx="{cx}" cy="{cy}" r="{rng.integers(25, 60)}" fill="{c}"/>')
        elif kind == 1:
            body.append(f'<rect x="{cx - 40}" y="{cy - 30}" width="{rng.integers(40, 110)}" height="{rng.integers(30, 80)}" fill="{c}"/>')
        elif kind == 2:
            body.append(f'<path d="{_blob(rng, cx, cy, float(rng.integers(30, 60)))}" fill="{c}"/>')
        elif kind == 3:
            pts = " ".join(f"{cx + rng.integers(-60, 60)},{cy + rng.integers(-50, 50)}" for _ in range(4 + k % 3))
            body.append(f'<polygon points="{pts}" fill="{c}"/>')
        else:
            body.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rng.integers(30, 70)}" ry="{rng.integers(15, 40)}" fill="{c}"/>')
    g = f'<g transform="rotate({rot} {W / 2} {H / 2})">' + "".join(body) + "</g>"
    # con la rotación el fondo debe seguir cubriendo el lienzo
    bg = f'<rect width="{W}" height="{H}" fill="{cols[0]}"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{bg}{g}</svg>', n


def render_svg(svg: str, scale: float = 1.0, alpha: bool = False, aa: bool = True) -> np.ndarray:
    fitz.TOOLS.set_aa_level(8 if aa else 0)
    try:
        doc = fitz.open(stream=svg.encode(), filetype="svg")
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=alpha)
        a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n).copy()
    finally:
        fitz.TOOLS.set_aa_level(8)
    return a


def degrade(seed: int):
    """Devuelve (entrada degradada RGB, verdad RGB al mismo tamaño, escala usada)."""
    rng = np.random.default_rng(1000 + seed)
    rot = float(rng.choice([0.0, -2.0, 1.5, 2.0]))
    svg, n = logo_svg(seed, rot)
    scale = float(rng.choice([0.5, 0.75, 1.0, 1.5]))
    truth = render_svg(svg, scale)[..., :3]
    img = truth.copy()
    if seed % 3 == 0:
        img = cv2.GaussianBlur(img, (0, 0), float(rng.choice([0.6, 1.0])))
    if seed % 4 == 1:
        img = np.clip(img.astype(np.int16) + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    q = int(rng.choice([50, 70, 85, 95]))
    _, b = cv2.imencode(".jpg", img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, q])
    img = cv2.imdecode(b, 1)[..., ::-1].copy()
    return img, truth, svg, n
