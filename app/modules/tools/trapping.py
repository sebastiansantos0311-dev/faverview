"""Trapping (reventado) por placas raster (S7 §11.1 y AUTOTRAP T1). Motor de decisión por pares de tintas.

Reglas estándar de la industria, ORIENTATIVAS: confirma con una prueba de imprenta.
R1 técnica/barniz nunca · R2 blanco solo choke · R3 negro: la otra se expande bajo él · R4 la más clara bajo la más oscura ·
R5 luminosidad parecida: trap centrado (mitad cada una) · R6 opaca contra transparente: la transparente bajo la opaca ·
R7 negro enriquecido: retracción de CMY · R8 objetos finos: trap limitado · R9 texto pequeño sin trap ·
R10 solo entre zonas sólidas (los degradados no se trapean) · R11 tope de TAC · R12 tolerancia distinta en x e y (elíptica)."""
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core import colorscience as cs
from app.core import inks as inkmod
from app.core.errors import UserError
from app.core.press import PressProfile
from app.modules.separate.pdf_render import PROCESS, Plates

WIDTHS_MM = {"flexo": 0.15, "offset": 0.08, "serigrafia": 0.25}      # compatibilidad: ancho por proceso
DARK_L = 25.0           # más oscuras que esto: nunca se expanden (negro y similares)
SOLID = 0.5             # solo se trapea entre zonas con al menos este % de tinta (R10)
OPAQUE = 0.8
CMY = ("Cyan", "Magenta", "Yellow")


@dataclass
class TrapResult:
    plates: Plates
    trap_map: np.ndarray
    traps: list = field(default_factory=list)      # [{de, bajo, regla, ancho_mm, pixeles}]
    warnings: list = field(default_factory=list)
    press: PressProfile | None = None
    pullback_mask: np.ndarray | None = None    # zona de la retracción R7 (se excluye de la prueba de movimiento: es intencionada)


def _lab_of(name: str, meta: dict):
    m = meta.get(name) or {}
    if m.get("lab"):
        return tuple(m["lab"])
    ref = {i.name: i for i in inkmod.builtin_library().inks}.get(name)
    return tuple(ref.lab) if ref and ref.lab else (50.0, 0.0, 0.0)


def _kind(name: str, meta: dict) -> str:
    return (meta.get(name) or {}).get("tipo") or ("process" if name in PROCESS else "spot")


def _px(mm: float, px_mm: float) -> int:
    """Píxeles que cubren al menos `mm` (redondeo hacia arriba, mínimo 1 si mm > 0)."""
    return 0 if mm <= 0 else max(int(math.ceil(mm * px_mm - 1e-6)), 1)


def _ell(rx: int, ry: int):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rx + 1, 2 * ry + 1))


def _trap_kernel(rx: int, ry: int):
    """Elemento estructurante del trap: elipse de semiejes (rx + 0,5, ry + 0,5). El medio píxel extra garantiza cubrir el movimiento
    también en los bordes diagonales de la cuadrícula (una elipse de radio 1 no incluye las diagonales)."""
    ax, ay = rx + 0.5, ry + 0.5
    nx, ny = int(math.ceil(ax)), int(math.ceil(ay))
    y, x = np.mgrid[-ny:ny + 1, -nx:nx + 1]
    return ((x / ax) ** 2 + (y / ay) ** 2 <= 1.0 + 1e-9).astype(np.uint8)


def decide(a: str, b: str, info: dict, press: PressProfile, solo_opacas: bool = False) -> list[tuple]:
    """Decisión para el par: lista de (expande, bajo, fracción_del_trap, regla). Vacía = sin trap."""
    (La, ka, oa), (Lb, kb, ob) = info[a], info[b]
    if ka in ("varnish", "technical") or kb in ("varnish", "technical"):
        return []                                                       # R1
    if ka == "white" or kb == "white":
        return []                                                       # R2 (el choke se aplica aparte)
    opa, opb = oa >= OPAQUE, ob >= OPAQUE
    if opa != opb:                                                      # R6
        return [(b, a, 1.0, "R6")] if opa else [(a, b, 1.0, "R6")]
    if solo_opacas:
        return []
    da, db = La < DARK_L, Lb < DARK_L
    if da != db:                                                        # R3
        return [(b, a, 1.0, "R3")] if da else [(a, b, 1.0, "R3")]
    if abs(La - Lb) >= press.centrado_si_delta_L_menor_que and not (da and db):   # R4
        return [(a, b, 1.0, "R4")] if La > Lb else [(b, a, 1.0, "R4")]
    return [(a, b, 0.5, "R5"), (b, a, 0.5, "R5")]                       # R5: centrado


def trap(plates: Plates, meta: dict | None = None, *, press: PressProfile | None = None, proceso: str | None = None,
         ancho_mm: float | None = None, tabla: dict | None = None, porcentaje: float = 100.0, tac_max: float | None = 300.0,
         mantener_texto: np.ndarray | None = None, choke_blanco_mm: float | None = None, solo_opacas: bool = False) -> TrapResult:
    """Devuelve placas con trapping. Con `press` el ancho es tolerancia × factor; sin él se mantienen `proceso` y `ancho_mm`.

    `tabla`: {("Cyan", "Magenta"): mm} sobrescribe el ancho de un par (A se expande bajo B).
    `mantener_texto`: máscara bool de zonas donde no se trapea (texto pequeño, R9)."""
    meta = meta or {}
    if press is None:
        if proceso is None and ancho_mm is None:
            proceso = "flexo"
        if ancho_mm is None and proceso not in WIDTHS_MM:
            raise UserError("Proceso desconocido (flexo, offset o serigrafia).")
        press = PressProfile(nombre="Manual", proceso=proceso or "flexo",
                             tolerancia_mm=ancho_mm if ancho_mm is not None else WIDTHS_MM[proceso])
    px_mm = plates.dpi / 25.4
    arrays = {n: a.copy() for n, a in plates.arrays.items()}
    names = [n for n in plates.names if not plates.empty(n)]
    info = {n: (_lab_of(n, meta)[0], _kind(n, meta), float((meta.get(n) or {}).get("opacity", 1.0 if _kind(n, meta) == "white" else 0.0)))
            for n in names}
    ink = np.max([plates.arrays[n] for n in names], axis=0) if names else np.zeros((plates.height, plates.width), np.uint8)
    base = np.repeat((255 - (ink.astype(np.float32) * 0.35)).astype(np.uint8)[..., None], 3, axis=2)
    out = TrapResult(Plates(plates.names, arrays, plates.dpi, plates.page, plates.width, plates.height, list(plates.warnings), plates.key), base,
                     press=press)
    tx, ty = press.trap_xy()
    if max(tx, ty) <= 0 and not tabla:
        out.warnings.append("Tolerancia 0: no se aplica trap (por ejemplo, impresión digital).")
        return out
    factor = max(min(porcentaje, 100.0), 0.0) / 100.0
    solid = {n: plates.arrays[n] >= 255 * SOLID for n in names}
    keep = mantener_texto
    frac = press.trap_max_fraccion_objeto
    _dt: dict = {}
    _thick: dict = {}

    def dist_to(n):           # distancia (px) de cada píxel a la zona sólida de n
        if n not in _dt:
            _dt[n] = cv2.distanceTransform((~solid[n]).astype(np.uint8), cv2.DIST_L2, 3)
        return _dt[n]

    def thickness(n, r):      # grosor local (px) de la zona sólida de n
        if (n, r) not in _thick:
            dt = cv2.distanceTransform(solid[n].astype(np.uint8), cv2.DIST_L2, 3)
            wnd = int(math.ceil(r / frac)) + 2            # ventana suficiente para reconocer un objeto ancho
            _thick[(n, r)] = 2 * cv2.dilate(dt, _ell(wnd, wnd))
        return _thick[(n, r)]

    def apply(a, b, mx, my, regla, mm_override=None):
        if mm_override is not None:
            rx = ry = _px(mm_override, px_mm)
        else:
            rx, ry = _px(mx, px_mm), _px(my, px_mm)
        if rx == 0 and ry == 0:
            return
        grown = cv2.dilate(solid[a].astype(np.uint8), _trap_kernel(rx, ry)) > 0
        zone = grown & solid[b] & ~solid[a]
        if frac:
            r8 = max(rx, ry)
            # R8: objetos finos. Bajo un objeto oscuro fino (R3/R4) el trap no lo deforma (el oscuro domina): solo limita el que se expande
            th = thickness(a, r8) if regla in ("R3", "R4") else np.minimum(thickness(a, r8), thickness(b, r8))
            zone &= dist_to(a) <= np.maximum(frac * th, 1.0)
        if keep is not None:
            zone &= ~keep                                                               # R9
        if not zone.any():
            return
        val = cv2.dilate(plates.arrays[a], _trap_kernel(rx, ry)).astype(np.float32) * factor
        if tac_max:                                                                     # R11
            total = sum(arrays[n].astype(np.float32) for n in names if n != a) / 255 * 100
            val = np.minimum(val, np.maximum(tac_max - total, 0) / 100 * 255)
        new = np.where(zone, np.maximum(arrays[a], val.astype(np.uint8)), arrays[a])
        changed = int((new != arrays[a]).sum())
        if changed:
            arrays[a] = new
            rgb = np.clip(np.rint(np.asarray(cs.lab_to_srgb(_lab_of(a, meta))) * 255), 0, 255).astype(np.uint8)
            out.trap_map[cv2.dilate((new != plates.arrays[a]).astype(np.uint8), _ell(2, 2)) > 0] = rgb
            out.traps.append({"de": a, "bajo": b, "regla": regla, "ancho_mm": round(max(rx, ry) / px_mm, 3), "pixeles": changed})

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if not (cv2.dilate(solid[a].astype(np.uint8), _ell(2, 2)) & solid[b].astype(np.uint8)).any():
                continue                                                                # sin contacto
            for de, bajo, f, regla in decide(a, b, info, press, solo_opacas):
                mm_t = (tabla or {}).get((de, bajo))
                if mm_t is not None:
                    apply(de, bajo, 0, 0, "tabla", mm_override=mm_t)
                else:
                    apply(de, bajo, tx * f, ty * f, regla)          # centrado: la mitad cada una (redondeo hacia arriba)
    for w in names:                                                  # R2: choke del blanco
        if info[w][1] == "white":
            mm = choke_blanco_mm if choke_blanco_mm is not None else press.choke_mm()
            r = _px(mm, px_mm)
            if r:
                arrays[w] = cv2.erode(arrays[w], _ell(r, r))
                out.traps.append({"de": w, "bajo": "(choke)", "regla": "R2", "ancho_mm": round(r / px_mm, 3),
                                  "pixeles": int((arrays[w] != plates.arrays[w]).sum())})
    pb = press.pullback_mm()                                        # R7: negro enriquecido → retracción de CMY
    kname = next((n for n in names if n == "Black" or (info[n][1] == "process" and info[n][0] < DARK_L)), None)
    cmy = [n for n in names if n in CMY]
    if kname and cmy and pb > 0 and not solo_opacas:
        rich = solid[kname] & (sum(plates.arrays[n].astype(np.int16) for n in cmy) >= 255 * 0.3)
        if rich.any():
            r = _px(pb, px_mm)
            inner = cv2.erode(solid[kname].astype(np.uint8), _ell(r, r)) > 0
            band = solid[kname] & ~inner
            out.pullback_mask = cv2.dilate(band.astype(np.uint8), _ell(r, r)) > 0
            for n in cmy:
                cut = band & (arrays[n] > 0)
                if cut.any():
                    arrays[n] = np.where(band, 0, arrays[n]).astype(np.uint8)
                    out.traps.append({"de": n, "bajo": "(retracción bajo negro)", "regla": "R7", "ancho_mm": round(r / px_mm, 3), "pixeles": int(cut.sum())})
    if not out.traps:
        out.warnings.append("No se encontraron bordes entre tintas donde hiciera falta trapping.")
    out.warnings.append("Estimación orientativa: confirma los anchos de trap con tu imprenta.")
    return out


def shift_plate(plates: Plates, name: str, dx_px: float, dy_px: float) -> Plates:
    M = np.float32([[1, 0, dx_px], [0, 1, dy_px]])
    arrays = dict(plates.arrays)
    arrays[name] = cv2.warpAffine(plates.arrays[name], M, (plates.width, plates.height), flags=cv2.INTER_NEAREST, borderValue=0)
    return Plates(plates.names, arrays, plates.dpi, plates.page, plates.width, plates.height, list(plates.warnings), plates.key)


def misregistration(plates: Plates, name: str, dx_um: float, dy_um: float = 0.0) -> Plates:
    """Copia con la placa `name` desplazada (µm) para simular un mal registro."""
    if name not in plates.arrays:
        raise UserError("Esa tinta no existe.")
    px_mm = plates.dpi / 25.4
    M = np.float32([[1, 0, dx_um / 1000 * px_mm], [0, 1, dy_um / 1000 * px_mm]])
    arrays = dict(plates.arrays)
    arrays[name] = cv2.warpAffine(plates.arrays[name], M, (plates.width, plates.height), flags=cv2.INTER_LINEAR, borderValue=0)
    return Plates(plates.names, arrays, plates.dpi, plates.page, plates.width, plates.height, list(plates.warnings), plates.key)


def text_mask(pdf_path, page: int, plates: Plates, min_pt: float) -> np.ndarray | None:
    """R9: máscara de las zonas de texto menor de `min_pt` puntos (solo PDF)."""
    from app.modules.separate import analysis
    m = np.zeros((plates.height, plates.width), bool)
    n = 0
    for size, _, (x, y, w, h) in analysis._text_spans(pdf_path, page, plates.dpi):
        if size < min_pt:
            m[max(y - 2, 0):y + h + 2, max(x - 2, 0):x + w + 2] = True
            n += 1
    return m if n else None
