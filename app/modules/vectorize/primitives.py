"""Primitivas geométricas (S5 §9): arcos, círculos y elipses ajustados a las cadenas, emitidos como Bézier exactas."""
import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

KAPPA = 0.5522847498


def fit_circle(pts):
    """Círculo por mínimos cuadrados (Kåsa) refinado con la distancia geométrica. Devuelve (cx, cy, r)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.c_[x, y, np.ones(len(x))]
    b = -(x ** 2 + y ** 2)
    try:
        c = np.linalg.lstsq(A, b, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    cx, cy = -c[0] / 2, -c[1] / 2
    r2 = cx ** 2 + cy ** 2 - c[2]
    if r2 <= 0:
        return None
    r = float(np.sqrt(r2))
    if r > 1e5:
        return None
    sol = least_squares(lambda p: np.hypot(x - p[0], y - p[1]) - p[2], [cx, cy, r], method="lm", max_nfev=30)
    return float(sol.x[0]), float(sol.x[1]), float(abs(sol.x[2]))


def arc_cubics(cx, cy, r, a0, sweep):
    """Cubicas ("C", p0, c1, c2, p1) que cubren `sweep` rad desde `a0` (trozos de ≤ 90°)."""
    n = max(1, int(np.ceil(abs(sweep) / (np.pi / 2) - 1e-9)))
    d = sweep / n
    k = 4 / 3 * np.tan(d / 4)
    out = []
    for i in range(n):
        t0 = a0 + i * d
        t1 = t0 + d
        p0 = np.array([cx + r * np.cos(t0), cy + r * np.sin(t0)])
        p3 = np.array([cx + r * np.cos(t1), cy + r * np.sin(t1)])
        c1 = p0 + k * r * np.array([-np.sin(t0), np.cos(t0)])
        c2 = p3 - k * r * np.array([-np.sin(t1), np.cos(t1)])
        out.append(["C", p0, c1, c2, p3])
    return out


def fit_arc(part, tol, min_sweep_deg=8.0):
    """Arco de circunferencia para una cadena abierta (extremos fijos) o None si no encaja dentro de `tol`."""
    if len(part) < 8:
        return None
    circ = fit_circle(part)
    if circ is None:
        return None
    cx, cy, r = circ
    err = np.abs(np.hypot(part[:, 0] - cx, part[:, 1] - cy) - r).max()
    if err > tol * 0.8:
        return None
    ang = np.unwrap(np.arctan2(part[:, 1] - cy, part[:, 0] - cx))
    sweep = float(ang[-1] - ang[0])
    if abs(np.degrees(sweep)) < min_sweep_deg or abs(sweep) > 2 * np.pi * 0.95 or np.any(np.diff(np.sign(np.diff(ang))) != 0):
        return None
    segs = arc_cubics(cx, cy, r, float(ang[0]), sweep)
    segs[0][1] = part[0].copy()
    segs[-1][4] = part[-1].copy()
    return [tuple(s) for s in segs]


def fit_closed_circle(pts, tol):
    """Cadena cerrada que es un círculo: 4 cúbicas. None si no lo es."""
    p = pts[:-1] if np.allclose(pts[0], pts[-1]) else pts
    circ = fit_circle(p)
    if circ is None:
        return None
    cx, cy, r = circ
    if np.abs(np.hypot(p[:, 0] - cx, p[:, 1] - cy) - r).max() > tol:
        return None
    a0 = float(np.arctan2(p[0, 1] - cy, p[0, 0] - cx))
    d = np.arctan2(p[len(p) // 4, 1] - cy, p[len(p) // 4, 0] - cx) - a0
    sign = 1.0 if np.sin(d) >= 0 else -1.0
    segs = arc_cubics(cx, cy, r, a0, sign * 2 * np.pi)
    return [tuple(s) for s in segs]


def fit_closed_ellipse(pts, tol):
    p = pts[:-1] if np.allclose(pts[0], pts[-1]) else pts
    if len(p) < 12:
        return None
    (cx, cy), (w, h), ang = cv2.fitEllipse(p.astype(np.float32))
    a, b = w / 2, h / 2
    if min(a, b) < 2:
        return None
    t = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    th = np.radians(ang)
    ex = cx + a * np.cos(t) * np.cos(th) - b * np.sin(t) * np.sin(th)
    ey = cy + a * np.cos(t) * np.sin(th) + b * np.sin(t) * np.cos(th)
    d, _ = cKDTree(np.c_[ex, ey]).query(p)
    if d.max() > tol:
        return None
    # 4 cúbicas de la circunferencia unidad transformadas
    base = arc_cubics(0.0, 0.0, 1.0, 0.0, 2 * np.pi)
    M = np.array([[a * np.cos(th), -b * np.sin(th)], [a * np.sin(th), b * np.cos(th)]])
    out = []
    for s in base:
        out.append(("C",) + tuple(M @ q + np.array([cx, cy]) for q in s[1:]))
    return out
