"""Ajuste de curvas por cadena (S4 §8.1.5): suavizado, esquinas y Bézier cúbicas por mínimos cuadrados (Schneider, 1990).

Un segmento es ("L", p0, p1) o ("C", p0, c1, c2, p1) con puntos (x, y) numpy."""
import numpy as np

from app.modules.vectorize import primitives


# ---------------------------------------------------------------- Schneider
def _bez(ctrl, t):
    t = np.asarray(t)[:, None]
    mt = 1 - t
    return mt ** 3 * ctrl[0] + 3 * mt ** 2 * t * ctrl[1] + 3 * mt * t ** 2 * ctrl[2] + t ** 3 * ctrl[3]


def _bez_d1(ctrl, t):
    t = np.asarray(t)[:, None]
    mt = 1 - t
    return 3 * mt ** 2 * (ctrl[1] - ctrl[0]) + 6 * mt * t * (ctrl[2] - ctrl[1]) + 3 * t ** 2 * (ctrl[3] - ctrl[2])


def _bez_d2(ctrl, t):
    t = np.asarray(t)[:, None]
    return 6 * (1 - t) * (ctrl[2] - 2 * ctrl[1] + ctrl[0]) + 6 * t * (ctrl[3] - 2 * ctrl[2] + ctrl[1])


def _chord(pts):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    return d / d[-1] if d[-1] > 0 else np.linspace(0, 1, len(pts))


def _generate(pts, u, t1, t2):
    p0, p3 = pts[0], pts[-1]
    b0, b1, b2, b3 = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u ** 2 * (1 - u), u ** 3
    A1 = t1[None, :] * b1[:, None]
    A2 = t2[None, :] * b2[:, None]
    C = np.array([[np.sum(A1 * A1), np.sum(A1 * A2)], [np.sum(A1 * A2), np.sum(A2 * A2)]])
    tmp = pts - (p0[None, :] * (b0 + b1)[:, None] + p3[None, :] * (b2 + b3)[:, None])
    X = np.array([np.sum(A1 * tmp), np.sum(A2 * tmp)])
    det = C[0, 0] * C[1, 1] - C[0, 1] ** 2
    seg = np.linalg.norm(p3 - p0)
    if abs(det) > 1e-12:
        a1 = (X[0] * C[1, 1] - X[1] * C[0, 1]) / det
        a2 = (C[0, 0] * X[1] - C[0, 1] * X[0]) / det
    else:
        a1 = a2 = 0.0
    if a1 < 1e-6 * seg or a2 < 1e-6 * seg:
        a1 = a2 = seg / 3.0
    return np.array([p0, p0 + t1 * a1, p3 + t2 * a2, p3])


def _reparam(ctrl, pts, u):
    d1, d2 = _bez_d1(ctrl, u), _bez_d2(ctrl, u)
    diff = _bez(ctrl, u) - pts
    num = np.sum(diff * d1, axis=1)
    den = np.sum(d1 * d1, axis=1) + np.sum(diff * d2, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        nu = np.where(np.abs(den) > 1e-12, u - num / den, u)
    return np.clip(nu, 0, 1)


def _max_err(pts, ctrl, u):
    d = np.linalg.norm(_bez(ctrl, u) - pts, axis=1)
    i = int(d.argmax())
    return float(d[i]), i


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else np.array([1.0, 0.0])


def fit_cubic(pts, t1, t2, tol, depth=0):
    """Ajusta una o varias cúbicas a `pts` (n, 2). t1: tangente al inicio (hacia adelante); t2: en el final (hacia atrás)."""
    if len(pts) == 2:
        d = np.linalg.norm(pts[1] - pts[0]) / 3
        return [np.array([pts[0], pts[0] + t1 * d, pts[1] + t2 * d, pts[1]])]
    u = _chord(pts)
    ctrl = _generate(pts, u, t1, t2)
    err, split = _max_err(pts, ctrl, u)
    if err < tol:
        return [ctrl]
    if err < tol * 6:
        for _ in range(4):
            u = _reparam(ctrl, pts, u)
            ctrl = _generate(pts, u, t1, t2)
            err, split = _max_err(pts, ctrl, u)
            if err < tol:
                return [ctrl]
    split = min(max(split, 1), len(pts) - 2)
    if depth > 24:
        return [ctrl]
    tc = _unit(pts[split - 1] - pts[split + 1])
    return fit_cubic(pts[:split + 1], t1, tc, tol, depth + 1) + fit_cubic(pts[split:], -tc, t2, tol, depth + 1)


# ---------------------------------------------------------------- cadena -> segmentos
def _resample(pts, step=1.0):
    """Puntos equiespaciados por longitud de arco (mantiene los extremos)."""
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    if d[-1] < step * 2:
        return pts
    n = max(int(round(d[-1] / step)), 2)
    s = np.linspace(0, d[-1], n + 1)
    return np.stack([np.interp(s, d, pts[:, 0]), np.interp(s, d, pts[:, 1])], 1)


def _kernel(sigma):
    k = int(max(1, round(sigma * 2.5)))
    ker = np.exp(-0.5 * (np.arange(-k, k + 1) / sigma) ** 2)
    return k, ker / ker.sum()


def _smooth_open(pts, sigma):
    """Suavizado gaussiano con los extremos fijos (reflexión puntual respecto a cada extremo)."""
    n = len(pts)
    if n < 5 or sigma <= 0:
        return pts
    k, ker = _kernel(sigma)
    k = min(k, n - 1)
    ker = ker[len(ker) // 2 - k: len(ker) // 2 + k + 1]
    ker = ker / ker.sum()
    pre = 2 * pts[0] - pts[1:k + 1][::-1]
    post = 2 * pts[-1] - pts[-k - 1:-1][::-1]
    ext = np.vstack([pre, pts, post])
    out = np.stack([np.convolve(ext[:, i], ker, mode="valid") for i in range(2)], 1)
    out[0], out[-1] = pts[0], pts[-1]
    return out


def _smooth_closed(pts, sigma):
    n = len(pts)
    if n < 8 or sigma <= 0:
        return pts
    k, ker = _kernel(sigma)
    k = min(k, n // 2 - 1)
    ker = ker[len(ker) // 2 - k: len(ker) // 2 + k + 1]
    ker = ker / ker.sum()
    ext = np.vstack([pts[-k:], pts, pts[:k]])
    return np.stack([np.convolve(ext[:, i], ker, mode="valid") for i in range(2)], 1)


def find_corners(pts, closed, angle_deg=60.0, w=5):
    """Índices de esquinas: giro local (vectores a ±w puntos) mayor que el ángulo y máximo local."""
    n = len(pts)
    if n < 2 * w + 1:
        return []
    idx = np.arange(n)
    if closed:
        a, b = pts[(idx - w) % n], pts[(idx + w) % n]
    else:
        a, b = pts[np.clip(idx - w, 0, n - 1)], pts[np.clip(idx + w, 0, n - 1)]
    v1, v2 = pts - a, b - pts
    n1, n2 = np.linalg.norm(v1, axis=1), np.linalg.norm(v2, axis=1)
    cosang = np.sum(v1 * v2, axis=1) / np.maximum(n1 * n2, 1e-9)
    turn = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
    if not closed:
        turn[:w] = 0
        turn[-w:] = 0
    corners = []
    for i in np.argsort(-turn):
        if turn[i] < angle_deg:
            break
        if all((abs(i - c) if not closed else min(abs(i - c), n - abs(i - c))) > w for c in corners):
            corners.append(int(i))
    return sorted(corners)


def _dev_max(part):
    chord = part[-1] - part[0]
    cl = np.linalg.norm(chord)
    if cl == 0:
        return 1e9
    return float((np.abs(chord[0] * (part[:, 1] - part[0, 1]) - chord[1] * (part[:, 0] - part[0, 0])) / cl).max())


def _fit_part(part, tol, sigma, t_start=None, t_end=None, fixed_ends=True, prims=False):
    if len(part) < 2:
        return []
    if _dev_max(part) < tol * 0.9:
        return [("L", part[0].copy(), part[-1].copy())]
    arc = primitives.fit_arc(part, tol) if prims else None
    sm = _smooth_open(part, sigma) if fixed_ends else part
    if len(sm) < 3:
        return [("L", sm[0].copy(), sm[-1].copy())]
    k = min(4, len(sm) - 1)
    t1 = t_start if t_start is not None else _unit(sm[k] - sm[0])
    t2 = t_end if t_end is not None else _unit(sm[-1 - k] - sm[-1])
    out = []
    for c in fit_cubic(sm, t1, t2, tol):
        out.append(("C", c[0], c[1], c[2], c[3]))
    if arc and len(arc) <= len(out):        # el arco exacto solo se acepta si no usa más nodos
        return arc
    return out


def fit_polyline(pts, tol=0.8, angle_deg=60.0, sigma=1.6, step=1.0, prims=False):
    """Cadena abierta (extremos fijos): esquinas + Schneider."""
    pts = np.asarray(pts, float)
    raw = _resample(pts, step) if len(pts) > 3 else pts
    corners = find_corners(raw, False, angle_deg, w=max(3, min(6, len(raw) // 6)))
    cuts = [0] + corners + [len(raw) - 1]
    segs = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        segs += _fit_part(raw[a:b + 1], tol, sigma, prims=prims)
    return segs


def fit_closed(pts, tol=0.8, angle_deg=60.0, sigma=1.6, step=1.0, prims=False):
    """Cadena cerrada sin nodos: se corta en las esquinas o, si no hay, en dos mitades con tangentes continuas."""
    pts = np.asarray(pts, float)
    raw = _resample(pts, step)[:-1] if len(pts) > 8 else pts[:-1]
    n = len(raw)
    if n < 8:
        return fit_polyline(pts, tol, angle_deg, sigma, step, prims)
    prim = None
    if prims:
        for fn in (primitives.fit_closed_circle, primitives.fit_closed_ellipse):
            prim = fn(raw, tol)
            if prim:
                break
    base = _closed_core(raw, n, tol, angle_deg, sigma, prims)
    if prim and len(prim) <= len(base) + 2:      # geometría exacta a cambio de, como mucho, 2 nodos más
        return prim
    return base


def _closed_core(raw, n, tol, angle_deg, sigma, prims):
    corners = find_corners(raw, True, angle_deg, w=max(3, min(6, n // 8)))
    sm = _smooth_closed(raw, sigma)
    for c in corners:
        sm[c] = raw[c]
    cuts = corners if len(corners) >= 2 else ([corners[0], (corners[0] + n // 2) % n] if corners else [0, n // 2])
    segs = []
    for i, a in enumerate(cuts):
        b = cuts[(i + 1) % len(cuts)]
        idx = list(range(a, b + 1)) if b > a else list(range(a, n)) + list(range(0, b + 1))
        part = sm[idx]
        ta = _unit(sm[(a + 2) % n] - sm[(a - 2) % n]) if a not in corners else None
        tb = _unit(sm[(b - 2) % n] - sm[(b + 2) % n]) if b not in corners else None
        segs += _fit_part(part, tol, 0.0, ta, tb, fixed_ends=False, prims=prims)
    return segs


def seg_reverse(seg):
    if seg[0] == "L":
        return ("L", seg[2], seg[1])
    return ("C", seg[4], seg[3], seg[2], seg[1])


def seg_points(seg, n=8):
    """Puntos de muestreo de un segmento (para áreas, errores y renders)."""
    if seg[0] == "L":
        return np.array([seg[1], seg[2]])
    t = np.linspace(0, 1, n)
    return _bez(np.array(seg[1:]), t)
