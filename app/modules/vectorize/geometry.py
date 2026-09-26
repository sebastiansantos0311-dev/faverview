"""Geometría limpia y controles de preprensa v2 (S5 §9): enderezado, simetría, trazos, texto y engrosado de detalles."""
import cv2
import numpy as np
from skimage.morphology import skeletonize

from app.modules.vectorize import fit


# ---------------------------------------------------------------- enderezado
def straighten(chains, fitted, max_deg: float = 2.0, max_shift: float = 1.5):
    """Rectas casi horizontales/verticales pasan a serlo exactamente moviendo sus nodos (compartidos, así no aparecen huecos)."""
    pos, locked = {}, {}
    for c in chains:
        pos.setdefault(c.v0, c.pts[0].copy())
        pos.setdefault(c.v1, c.pts[-1].copy())
    orig = {v: p.copy() for v, p in pos.items()}
    for c, segs in zip(chains, fitted):
        if c.closed or len(segs) != 1 or segs[0][0] != "L":
            continue
        a, b = c.v0, c.v1
        d = pos[b] - pos[a]
        L = float(np.hypot(*d))
        if L < 3:
            continue
        ang = np.degrees(np.arctan2(d[1], d[0])) % 180
        for axis, near in ((1, ang < max_deg or ang > 180 - max_deg), (0, abs(ang - 90) < max_deg)):
            if not near:
                continue
            for keep, move in ((a, b), (b, a)):
                if axis not in locked.setdefault(move, set()) and abs(pos[move][axis] - pos[keep][axis]) <= max_shift:
                    pos[move][axis] = pos[keep][axis]
                    locked[move].add(axis)
                    break
    out = []
    for c, segs in zip(chains, fitted):
        d0, d1 = pos[c.v0] - orig[c.v0], pos[c.v1] - orig[c.v1]
        if not d0.any() and not d1.any():
            out.append(segs)
            continue
        segs = list(segs)
        f, l = segs[0], segs[-1]
        if f[0] == "L":
            segs[0] = ("L", f[1] + d0, f[2])
        else:
            segs[0] = ("C", f[1] + d0, f[2] + d0, f[3], f[4])
        l = segs[-1]
        if l[0] == "L":
            segs[-1] = ("L", l[1], l[2] + d1)
        else:
            segs[-1] = ("C", l[1], l[2], l[3] + d1, l[4] + d1)
        out.append(segs)
    return out


def dedupe_segments(fitted):
    """Elimina segmentos de longitud cero (sin nodos duplicados)."""
    out = []
    for segs in fitted:
        keep = [s for s in segs if not (s[0] == "L" and np.allclose(s[1], s[2], atol=1e-6))]
        out.append(keep or segs[:1])
    return out


# ---------------------------------------------------------------- simetría
def symmetrize(labels: np.ndarray, min_iou: float = 0.97):
    """Detecta simetría vertical u horizontal del contenido y la impone (copia la mitad izquierda/superior reflejada)."""
    border = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    bg = int(np.bincount(border).argmax())
    fg = labels != bg
    if fg.sum() < 20:
        return labels, None
    ys, xs = np.where(fg)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    sub = labels[y0:y1, x0:x1]
    info, out = None, labels
    for axis, name in ((1, "vertical"), (0, "horizontal")):
        flip = np.flip(sub, axis)
        f1, f2 = sub != bg, flip != bg
        union = (f1 | f2).sum()
        iou = float(((sub == flip) & (f1 | f2)).sum() / max(union, 1))
        if iou >= min_iou and iou < 0.99999:
            half = sub.copy()
            n = sub.shape[axis]
            if axis == 1:
                half[:, n - n // 2:] = np.flip(sub[:, :n // 2], 1)
            else:
                half[n - n // 2:, :] = np.flip(sub[:n // 2, :], 0)
            out = out.copy()
            out[y0:y1, x0:x1] = half
            sub = half
            info = (info + "+" if info else "") + name
        elif iou >= 0.99999:
            info = (info + "+" if info else "") + name
    return out, info


# ---------------------------------------------------------------- trazos con grosor
def find_strokes(labels: np.ndarray, palette, min_ratio: float = 8.0, max_var: float = 0.3, max_width_px: float = 60.0):
    """Regiones alargadas de grosor casi constante y sin ramas → línea central + grosor."""
    border = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    bg = int(np.bincount(border).argmax())
    found = []
    for k in np.unique(labels):
        if k == bg:
            continue
        mask = (labels == k).astype(np.uint8)
        n, cc, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if n != 2:                                      # una sola pieza por región
            continue
        sk = skeletonize(mask > 0)
        pts = np.argwhere(sk)
        if len(pts) < 8:
            continue
        dt = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        w = 2 * dt[sk]
        mean_w = float(w.mean())
        if mean_w > max_width_px or w.std() / max(mean_w, 1e-6) > max_var or len(pts) / max(mean_w, 1) < min_ratio:
            continue
        nb = cv2.filter2D(sk.astype(np.uint8), -1, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT) - sk
        ends = np.argwhere(sk & (nb == 1))
        if len(ends) != 2 or np.any(sk & (nb > 2)):      # solo caminos simples
            continue
        path, seen, cur = [tuple(ends[0])], {tuple(ends[0])}, tuple(ends[0])
        while True:
            nxt = None
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    q = (cur[0] + dy, cur[1] + dx)
                    if (dy or dx) and 0 <= q[0] < sk.shape[0] and 0 <= q[1] < sk.shape[1] and sk[q] and q not in seen:
                        nxt = q
                        break
                if nxt:
                    break
            if not nxt:
                break
            path.append(nxt)
            seen.add(nxt)
            cur = nxt
        if len(path) < 0.9 * len(pts):
            continue
        line = np.array([(x + 0.5, y + 0.5) for y, x in path], float)
        # el ancho medido en la línea central subestima 1 px; se corrige con el área real
        width = float(mask.sum() / max(len(path), 1))
        found.append({"label": int(k), "pts": line, "width": width})
    return found


def stroke_segments(pts, tol=0.8, angle=60.0, sigma=1.6, step=1.0):
    return fit.fit_polyline(pts, tol, angle, sigma, step)


# ---------------------------------------------------------------- texto
def detect_text(rgb: np.ndarray, min_conf: int = 60) -> list[dict]:
    """Zonas de texto con Tesseract (si no está disponible devuelve lista vacía)."""
    try:
        import pytesseract
        from app.config import setup_tesseract
        setup_tesseract()
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        d = pytesseract.image_to_data(g, lang="spa+eng", config="--psm 11", output_type=pytesseract.Output.DICT)
    except Exception:
        try:
            import pytesseract
            g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            d = pytesseract.image_to_data(g, output_type=pytesseract.Output.DICT)
        except Exception:
            return []
    zones = []
    for i, t in enumerate(d["text"]):
        try:
            conf = float(d["conf"][i])
        except ValueError:
            continue
        if t.strip() and conf >= min_conf and len(t.strip()) >= 2:
            zones.append({"x": int(d["left"][i]), "y": int(d["top"][i]), "w": int(d["width"][i]), "h": int(d["height"][i]),
                          "text": t.strip(), "conf": conf})
    return zones


# ---------------------------------------------------------------- engrosar detalles finos
def thicken_thin(labels: np.ndarray, min_px: float) -> np.ndarray:
    """Los detalles de una región más finos que `min_px` se engrosan hasta ese mínimo (las regiones de primer plano ganan al fondo)."""
    if min_px < 2:
        return labels
    border = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    bg = int(np.bincount(border).argmax())
    out = labels.copy()
    k = int(np.ceil(min_px)) | 1
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    for lab in np.unique(labels):
        if lab == bg:
            continue
        m = (labels == lab).astype(np.uint8)
        thin = m & ~cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
        if thin.any():
            grown = cv2.dilate(thin, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k // 2 * 2 + 1, k // 2 * 2 + 1)))
            out[(grown > 0) & (out == bg)] = lab
    return out
