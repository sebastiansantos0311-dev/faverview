"""Step & repeat / imposición y marcas dinámicas (S7 §11.2), con PyMuPDF (`show_pdf_page`: el contenido se reutiliza como
Form XObject, el archivo no crece por copia)."""
from dataclasses import dataclass
from datetime import datetime

import pikepdf
import pymupdf

from app.core.errors import UserError
from app.core.units import mm_to_pt, pt_to_mm
from app.modules.separate.pdf_inks import read_inventory
from app.modules.separate.raster_export import _alt_cmyk

PT = 72 / 25.4


@dataclass
class Cell:
    col: int
    row: int
    x: float           # mm, esquina superior izquierda del TrimBox de la etiqueta en la hoja
    y: float
    w: float
    h: float
    rot: int


def layout_cells(trim_w: float, trim_h: float, cols: int, rows: int, gap_x: float, gap_y: float, margin: tuple = (10, 10, 10, 10),
                 rot_by_row: list | None = None, rot_by_col: list | None = None, stagger_row_mm: float = 0.0,
                 stagger_col_mm: float = 0.0) -> list[Cell]:
    """Posiciones exactas (mm) de las etiquetas. `margin` = (izq, arriba, der, abajo). Las rotaciones 90/270 intercambian el ancho y el alto."""
    ml, mt = margin[0], margin[1]
    cells = []
    y = mt
    for r in range(rows):
        row_rot = (rot_by_row or [0])[r % len(rot_by_row or [0])]
        x = ml + (stagger_row_mm if r % 2 else 0.0)
        row_h = 0.0
        for c in range(cols):
            rot = (row_rot + (rot_by_col or [0])[c % len(rot_by_col or [0])]) % 360
            w, h = (trim_h, trim_w) if rot in (90, 270) else (trim_w, trim_h)
            cells.append(Cell(c, r, x, y + (stagger_col_mm if c % 2 else 0.0), w, h, rot))
            x += w + gap_x
            row_h = max(row_h, h)
        y += row_h + gap_y
    return cells


def fill_grid(sheet_w: float, sheet_h: float, trim_w: float, trim_h: float, gap_x: float, gap_y: float, margin=(10, 10, 10, 10)) -> tuple[int, int]:
    """Cuántas columnas × filas caben (opción «rellenar»)."""
    aw = sheet_w - margin[0] - margin[2]
    ah = sheet_h - margin[1] - margin[3]
    cols = max(int((aw + gap_x) // (trim_w + gap_x)), 0)
    rows = max(int((ah + gap_y) // (trim_h + gap_y)), 0)
    return cols, rows


def _ink_specs(pdf_path):
    """Tintas del trabajo (nombre exacto, alternativo CMYK) para la barra de control y los rótulos por placa."""
    inv = read_inventory(pdf_path)
    out = []
    for i in inv.inks:
        if i.kind in ("technical", "varnish") or i.name == "None":
            continue
        cmyk = i.alt_cmyk or _alt_cmyk(type("I", (), {"lab": i.lab or (50, 0, 0)})())
        out.append((i.name, tuple(cmyk), i.kind))
    return out


def _add_separation(pdf, page, key, name, cmyk):
    fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=list(cmyk), N=1)
    res = page.obj.get("/Resources")
    if res is None:
        page.obj["/Resources"] = res = pikepdf.Dictionary()
    if "/ColorSpace" not in res:
        res["/ColorSpace"] = pikepdf.Dictionary()
    res["/ColorSpace"][f"/{key}"] = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + name), pikepdf.Name.DeviceCMYK, fn])


def step_repeat(src, dst, *, sheet_w: float, sheet_h: float, cols: int | None = None, rows: int | None = None, gap_x: float = 3.0,
                gap_y: float = 3.0, margin=(10, 10, 10, 10), shared_bleed: bool = False, rot_by_row=None, rot_by_col=None,
                stagger_row_mm: float = 0.0, stagger_col_mm: float = 0.0, marks: dict | None = None, job_name: str = "",
                page: int = 0) -> dict:
    """Coloca la etiqueta en una hoja o banda. `marks`: {"registro", "corte", "barra_color", "microdots", "texto"} (bool cada una)."""
    marks = marks or {}
    with pymupdf.open(str(src)) as sdoc:
        if not 0 <= page < len(sdoc):
            raise UserError("Esa página no existe.")
        sp = sdoc[page]
        trim = pymupdf.Rect(sp.trimbox) if not pymupdf.Rect(sp.trimbox).is_empty else pymupdf.Rect(sp.rect)
        bleed = pymupdf.Rect(sp.bleedbox) if not pymupdf.Rect(sp.bleedbox).is_empty else trim
        tw, th = pt_to_mm(trim.width), pt_to_mm(trim.height)
        if cols is None or rows is None:
            cols, rows = fill_grid(sheet_w, sheet_h, tw, th, gap_x, gap_y, margin)
        if cols < 1 or rows < 1:
            raise UserError("La etiqueta no cabe en la hoja con esos márgenes y separaciones.")
        cells = layout_cells(tw, th, cols, rows, gap_x, gap_y, margin, rot_by_row or [0], rot_by_col or [0], stagger_row_mm, stagger_col_mm)
        used_w = max(c.x + c.w for c in cells)
        used_h = max(c.y + c.h for c in cells)
        if used_w > sheet_w - margin[2] + 0.01 or used_h > sheet_h - margin[3] + 0.01:
            raise UserError(f"Las {cols}×{rows} etiquetas necesitan {used_w + margin[2]:.1f} × {used_h + margin[3]:.1f} mm y la hoja es de {sheet_w:g} × {sheet_h:g} mm.")
        out = pymupdf.open()
        pg = out.new_page(width=sheet_w * PT, height=sheet_h * PT)
        bl, bt = trim.x0 - bleed.x0, trim.y0 - bleed.y0
        br, bb = bleed.x1 - trim.x1, bleed.y1 - trim.y1
        for c in cells:
            # el rectángulo destino incluye el sangrado (rotado con la etiqueta)
            x, y, w, h = c.x * PT, c.y * PT, c.w * PT, c.h * PT
            if c.rot == 0:
                dest = pymupdf.Rect(x - bl, y - bt, x + w + br, y + h + bb)
            elif c.rot == 90:
                dest = pymupdf.Rect(x - bb, y - bl, x + w + bt, y + h + br)
            elif c.rot == 180:
                dest = pymupdf.Rect(x - br, y - bb, x + w + bl, y + h + bt)
            else:
                dest = pymupdf.Rect(x - bt, y - br, x + w + bb, y + h + bl)
            pg.show_pdf_page(dest, sdoc, page, clip=bleed, rotate=-c.rot % 360, keep_proportion=True)
        specs = _ink_specs(src) if any(marks.get(k) for k in ("barra_color", "texto")) else []
        out.save(str(dst))
    # marcas con pikepdf (permiten /All y Separation con el nombre exacto de cada tinta)
    stats = {"repeticiones": len(cells), "columnas": cols, "filas": rows, "aprovechamiento_pct": round(100 * len(cells) * tw * th / (sheet_w * sheet_h), 1),
             "etiqueta_mm": [round(tw, 2), round(th, 2)]}
    if any(marks.get(k) for k in ("registro", "corte", "barra_color", "microdots", "texto")):
        _draw_marks(dst, cells, sheet_w, sheet_h, margin, marks, specs, job_name)
    return {**stats, "celdas": [c.__dict__ for c in cells]}


def _draw_marks(path, cells, sw, sh, margin, marks, specs, job):
    ops = []
    with pikepdf.open(str(path), allow_overwriting_input=True) as pdf:
        page = pdf.pages[0]
        H = sh * PT
        _add_separation(pdf, page, "FVAll", "All", (1, 1, 1, 1))
        page.obj["/Resources"]["/Font"] = pikepdf.Dictionary(F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                                                  BaseFont=pikepdf.Name.Helvetica, Encoding=pikepdf.Name.WinAnsiEncoding))

        def line(x0, y0, x1, y1):
            return f"{x0 * PT:.3f} {H - y0 * PT:.3f} m {x1 * PT:.3f} {H - y1 * PT:.3f} l S"

        if marks.get("registro"):
            ops.append("/FVAll CS 1 SCN 0.25 w")
            for (cx, cy) in ((margin[0] / 2, margin[1] / 2), (sw - margin[2] / 2, margin[1] / 2), (margin[0] / 2, sh - margin[3] / 2),
                             (sw - margin[2] / 2, sh - margin[3] / 2)):
                r = min(margin[0], margin[1], 6) * 0.35
                ops += [line(cx - r, cy, cx + r, cy), line(cx, cy - r, cx, cy + r),
                        f"{(cx + r * 0.6) * PT:.3f} {H - cy * PT:.3f} m " + f"{(cx + r * 0.6) * PT:.3f} {H - cy * PT:.3f} l"]
        if marks.get("corte"):
            ops.append("/FVAll CS 1 SCN 0.25 w")
            l = min(margin[0], margin[1], 5) * 0.8
            for c in cells:
                for (px, py, dx, dy) in ((c.x, c.y, -1, -1), (c.x + c.w, c.y, 1, -1), (c.x, c.y + c.h, -1, 1), (c.x + c.w, c.y + c.h, 1, 1)):
                    ops += [line(px + dx * 1.0, py, px + dx * (1.0 + l), py), line(px, py + dy * 1.0, px, py + dy * (1.0 + l))]
        if marks.get("microdots"):
            ops.append("/FVAll cs 1 scn")
            for c in cells:
                for (px, py) in ((c.x - 0.6, c.y - 0.6), (c.x + c.w + 0.6, c.y - 0.6), (c.x - 0.6, c.y + c.h + 0.6), (c.x + c.w + 0.6, c.y + c.h + 0.6)):
                    ops.append(f"{(px - 0.075) * PT:.3f} {H - (py + 0.075) * PT:.3f} {0.15 * PT:.3f} {0.15 * PT:.3f} re f")
        ink_i = 0
        y0 = sh - margin[3] * 0.75
        if marks.get("barra_color") and specs:
            x = margin[0]
            for name, cmyk, kind in specs:
                for pct in (1.0, 0.5):
                    key = f"FVB{ink_i}"
                    ink_i += 1
                    _add_separation(pdf, page, key, name, cmyk)
                    ops.append(f"/{key} cs {pct} scn {x * PT:.3f} {H - (y0 + 4) * PT:.3f} {4 * PT:.3f} {4 * PT:.3f} re f")
                    x += 4.5
        if marks.get("texto"):
            x = margin[0]
            date = datetime.now().strftime("%Y-%m-%d")
            ops.append(f"BT /F1 6 Tf 0 0 0 1 k {x * PT:.3f} {H - (margin[1] * 0.4) * PT:.3f} Td ({_esc(job or 'trabajo')} {date}) Tj ET")
            # el nombre de cada tinta, en esa tinta, para que solo salga en su placa
            for name, cmyk, kind in specs:
                key = f"FVT{ink_i}"
                ink_i += 1
                _add_separation(pdf, page, key, name, cmyk)
                ops.append(f"BT /{key} cs 1 scn /F1 6 Tf {(x + 70) * PT:.3f} {H - (margin[1] * 0.4) * PT:.3f} Td ({_esc(name)}) Tj ET")
                x += 25
        cont = page.obj["/Contents"]
        old = b"\n".join(x.read_bytes() for x in (cont if isinstance(cont, pikepdf.Array) else [cont]))
        page.obj["/Contents"] = pdf.make_stream(old + b"\nq\n" + "\n".join(ops).encode("latin-1", "replace") + b"\nQ")
        pdf.save(str(path) + ".tmp")
    import os
    os.replace(str(path) + ".tmp", str(path))


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
