"""Alineación del arte del cliente (A) sobre el diseño (B).

Pasos: recorte del marco de capturas de pantalla → escala al ancho del diseño → homografía con ORB (o SIFT si
ORB no alcanza) → validación → refinamiento ECC sub-píxel. También devuelve una máscara de píxeles válidos
(los que realmente vienen del cliente y no del relleno blanco).
"""
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class AlignResult:
    aligned_client: np.ndarray
    homography: np.ndarray | None
    alignment_quality: float
    aligned: bool
    warning: str | None = None
    method: str = "reescalado"  # orb / sift / orb+ecc / sift+ecc / reescalado
    valid_mask: np.ndarray | None = None  # uint8 1 = píxel con contenido del cliente
    notes: list[str] = field(default_factory=list)

    @property
    def quality_label(self) -> str:
        if not self.aligned:
            return "mala"
        return "buena" if self.alignment_quality >= 0.6 else "regular" if self.alignment_quality >= 0.35 else "mala"


def _resize_to(img: np.ndarray, w: int, h: int) -> np.ndarray:
    interp = cv2.INTER_AREA if img.shape[1] > w else cv2.INTER_CUBIC
    return cv2.resize(img, (w, h), interpolation=interp)


# ---------------------------------------------------------------------------------- marco de capturas
def _bar_rows(img: np.ndarray, axis_rows: bool, ref_color, limit: int) -> int:
    """Cuántas líneas seguidas desde el borde son 'barra' (color casi uniforme distinto del borde del diseño)."""
    n = 0
    total = img.shape[0] if axis_rows else img.shape[1]
    for i in range(min(limit, total)):
        line = img[i] if axis_rows else img[:, i]
        med = np.median(line, axis=0)
        if np.abs(med - ref_color).max() < 40:  # se parece al borde del diseño: no es marco
            break
        frac = (np.abs(line.astype(np.int16) - med).max(axis=1) < 14).mean()
        if frac < 0.85:
            break
        n += 1
    if n:  # una barra real termina en un salto de color nítido; un degradado de luz no
        line = lambda i: np.median(img[i] if axis_rows else img[:, i], axis=0)
        after = min(total - 1, n + 2)
        if np.abs(line(n - 1) - line(after)).max() < 25:
            return 0
    return n


def strip_frame(client: np.ndarray, design: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Recorta barras uniformes en los bordes (estado del celular, barra del navegador, márgenes oscuros)."""
    H, W = client.shape[:2]
    dh, dw = design.shape[:2]
    edges = {"t": np.median(design[:3], axis=(0, 1)), "b": np.median(design[-3:], axis=(0, 1)),
             "l": np.median(design[:, :3], axis=(0, 1)), "r": np.median(design[:, -3:], axis=(0, 1))}
    lim_v, lim_h = int(0.25 * H), int(0.25 * W)
    t = _bar_rows(client, True, edges["t"], lim_v)
    b = _bar_rows(client[::-1], True, edges["b"], lim_v)
    l = _bar_rows(client, False, edges["l"], lim_h)
    r = _bar_rows(client[:, ::-1], False, edges["r"], lim_h)
    # solo cuenta si es una banda apreciable (≥ 1% de la dimensión)
    t = t if t >= 0.01 * H else 0
    b = b if b >= 0.01 * H else 0
    l = l if l >= 0.01 * W else 0
    r = r if r >= 0.01 * W else 0
    if not (t or b or l or r):
        return client, (0, 0, W, H)
    return client[t:H - b, l:W - r], (l, t, W - l - r, H - t - b)


# ---------------------------------------------------------------------------------- homografía
def _estimate(kind: str, g_c, g_d):
    """Devuelve (H, calidad, inliers) o None."""
    if kind == "orb":
        det = cv2.ORB_create(nfeatures=5000)
        norm = cv2.NORM_HAMMING
    else:
        det = cv2.SIFT_create(nfeatures=4000)
        norm = cv2.NORM_L2
    kp_c, des_c = det.detectAndCompute(g_c, None)
    kp_d, des_d = det.detectAndCompute(g_d, None)
    if des_c is None or des_d is None or len(kp_c) < 15 or len(kp_d) < 15:
        return None
    good = []
    for pair in cv2.BFMatcher(norm).knnMatch(des_c, des_d, k=2):
        if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
            good.append(pair[0])
    if len(good) < 15:
        return None
    src = np.float32([kp_c[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_d[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None or inl is None:
        return None
    return H, float(inl.sum()) / len(good), int(inl.sum())


def _valid_homography(H, w: int, h: int) -> bool:
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    moved = cv2.perspectiveTransform(corners, H).reshape(-1, 2).astype(np.float32)
    if not cv2.isContourConvex(moved):
        return False
    area = cv2.contourArea(moved) / float(w * h)
    if not 0.04 < area < 25:  # escala < 0,2 o > 5
        return False
    sides = [np.linalg.norm(moved[i] - moved[(i + 1) % 4]) for i in range(4)]
    return min(sides) > 0 and max(sides) / min(sides) < 3.0 * max(w / h, h / w, 1.0)  # sin perspectiva extrema


def _ecc_refine(design: np.ndarray, warped: np.ndarray, mask: np.ndarray):
    """Refinamiento sub-píxel a resolución reducida. Devuelve (imagen, máscara, cc) o None."""
    h, w = design.shape[:2]
    s = min(1.0, 800.0 / max(h, w))
    small = lambda im: cv2.GaussianBlur(cv2.resize(cv2.cvtColor(im, cv2.COLOR_RGB2GRAY), None, fx=s, fy=s,
                                                     interpolation=cv2.INTER_AREA), (0, 0), 1.2)
    gd, gc = small(design), small(warped)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        cc, warp = cv2.findTransformECC(gd, gc, warp, cv2.MOTION_AFFINE,
                                        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-6), None, 5)
    except cv2.error:
        return None
    if cc < 0.75 or not np.isfinite(warp).all():
        return None
    S = np.diag([s, s, 1.0])
    Hf = np.linalg.inv(S) @ np.vstack([warp, [0, 0, 1]]) @ S  # afín (6 gdl): no deforma con diferencias de contenido
    flags = cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP
    ref = cv2.warpPerspective(warped, Hf, (w, h), flags=flags, borderMode=cv2.BORDER_CONSTANT,
                              borderValue=(255, 255, 255))
    refm = cv2.warpPerspective(mask, Hf, (w, h), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    # solo se acepta si de verdad reduce la diferencia
    err0 = float(np.abs(gd.astype(np.int16) - gc).mean())
    gr = small(ref)
    err1 = float(np.abs(gd.astype(np.int16) - gr).mean())
    if err1 > err0 * 0.9:
        return None
    return ref, refm, float(cc)


def align_manual(design: np.ndarray, client: np.ndarray, pts_client, pts_design) -> AlignResult:
    """Alineación indicada por el usuario: 4 puntos equivalentes (coordenadas del cliente ORIGINAL y del diseño)."""
    h, w = design.shape[:2]
    H = cv2.getPerspectiveTransform(np.float32(pts_client), np.float32(pts_design))
    warped = cv2.warpPerspective(client, H, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(255, 255, 255))
    mask = cv2.warpPerspective(np.ones(client.shape[:2], np.uint8), H, (w, h), flags=cv2.INTER_NEAREST,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return AlignResult(warped, H, 1.0, True, None, "manual", mask, ["Alineación manual"])


def align_images(design: np.ndarray, client: np.ndarray, manual: dict | None = None) -> AlignResult:
    if manual and manual.get("client") and manual.get("design"):
        return align_manual(design, client, manual["client"], manual["design"])
    h, w = design.shape[:2]
    notes = []
    orig_shape = client.shape[:2]
    client, _crop = strip_frame(client, design)
    if client.shape[:2] != orig_shape:
        notes.append("Se recortó el marco de la captura de pantalla")
    ch, cw = client.shape[:2]

    new_h = max(1, round(ch * w / cw))
    scaled = _resize_to(client, w, new_h)
    fallback_img = _resize_to(client, w, h)
    ones = np.ones(scaled.shape[:2], np.uint8)

    warn = None
    if abs(new_h - h) / h > 0.03:
        warn = ("Las proporciones del arte del cliente y del diseño son distintas; "
                "los resultados pueden ser poco confiables.")

    def fail(msg):
        return AlignResult(fallback_img, None, 0.0, False, warn or msg, "reescalado",
                           np.ones((h, w), np.uint8), notes)

    g_d = cv2.cvtColor(design, cv2.COLOR_RGB2GRAY)
    g_c = cv2.cvtColor(scaled, cv2.COLOR_RGB2GRAY)

    chosen = None
    for kind in ("orb", "sift"):
        est = _estimate(kind, g_c, g_d)
        if est is None:
            continue
        H, quality, inliers = est
        if inliers >= 15 and quality >= 0.3 and _valid_homography(H, w, new_h):
            chosen = (kind, H, quality)
            break
        if kind == "orb":
            notes.append("ORB no alcanzó; se probó SIFT")
    if chosen is None:
        return fail("No se pudo alinear automáticamente; se usó solo el reescalado.")

    kind, H, quality = chosen
    corners = np.float32([[0, 0], [w, 0], [w, new_h], [0, new_h]]).reshape(-1, 1, 2)
    disp = np.abs(cv2.perspectiveTransform(corners, H).reshape(-1, 2) - corners.reshape(-1, 2)).max()
    if disp < 1.0 and new_h == h:
        warped, mask = scaled, ones
    else:
        warped = cv2.warpPerspective(scaled, H, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                                     borderValue=(255, 255, 255))
        mask = cv2.warpPerspective(ones, H, (w, h), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT,
                                   borderValue=0)
    method = kind
    ecc = _ecc_refine(design, warped, mask)
    if ecc is not None:
        warped, mask, _cc = ecc
        method += "+ecc"
    return AlignResult(warped, H, quality, True, warn, method, mask, notes)
