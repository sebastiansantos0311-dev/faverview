"""Distorsión flexo (S7 §11.3): compensación del alargamiento del cliché al montarlo en el cilindro.

D % = (2π · k / R) · 100, con k = espesor del cliché − espesor de la base de poliéster (según la tabla del fabricante; lo
introduce el usuario) y R = repetición (desarrollo del cilindro) en mm. También se puede introducir D % directamente."""
import math

import pymupdf

from app.core.errors import UserError
from app.core.units import mm_to_pt

NOTE = "Estimación con la fórmula estándar; confirma el factor k con la tabla de tu proveedor de clichés."


def distortion_pct(k_mm: float, repeat_mm: float) -> float:
    """D % = 2π·k / R · 100."""
    if repeat_mm <= 0:
        raise UserError("La repetición debe ser mayor que 0.")
    if k_mm < 0:
        raise UserError("El factor k no puede ser negativo.")
    return 2 * math.pi * k_mm / repeat_mm * 100.0


def apply_distortion(src, dst, pct: float, direction: str = "vertical", note: bool = True) -> dict:
    """Escala el PDF SOLO en la dirección de impresión: el arte se comprime en `pct` % (el cliché se alargará al montarlo)."""
    if direction not in ("horizontal", "vertical"):
        raise UserError("La dirección debe ser «horizontal» o «vertical».")
    if not 0 <= pct < 20:
        raise UserError("La distorsión debe estar entre 0 y 20 %.")
    f = 1.0 - pct / 100.0
    with pymupdf.open(str(src)) as sdoc:
        out = pymupdf.open()
        info = []
        strip = mm_to_pt(6) if note else 0.0
        for i, sp in enumerate(sdoc):
            r = sp.rect
            w = r.width * (f if direction == "horizontal" else 1.0)
            h = r.height * (f if direction == "vertical" else 1.0)
            pg = out.new_page(width=w, height=h + strip)
            pg.show_pdf_page(pymupdf.Rect(0, 0, w, h), sdoc, i, keep_proportion=False)
            if note:
                pg.insert_text((mm_to_pt(3), h + strip * 0.7), f"Distorsión aplicada: {pct:.2f} % en dirección {direction} (FAVERVIEW)",
                               fontsize=5.5)
            info.append({"pagina": i + 1, "antes_mm": [round(r.width / 72 * 25.4, 2), round(r.height / 72 * 25.4, 2)],
                         "despues_mm": [round(w / 72 * 25.4, 2), round(h / 72 * 25.4, 2)]})
        out.save(str(dst))
    return {"distorsion_pct": round(pct, 4), "direccion": direction, "paginas": info, "nota": NOTE}
