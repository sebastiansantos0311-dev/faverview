"""Exportación del vectorizador (S4 §8.1.7): SVG, PDF (tintas directas Separation o CMYK), EPS (Ghostscript) y DXF (ezdxf)."""
import io
import tempfile
from pathlib import Path

import numpy as np
import pikepdf

from app.core import ghostscript
from app.core.errors import UserError
from app.modules.separate.raster_export import _alt_cmyk
from app.modules.vectorize.fit import seg_points


def _mm_per_px(res, size_mm: float | None) -> float | None:
    """mm por unidad del vector: por el ancho final pedido o por el dpi de la imagen."""
    if size_mm:
        return size_mm / res.width
    if res.dpi:
        return 25.4 / res.dpi
    return None


def _loops(res, region):
    return [l for l in region.loops if l.outer] if res.mode == "apilado" else region.loops


def _d(loop, f=1.0, flip_h=None, prec=2) -> str:
    def P(p):
        y = (flip_h - p[1]) if flip_h is not None else p[1]
        return f"{p[0] * f:.{prec}f} {y * f:.{prec}f}"
    first = loop.segs[0]
    out = [f"M{P(first[1])}"]
    for s in loop.segs:
        out.append(f"L{P(s[2])}" if s[0] == "L" else f"C{P(s[2])} {P(s[3])} {P(s[4])}")
    out.append("Z")
    return "".join(out)


def to_svg(res, size_mm: float | None = None) -> str:
    k = _mm_per_px(res, size_mm)
    dims = f' width="{res.width * k:.3f}mm" height="{res.height * k:.3f}mm"' if k else ""
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg"{dims} viewBox="0 0 {res.width} {res.height}">']
    for r in res.regions:
        d = "".join(_d(l) for l in _loops(res, r))
        parts.append(f'<path fill="{r.color}" fill-rule="evenodd" d="{d}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def to_pdf(res, size_mm: float | None = None, mode: str = "separation", names: list[str] | None = None,
           overprint: set[str] | None = None) -> bytes:
    """PDF: cada color es una tinta directa Separation con su nombre y alternativo CMYK (o CMYK puro)."""
    k = _mm_per_px(res, size_mm) or (1 / 72 * 25.4)          # sin dato: 1 px = 1 pt
    f = k / 25.4 * 72
    wp, hp = res.width * f, res.height * f
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(wp, hp))
    cs_res, gs_res = pikepdf.Dictionary(), pikepdf.Dictionary()
    ops = []
    by_label = {r.label: r for r in res.regions}
    for i, r in enumerate(res.regions):
        name = (names[r.label] if names and r.label < len(names) else None) or f"Color {r.label + 1}"
        cmyk = _alt_cmyk(type("I", (), {"lab": r.lab})())
        if mode == "separation":
            fn = pdf.make_stream(b"", FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=cmyk, N=1)
            fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=cmyk, N=1)
            key = f"CS{i}"
            cs_res[f"/{key}"] = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + name.replace(" ", "_")), pikepdf.Name.DeviceCMYK, fn])
            ops.append(f"/{key} cs 1 scn")
        else:
            ops.append("{:.4f} {:.4f} {:.4f} {:.4f} k".format(*cmyk))
        if overprint and name in overprint:
            gs_res["/GSop"] = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1)
            ops.insert(len(ops) - 1, "/GSop gs")
        path = "".join(_pdf_path(l, f, res.height) for l in _loops(res, r))
        ops.append(path + "f*")
    page.Resources = pikepdf.Dictionary(ColorSpace=cs_res, ExtGState=gs_res)
    page.Contents = pdf.make_stream("\n".join(ops).encode())
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def _pdf_path(loop, f, H) -> str:
    def P(p):
        return f"{p[0] * f:.3f} {(H - p[1]) * f:.3f}"
    s = loop.segs
    out = [f"{P(s[0][1])} m "]
    for g in s:
        out.append(f"{P(g[2])} l " if g[0] == "L" else f"{P(g[2])} {P(g[3])} {P(g[4])} c ")
    out.append("h ")
    return "".join(out)


def to_eps(pdf_bytes: bytes) -> bytes:
    """EPS con Ghostscript `eps2write` a partir del PDF (necesita Ghostscript instalado)."""
    if not ghostscript.available():
        raise UserError("Para exportar EPS hace falta Ghostscript (ver la guía de instalación).")
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "in.pdf", Path(d) / "out.eps"
        src.write_bytes(pdf_bytes)
        ghostscript.run_gs(["-sDEVICE=eps2write", f"-sOutputFile={dst}", str(src)], timeout=120)
        return dst.read_bytes()


def _flatten(seg, tol_units: float):
    if seg[0] == "L":
        return [seg[1], seg[2]]
    n = int(max(4, min(40, np.linalg.norm(seg[4] - seg[1]) / max(tol_units * 4, 1e-6))))
    return list(seg_points(seg, n))


def to_dxf(res, size_mm: float | None = None) -> bytes:
    """DXF en mm para corte y troquel: una polilínea cerrada por trazado, una capa por color."""
    import ezdxf
    k = _mm_per_px(res, size_mm)
    if not k:
        raise UserError("Indica el tamaño final en mm (o usa una imagen con ppi) para exportar DXF.")
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for r in res.regions:
        layer = f"COLOR_{r.label + 1}_{r.color.lstrip('#')}"
        doc.layers.add(layer)
        for l in _loops(res, r):
            pts = []
            for s in l.segs:
                pts += _flatten(s, 0.02 / k)[:-1]
            if len(pts) < 3:
                continue
            msp.add_lwpolyline([(p[0] * k, (res.height - p[1]) * k) for p in pts], close=True, dxfattribs={"layer": layer})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def render(res, width: int, height: int) -> np.ndarray:
    """Render RGB del vector (PyMuPDF abre SVG) a `width`×`height` px: para superponer y ver diferencias."""
    import fitz
    svg = to_svg(res).replace("<svg ", f'<svg width="{width}" height="{height}" ', 1)
    doc = fitz.open(stream=svg.encode(), filetype="svg")
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(width / doc[0].rect.width, height / doc[0].rect.height), alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()


def to_outline_svg(res) -> str:
    """Solo contornos y nodos (para revisar la calidad del ajuste)."""
    r = max(1.0, res.width / 250)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {res.width} {res.height}">']
    for reg in res.regions:
        d = "".join(_d(l) for l in reg.loops)
        parts.append(f'<path fill="none" stroke="#e11" stroke-width="{r / 3:.2f}" d="{d}"/>')
        for l in reg.loops:
            for s in l.segs:
                parts.append(f'<circle cx="{s[1][0]:.1f}" cy="{s[1][1]:.1f}" r="{r:.1f}" fill="#06f"/>')
    parts.append("</svg>")
    return "".join(parts)
