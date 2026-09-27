"""Auto-trap integrado en la separación (AUTOTRAP T3): se aplica a los canales antes del tramado y de la exportación."""
import numpy as np

from app.core import colorscience as cs
from app.core.press import PressProfile
from app.modules.separate import raster
from app.modules.separate.pdf_render import Plates
from app.modules.tools import registration_check as rc
from app.modules.tools import trapping

SUBSTRATE_DE = 10.0


def _plates(res: raster.SepResult, dpi: float) -> Plates:
    h, w = next(iter(res.channels.values())).shape
    return Plates(list(res.names), dict(res.channels), dpi, 0, w, h)


def _meta(res: raster.SepResult, substrate) -> tuple[dict, list[str]]:
    """Lab, tipo y opacidad por tinta. Un canal del color del sustrato no se imprime: no se trapea (se marca como técnico)."""
    meta, notes = {}, []
    for ink in res.palette:
        kind = "white" if ink.opacity >= 1 else "spot"
        if ink.opacity < 1 and float(cs.delta_e2000(ink.lab, substrate)) < SUBSTRATE_DE:
            kind = "technical"
            notes.append(f"«{ink.name}» se parece al sustrato: se trata como fondo sin imprimir (sin trap).")
        meta[ink.name] = {"lab": tuple(ink.lab), "tipo": kind, "opacity": ink.opacity}
    return meta, notes


def apply_raster(res: raster.SepResult, dpi: float | None, press: PressProfile, substrate=raster.PAPER, modo: str = "planas") -> raster.SepResult:
    """Reemplaza los canales de `res` por los canales con trap y anota la prueba de movimiento antes y después."""
    if modo == "indice":
        res.warnings.append("Auto-trap: el modo índice (difusión de error) no tiene bordes a tope, así que no se aplica.")
        res.stats["auto_trap"] = "no aplica"
        return res
    if modo == "cmyk":
        res.warnings.append("Auto-trap: el modo CMYK no se trapea (las tintas de proceso se superponen por naturaleza).")
        res.stats["auto_trap"] = "no aplica"
        return res
    if not dpi:
        dpi = 200.0
        res.warnings.append("La imagen no trae ppi: se asumieron 200 ppi para pasar la tolerancia de mm a píxeles.")
    plates = _plates(res, dpi)
    meta, notes = _meta(res, substrate)
    res.warnings += notes
    solo = modo == "proceso"
    if solo:
        res.warnings.append("Auto-trap en proceso simulado: solo se aplica el choke de la base blanca y las tintas opacas (el resto se superpone por naturaleza).")
    tr = trapping.trap(plates, meta, press=press, tac_max=None, solo_opacas=solo)
    res.trap = tr
    res.channels = dict(tr.plates.arrays)
    res.sim = raster.simulate(res.palette, [res.channels[i.name] for i in res.palette], substrate) if res.palette else res.sim
    if not solo:
        res.reg_before = rc.check(plates, press, meta)
        res.reg_after = rc.check(tr.plates, press, meta, ignore=tr.pullback_mask)
    res.stats["auto_trap"] = {"perfil": press.nombre, "tolerancia_mm": press.tolerancia_mm, "traps": len(tr.traps),
                              **({"filetes_mm2_antes": round(res.reg_before.filetes_mm2, 3), "filetes_mm2_despues": round(res.reg_after.filetes_mm2, 3)} if res.reg_after else {})}
    res.warnings += tr.warnings
    return res


def registro_texto(res: raster.SepResult) -> str:
    if res.reg_after is None:
        return ""
    tol = res.reg_after.tolerancia_mm
    t = f"±{tol[0]:g}" if tol[0] == tol[1] else f"±{tol[0]:g} × {tol[1]:g}"
    if res.reg_after.filetes_px == 0:
        return f"✔ Sin filetes con {t} mm"
    return f"✘ {res.reg_after.filetes_mm2:.2f} mm² de filetes con {t} mm: ver el mapa"
