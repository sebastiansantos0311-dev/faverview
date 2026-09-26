"""Trapping (reventado) por placas raster (S7 §11.1). Enfoque explicable: la tinta más clara se expande bajo la más oscura.

El trapping vectorial queda fuera de alcance. Estimación orientativa: confirma con una prueba de imprenta."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core import inks as inkmod
from app.core.errors import UserError
from app.modules.separate.pdf_render import PROCESS, Plates

# ancho del trap por proceso (mm)
WIDTHS_MM = {"flexo": 0.15, "offset": 0.08, "serigrafia": 0.25}
DARK_L = 25.0           # las tintas más oscuras que esto no se expanden (negro y similares)
SOLID = 0.5             # solo se trapea entre zonas con al menos este % de tinta (los degradados que se tocan no se trapean)


@dataclass
class TrapResult:
    plates: Plates
    trap_map: np.ndarray                     # RGB: en color de la tinta que se expande, solo donde hay trap
    traps: list = field(default_factory=list)      # [{de, bajo, ancho_mm, pixeles}]
    warnings: list = field(default_factory=list)


def _lab_of(name: str, meta: dict):
    m = meta.get(name) or {}
    if m.get("lab"):
        return tuple(m["lab"])
    ref = {i.name: i for i in inkmod.builtin_library().inks}.get(name)
    return tuple(ref.lab) if ref and ref.lab else (50.0, 0.0, 0.0)


def _kind(name: str, meta: dict) -> str:
    return (meta.get(name) or {}).get("tipo") or ("process" if name in PROCESS else "spot")


def _disk(r: int):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def trap(plates: Plates, meta: dict | None = None, *, proceso: str = "flexo", ancho_mm: float | None = None,
         tabla: dict | None = None, porcentaje: float = 100.0, tac_max: float | None = 300.0, mantener_texto: np.ndarray | None = None,
         choke_blanco_mm: float | None = None) -> TrapResult:
    """Devuelve placas con trapping.

    `tabla`: {("Cyan", "Magenta"): mm} para sobrescribir el ancho de un par (A se expande bajo B).
    `porcentaje`: 100 = trap completo; 50 = reducido. `tac_max`: tope de cobertura total en la zona del trap.
    `mantener_texto`: máscara bool (H, W) de zonas donde no se trapea (texto pequeño)."""
    meta = meta or {}
    if proceso not in WIDTHS_MM and ancho_mm is None:
        raise UserError("Proceso desconocido (flexo, offset o serigrafia).")
    base_mm = ancho_mm if ancho_mm is not None else WIDTHS_MM[proceso]
    px_mm = plates.dpi / 25.4
    arrays = {n: a.copy() for n, a in plates.arrays.items()}
    names = [n for n in plates.names if not plates.empty(n)]
    info = {n: (_lab_of(n, meta)[0], _kind(n, meta)) for n in names}
    # fondo del mapa: el trabajo en gris muy claro para ver dónde caen los traps; los traps se resaltan encima
    ink = np.max([plates.arrays[n] for n in names], axis=0) if names else np.zeros((plates.height, plates.width), np.uint8)
    base = np.repeat((255 - (ink.astype(np.float32) * 0.35)).astype(np.uint8)[..., None], 3, axis=2)
    out = TrapResult(Plates(plates.names, arrays, plates.dpi, plates.page, plates.width, plates.height, list(plates.warnings), plates.key), base)
    factor = max(min(porcentaje, 100.0), 0.0) / 100.0
    solid = {n: plates.arrays[n] >= 255 * SOLID for n in names}
    keep = mantener_texto if mantener_texto is not None else None
    for a in names:
        La, ka = info[a]
        if ka in ("varnish", "technical") or La < DARK_L or a == "Black":
            continue                                    # negro, barniz y tintas técnicas nunca se expanden
        if ka == "white":
            continue                                    # el blanco solo se contrae (choke)
        for b in names:
            if a == b:
                continue
            Lb, kb = info[b]
            if kb in ("varnish", "technical", "white") or La <= Lb + 5.0:
                continue                                # A solo se expande bajo una tinta claramente más oscura
            mm = (tabla or {}).get((a, b), base_mm)
            r = max(int(round(mm * px_mm)), 1)
            grown = cv2.dilate(arrays[a] * 0 + (solid[a].astype(np.uint8) * 255), _disk(r)) > 0
            zone = grown & solid[b] & ~solid[a]
            if keep is not None:
                zone &= ~keep
            if not zone.any():
                continue
            # cobertura de la zona del trap: la de A en su borde (dilatación en escala de grises), por el porcentaje elegido
            val = cv2.dilate(plates.arrays[a], _disk(r)).astype(np.float32) * factor
            if tac_max:
                total = sum(arrays[n].astype(np.float32) for n in names if n != a) / 255 * 100
                room = np.maximum(tac_max - total, 0) / 100 * 255
                val = np.minimum(val, room)
            new = np.where(zone, np.maximum(arrays[a], val.astype(np.uint8)), arrays[a])
            changed = int((new != arrays[a]).sum())
            if changed:
                arrays[a] = new
                from app.core import colorscience as cs
                rgb = np.clip(np.rint(np.asarray(cs.lab_to_srgb(_lab_of(a, meta))) * 255), 0, 255).astype(np.uint8)
                grown = cv2.dilate((new != plates.arrays[a]).astype(np.uint8), _disk(2)) > 0      # engrosado solo para verlo
                out.trap_map[grown] = rgb
                out.traps.append({"de": a, "bajo": b, "ancho_mm": round(mm, 3), "pixeles": changed})
    # choke del blanco
    for w in names:
        if info[w][1] == "white":
            mm = choke_blanco_mm if choke_blanco_mm is not None else min(base_mm, 0.2)
            r = max(int(round(mm * px_mm)), 1)
            arrays[w] = cv2.erode(arrays[w], _disk(r))
            out.traps.append({"de": w, "bajo": "(choke)", "ancho_mm": round(mm, 3), "pixeles": int((arrays[w] != plates.arrays[w]).sum())})
    if not out.traps:
        out.warnings.append("No se encontraron bordes entre tintas donde hiciera falta trapping.")
    out.warnings.append("Estimación orientativa: confirma los anchos de trap con tu imprenta.")
    return out


def misregistration(plates: Plates, name: str, dx_um: float, dy_um: float = 0.0) -> Plates:
    """Copia con la placa `name` desplazada (µm) para simular un mal registro."""
    if name not in plates.arrays:
        raise UserError("Esa tinta no existe.")
    px_mm = plates.dpi / 25.4
    M = np.float32([[1, 0, dx_um / 1000 * px_mm], [0, 1, dy_um / 1000 * px_mm]])
    arrays = dict(plates.arrays)
    arrays[name] = cv2.warpAffine(plates.arrays[name], M, (plates.width, plates.height), flags=cv2.INTER_LINEAR, borderValue=0)
    return Plates(plates.names, arrays, plates.dpi, plates.page, plates.width, plates.height, list(plates.warnings), plates.key)
