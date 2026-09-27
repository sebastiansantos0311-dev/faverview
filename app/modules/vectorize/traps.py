"""Trap vectorial exacto (AUTOTRAP T4): a partir de las fronteras compartidas del vectorizador.

Cada cadena separa exactamente dos regiones A|B. Se decide con las reglas de tools/trapping (R1–R6) y se emite un trazo del
color de la tinta que se expande, de ancho 2 × trap, centrado en la frontera, en sobreimpresión y recortado a A ∪ B.
En el trap centrado (R5) salen dos trazos de ancho = trap, uno por tinta. R7 (retracción) y R8/R9 no se aplican en vectorial."""
from app.core import colorscience as cs
from app.core.errors import UserError
from app.core.press import PressProfile
from app.modules.tools import trapping

PAPER = (95.0, 0.0, -2.0)
PAPER_DE = 10.0
LAYER = "Traps FAVERVIEW"
MARGEN_MM = 0.03            # margen de seguridad sobre la tolerancia (antialias del render y redondeos de la verificación)


def is_paper(lab) -> bool:
    return float(cs.delta_e2000(lab, PAPER)) < PAPER_DE


def paper_labels(res) -> set[int]:
    return {i for i, ink in enumerate(res.palette) if is_paper(ink.lab)}


def build(res, press: PressProfile, mm_per_px: float | None) -> list[dict]:
    """Grupos de traps: [{"par": (a, b), "trazos": [{"color": etiqueta, "segs": [...], "ancho_px": w, "regla": "R4"}]}]."""
    if not mm_per_px:
        raise UserError("Para el trap vectorial indica el tamaño final en mm (o usa una imagen con ppi).")
    if max(press.tol_xy()) <= 0:
        return []
    paper = paper_labels(res)
    info = {str(i): (float(ink.lab[0]), "spot", float(getattr(ink, "opacity", 0.0))) for i, ink in enumerate(res.palette)}
    trap_mm = press.trap_mm()
    groups: dict[tuple, dict] = {}
    for left, right, segs in res.edges:
        if left < 0 or right < 0 or left in paper or right in paper or left == right:
            continue
        for de, bajo, f, regla in trapping.decide(str(left), str(right), info, press):
            w = 2 * (trap_mm * f + MARGEN_MM * f) / mm_per_px     # ancho del trazo: 2 × trap (o el trap si es centrado), con margen
            g = groups.setdefault(tuple(sorted((left, right))), {"par": tuple(sorted((left, right))), "trazos": []})
            g["trazos"].append({"color": int(de), "bajo": int(bajo), "segs": segs, "ancho_px": w, "regla": regla})
    return list(groups.values())


def summary(groups: list[dict], mm_per_px: float) -> list[dict]:
    """Resumen legible: por par de regiones, qué tinta se expande y cuánto."""
    out = []
    for g in groups:
        by = {}
        for t in g["trazos"]:
            key = (t["color"], t["bajo"], t["regla"])
            by.setdefault(key, [0, t["ancho_px"] * mm_per_px])
            by[key][0] += 1
        for (de, bajo, regla), (n, w) in by.items():
            out.append({"de": de, "bajo": bajo, "regla": regla, "cadenas": n, "ancho_trazo_mm": round(w, 3)})
    return out
