"""Braille español grado 1 con tabla propia + geometría Marburg Medium configurable (S7 §11.4).

liblouis no se usa (no hay una compilación fiable para Windows): la tabla propia está documentada aquí. Los valores de la
geometría son los habituales de Marburg Medium (uso farmacéutico, EN 15823) y son configurables: VERIFÍCALOS con la norma o con
tu proveedor de troquelado antes de producir. La zona de pliegues y solapas debe quedar libre de braille."""
import io
import math

import pikepdf

from app.core.errors import UserError
from app.core.units import mm_to_pt

# Puntos de la celda braille (numeración estándar 1-2-3 columna izquierda, 4-5-6 derecha).
LETTERS = {
    "a": (1,), "b": (1, 2), "c": (1, 4), "d": (1, 4, 5), "e": (1, 5), "f": (1, 2, 4), "g": (1, 2, 4, 5), "h": (1, 2, 5),
    "i": (2, 4), "j": (2, 4, 5), "k": (1, 3), "l": (1, 2, 3), "m": (1, 3, 4), "n": (1, 3, 4, 5), "o": (1, 3, 5), "p": (1, 2, 3, 4),
    "q": (1, 2, 3, 4, 5), "r": (1, 2, 3, 5), "s": (2, 3, 4), "t": (2, 3, 4, 5), "u": (1, 3, 6), "v": (1, 2, 3, 6),
    "w": (2, 4, 5, 6), "x": (1, 3, 4, 6), "y": (1, 3, 4, 5, 6), "z": (1, 3, 5, 6),
    "ñ": (1, 2, 4, 5, 6), "á": (1, 2, 3, 5, 6), "é": (2, 3, 4, 6), "í": (3, 4), "ó": (3, 4, 6), "ú": (2, 3, 4, 5, 6), "ü": (1, 2, 5, 6),
}
DIGITS = dict(zip("1234567890", [LETTERS[c] for c in "abcdefghij"]))
CAPITAL = (6,)
NUMERIC = (3, 4, 5, 6)
PUNCT = {",": (2,), ".": (3,), ";": (2, 3), ":": (2, 5), "-": (3, 6), "?": (2, 6), "¿": (2, 6), "!": (2, 3, 5), "¡": (2, 3, 5),
         "(": (2, 3, 6), ")": (3, 5, 6), "/": (3, 4), "%": (4, 5, 6)}
UNICODE_BASE = 0x2800


def cell_char(dots) -> str:
    return chr(UNICODE_BASE + sum(1 << (d - 1) for d in dots))


def translate(text: str) -> list[tuple]:
    """Texto → lista de celdas (tuplas de puntos; () = espacio). Mayúscula: signo de dot 6 (dos veces si la palabra está toda en mayúsculas)."""
    cells: list[tuple] = []
    words = text.split(" ")
    for wi, word in enumerate(words):
        if wi:
            cells.append(())
        letters = [c for c in word if c.isalpha()]
        all_caps = len(letters) > 1 and all(c.isupper() for c in letters)
        if all_caps:
            cells += [CAPITAL, CAPITAL]
        in_number = False
        for ch in word:
            low = ch.lower()
            if ch.isdigit():
                if not in_number:
                    cells.append(NUMERIC)
                    in_number = True
                cells.append(DIGITS[ch])
                continue
            if in_number and ch not in ".,":
                in_number = False
            if low in LETTERS:
                if ch.isupper() and not all_caps:
                    cells.append(CAPITAL)
                cells.append(LETTERS[low])
            elif ch in PUNCT:
                cells.append(PUNCT[ch])
            else:
                raise UserError(f"El carácter «{ch}» no está en la tabla de braille grado 1 de FAVERVIEW.")
    return cells


def to_unicode(text: str) -> str:
    return "".join(" " if not c else cell_char(c) for c in translate(text))


# Marburg Medium (mm) — configurable
MARBURG = {"diametro": 1.6, "punto_x": 2.5, "punto_y": 2.5, "celda": 6.0, "linea": 10.0}
DOT_POS = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2)}


def layout(text: str, max_width_mm: float = 60.0, geometria: dict | None = None) -> dict:
    """Puntos en mm (origen arriba-izquierda) con salto de línea por palabras."""
    g = {**MARBURG, **(geometria or {})}
    cells = translate(text)
    per_line = max(int((max_width_mm + (g["celda"] - g["punto_x"])) // g["celda"]), 1)
    # partir por palabras (los espacios son celdas vacías)
    lines, cur = [], []
    words, w = [], []
    for c in cells + [()]:
        if c == ():
            words.append(w)
            w = []
        else:
            w.append(c)
    line: list = []
    for wd in words:
        need = len(wd) + (1 if line else 0)
        if line and len(line) + need > per_line:
            lines.append(line)
            line = []
        if line:
            line.append(())
        if len(wd) > per_line:
            raise UserError(f"La palabra de {len(wd)} celdas no cabe en {max_width_mm:g} mm (máximo {per_line} celdas por línea).")
        line += wd
    if line:
        lines.append(line)
    dots = []
    for li, line in enumerate(lines):
        for ci, cell in enumerate(line):
            for d in cell:
                col, row = DOT_POS[d]
                dots.append((ci * g["celda"] + col * g["punto_x"] + g["diametro"] / 2, li * g["linea"] + row * g["punto_y"] + g["diametro"] / 2))
    width = (max(len(l) for l in lines) - 1) * g["celda"] + g["punto_x"] + g["diametro"] if lines else 0
    height = (len(lines) - 1) * g["linea"] + 2 * g["punto_y"] + g["diametro"] if lines else 0
    return {"puntos": dots, "ancho_mm": round(width, 2), "alto_mm": round(height, 2), "lineas": len(lines), "celdas": sum(len(l) for l in lines),
            "unicode": "\n".join("".join(" " if not c else cell_char(c) for c in l) for l in lines), "diametro": g["diametro"],
            "avisos": ["Verifica las dimensiones con la norma (Marburg Medium, EN 15823) o con tu proveedor.",
                       "Mantén el braille alejado de pliegues, solapas y bordes de corte."]}


def to_svg(lay: dict, color: str = "#000") -> str:
    r = lay["diametro"] / 2
    circles = "".join(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r:.3f}"/>' for x, y in lay["puntos"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{lay["ancho_mm"]}mm" height="{lay["alto_mm"]}mm" '
            f'viewBox="0 0 {lay["ancho_mm"]} {lay["alto_mm"]}" fill="{color}">{circles}</svg>')


def to_pdf(lay: dict, ink_name: str = "Braille", ink_cmyk=(0, 0, 0, 1), overprint: bool = True) -> bytes:
    """PDF vectorial: un círculo (4 Bézier) por punto en la tinta técnica «Braille», con sobreimpresión."""
    pdf = pikepdf.new()
    wp, hp = mm_to_pt(lay["ancho_mm"]), mm_to_pt(lay["alto_mm"])
    page = pdf.add_blank_page(page_size=(max(wp, 10), max(hp, 10)))
    fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=list(ink_cmyk), N=1)
    res = pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(CS0=pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + ink_name.replace(" ", "_")),
                                                                              pikepdf.Name.DeviceCMYK, fn])))
    if overprint:
        res["/ExtGState"] = pikepdf.Dictionary(GS0=pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1))
    ops = (["/GS0 gs"] if overprint else []) + ["/CS0 cs 1 scn"]
    k = 0.5522847498
    r = mm_to_pt(lay["diametro"] / 2)
    for x, y in lay["puntos"]:
        cx, cy = mm_to_pt(x), hp - mm_to_pt(y)
        ops.append(f"{cx + r:.3f} {cy:.3f} m {cx + r:.3f} {cy + k * r:.3f} {cx + k * r:.3f} {cy + r:.3f} {cx:.3f} {cy + r:.3f} c "
                   f"{cx - k * r:.3f} {cy + r:.3f} {cx - r:.3f} {cy + k * r:.3f} {cx - r:.3f} {cy:.3f} c "
                   f"{cx - r:.3f} {cy - k * r:.3f} {cx - k * r:.3f} {cy - r:.3f} {cx:.3f} {cy - r:.3f} c "
                   f"{cx + k * r:.3f} {cy - r:.3f} {cx + r:.3f} {cy - k * r:.3f} {cx + r:.3f} {cy:.3f} c f")
    page.Resources = res
    page.Contents = pdf.make_stream("\n".join(ops).encode())
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()
