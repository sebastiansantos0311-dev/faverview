"""Alineación del arte del cliente (A) sobre el diseño (B) con ORB + homografía."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class AlignResult:
    aligned_client: np.ndarray
    homography: np.ndarray | None
    alignment_quality: float
    aligned: bool
    warning: str | None = None


def _resize_to(img: np.ndarray, w: int, h: int) -> np.ndarray:
    interp = cv2.INTER_AREA if img.shape[1] > w else cv2.INTER_CUBIC
    return cv2.resize(img, (w, h), interpolation=interp)


def align_images(design: np.ndarray, client: np.ndarray) -> AlignResult:
    h, w = design.shape[:2]
    ch, cw = client.shape[:2]
    # 1. Escalar A al ancho de B manteniendo proporción
    new_h = max(1, round(ch * w / cw))
    scaled = _resize_to(client, w, new_h)
    fallback_img = _resize_to(client, w, h)

    warn = None
    if abs(new_h - h) / h > 0.03:
        warn = ("Las proporciones del arte del cliente y del diseño son distintas; "
                "los resultados pueden ser poco confiables.")

    def fail(msg):
        return AlignResult(fallback_img, None, 0.0, False, warn or msg)

    g_d = cv2.cvtColor(design, cv2.COLOR_RGB2GRAY)
    g_c = cv2.cvtColor(scaled, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(nfeatures=5000)
    kp_c, des_c = orb.detectAndCompute(g_c, None)
    kp_d, des_d = orb.detectAndCompute(g_d, None)

    if des_c is None or des_d is None or len(kp_c) < 15 or len(kp_d) < 15:
        return fail("No se pudo alinear automáticamente (pocos rasgos detectados); "
                    "se usó solo el reescalado.")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    good = []
    for pair in matcher.knnMatch(des_c, des_d, k=2):
        if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
            good.append(pair[0])
    if len(good) < 15:
        return fail("No se pudo alinear automáticamente (pocas coincidencias); "
                    "se usó solo el reescalado.")

    src = np.float32([kp_c[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_d[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None or inl is None:
        return fail("No se pudo calcular la alineación; se usó solo el reescalado.")
    quality = float(inl.sum()) / len(good)
    if inl.sum() < 12 or quality < 0.3:
        return fail("La alineación no es confiable; se usó solo el reescalado.")

    corners = np.float32([[0, 0], [w, 0], [w, new_h], [0, new_h]]).reshape(-1, 1, 2)
    moved = cv2.perspectiveTransform(corners, H).reshape(-1, 2).astype(np.float32)
    area = cv2.contourArea(moved)
    if not cv2.isContourConvex(moved) or not 0.5 < area / float(w * new_h) < 2.0:
        return fail("La alineación calculada es inválida; se usó solo el reescalado.")

    disp = np.abs(moved - corners.reshape(-1, 2)).max()
    if disp < 1.0 and new_h == h:
        return AlignResult(scaled, H, quality, True, warn)

    warped = cv2.warpPerspective(scaled, H, (w, h), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return AlignResult(warped, H, quality, True, warn)
