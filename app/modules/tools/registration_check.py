"""Prueba de movimiento (AUTOTRAP T2): comprueba objetivamente que la tolerancia de registro no deja filetes de sustrato.

Cada placa se desplaza, una a la vez, la tolerancia en 8 direcciones respecto de las demás (el movimiento relativo es lo
que importa). Un filete es un píxel entre dos zonas de tinta distintas que quedaba cubierto y tras el movimiento no lo está."""
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core import inks as inkmod
from app.core.press import PressProfile
from app.modules.separate.pdf_render import Plates
from app.modules.tools.trapping import SOLID, _ell, _kind

DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


@dataclass
class RegResult:
    filetes_px: int
    filetes_mm2: float
    bordes_protegidos_pct: float
    peor_par: dict | None
    tolerancia_mm: list
    factor: float
    mapa: np.ndarray
    por_tinta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"filetes_px": self.filetes_px, "filetes_mm2": round(self.filetes_mm2, 4), "bordes_protegidos_pct": round(self.bordes_protegidos_pct, 2),
                "peor_par": self.peor_par, "tolerancia_mm": self.tolerancia_mm, "factor": self.factor, "por_tinta": self.por_tinta,
                "ok": self.filetes_px == 0}


def _printing(plates: Plates, meta: dict) -> list[str]:
    """Tintas que cubren el sustrato (se excluyen barniz y técnicas)."""
    return [n for n in plates.names if not plates.empty(n) and _kind(n, meta) not in ("varnish", "technical")]


def check(plates: Plates, press: PressProfile, meta: dict | None = None, *, factor: float = 1.0, ignore: np.ndarray | None = None) -> RegResult:
    """`factor` multiplica la tolerancia (1 = la del perfil; 2 = el doble, para demostrar que la prueba mide algo)."""
    meta = meta or {}
    px_mm = plates.dpi / 25.4
    tx, ty = press.tol_xy()
    dx, dy = tx * factor * px_mm, ty * factor * px_mm
    names = _printing(plates, meta)
    S = {n: (plates.arrays[n] >= 255 * SOLID).astype(np.uint8) for n in names}
    h, w = plates.height, plates.width
    cnt = np.zeros((h, w), np.uint8)
    for n in names:
        cnt += S[n]
    U0 = cnt > 0
    # zona de borde entre regiones con distinta combinación de tintas, ambas entintadas
    sig = np.zeros((h, w), np.int64)
    for k, n in enumerate(names):
        sig += S[n].astype(np.int64) << k
    b = np.zeros((h, w), bool)
    dh = (sig[:, :-1] != sig[:, 1:]) & (sig[:, :-1] > 0) & (sig[:, 1:] > 0)
    b[:, :-1] |= dh
    b[:, 1:] |= dh
    dv = (sig[:-1, :] != sig[1:, :]) & (sig[:-1, :] > 0) & (sig[1:, :] > 0)
    b[:-1, :] |= dv
    b[1:, :] |= dv
    rr = int(math.ceil(max(dx, dy))) + 1
    band = cv2.dilate(b.astype(np.uint8), _ell(rr, rr)) > 0
    band &= U0
    if ignore is not None:
        band &= ~ignore
    total_band = int(band.sum())
    union_fil = np.zeros((h, w), bool)
    kern = {}
    for ux, uy in DIRS:                                   # rayos hacia ambos lados de la dirección de movimiento
        nn = math.hypot(ux, uy)
        kp = np.zeros((2 * rr + 1, 2 * rr + 1), np.uint8)
        km = kp.copy()
        for j in range(1, rr + 1):
            kp[rr + int(round(uy / nn * j)), rr + int(round(ux / nn * j))] = 1
            km[rr - int(round(uy / nn * j)), rr - int(round(ux / nn * j))] = 1
        kern[(ux, uy)] = (kp, km)
    per, worst = {}, None
    for n in names:
        others = (cnt - S[n]) > 0
        worst_n = 0
        for ux, uy in DIRS:
            nn = math.hypot(ux, uy)
            M = np.float32([[1, 0, ux / nn * dx], [0, 1, uy / nn * dy]])       # punto de la elipse de tolerancia
            moved = cv2.warpAffine(S[n], M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0) > 0
            covered = (others | moved).astype(np.uint8)
            kp, km = kern[(ux, uy)]
            # un filete es una rendija: hay tinta a ambos lados en la dirección del movimiento (no una muesca en el borde exterior)
            fil = band & (covered == 0) & (cv2.dilate(covered, kp) > 0) & (cv2.dilate(covered, km) > 0)
            c = int(fil.sum())
            union_fil |= fil
            if c > worst_n:
                worst_n = c
                if worst is None or c > worst["filetes_px"]:
                    worst = {"tinta": n, "direccion": [ux, uy], "filetes_px": c}
        per[n] = worst_n
    # se descartan los grupos de ≤ 4 píxeles (esquinas de la cuadrícula del render): no son rendijas reales
    n, lab, st, _ = cv2.connectedComponentsWithStats(union_fil.astype(np.uint8), connectivity=8)
    small = np.flatnonzero((st[:, cv2.CC_STAT_AREA] <= 4) & (np.maximum(st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT]) <= 3))
    small = small[small != 0]
    if len(small):
        union_fil &= ~np.isin(lab, small)
    npx = int(union_fil.sum())
    ink = np.max([plates.arrays[n] for n in names], axis=0) if names else np.zeros((h, w), np.uint8)
    g = (255 - ink.astype(np.float32) * 0.35).astype(np.uint8)
    mapa = np.repeat(g[..., None], 3, axis=2)
    mapa[cv2.dilate(union_fil.astype(np.uint8), _ell(1, 1)) > 0] = (255, 0, 200)
    prot = 100.0 if total_band == 0 else 100.0 * (1 - npx / total_band)
    return RegResult(npx, npx / (px_mm ** 2), prot, worst, [tx, ty], factor, mapa, per)


def side_by_side(before: RegResult, after: RegResult) -> np.ndarray:
    return np.hstack([before.mapa, np.full((before.mapa.shape[0], 8, 3), 255, np.uint8), after.mapa])


def moved_view(plates: Plates, meta: dict, tinta: str, ux: float, uy: float, mm: float) -> np.ndarray:
    """Vista simulada con la placa `tinta` desplazada `mm` en la dirección (ux, uy) (para el deslizador de la interfaz)."""
    from app.modules.separate.pdf_render import compose
    from app.modules.tools.trapping import shift_plate
    px = mm * plates.dpi / 25.4
    return compose(shift_plate(plates, tinta, ux * px, uy * px), meta)
