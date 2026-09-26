"""Exportación del vectorizador (S4 §8.1.7): SVG, PDF (tintas directas Separation o CMYK), EPS (Ghostscript) y DXF (ezdxf)."""
import io
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

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


def _d_segs(segs, closed=True, f=1.0, prec=2) -> str:
    def P(p):
        return f"{p[0] * f:.{prec}f} {p[1] * f:.{prec}f}"
    out = [f"M{P(segs[0][1])}"]
    for s in segs:
        out.append(f"L{P(s[2])}" if s[0] == "L" else f"C{P(s[2])} {P(s[3])} {P(s[4])}")
    return "".join(out) + ("Z" if closed else "")


def _d(loop, f=1.0) -> str:
    return _d_segs(loop.segs, True, f)


def to_svg(res, size_mm: float | None = None) -> str:
    k = _mm_per_px(res, size_mm)
    dims = f' width="{res.width * k:.3f}mm" height="{res.height * k:.3f}mm"' if k else ""
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg"{dims} viewBox="0 0 {res.width} {res.height}">']
    for r in res.regions:
        d = "".join(_d(l) for l in _loops(res, r))
        parts.append(f'<path fill="{r.color}" fill-rule="evenodd" d="{d}"/>')
    for s in res.strokes:
        parts.append(f'<path fill="none" stroke="{s["color"]}" stroke-width="{s["width"]:.2f}" d="{_d_segs(s["segs"], False)}"/>')
    for t in res.texts:
        parts.append(f'<text x="{t["x"]:.1f}" y="{t["y"]:.1f}" font-family="{escape(t["font"])}" font-size="{t["size"]:.1f}" '
                     f'fill="{t["color"]}">{escape(t["text"])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


class _CS:
    """Espacios de color del PDF: un Separation por color (o CMYK puro)."""

    def __init__(self, pdf, mode, names):
        self.pdf, self.mode, self.names = pdf, mode, names
        self.res = pikepdf.Dictionary()
        self.cache: dict[int, str] = {}

    def fill_op(self, label, lab, stroke=False) -> str:
        cmyk = _alt_cmyk(type("I", (), {"lab": lab})())
        if self.mode != "separation":
            return "{:.4f} {:.4f} {:.4f} {:.4f} {}".format(*cmyk, "K" if stroke else "k")
        if label not in self.cache:
            name = (self.names[label] if self.names and label < len(self.names) else None) or f"Color {label + 1}"
            fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=cmyk, N=1)
            key = f"CS{label}"
            self.res[f"/{key}"] = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + name.replace(" ", "_")),
                                                 pikepdf.Name.DeviceCMYK, fn])
            self.cache[label] = key
        return f"/{self.cache[label]} {'CS' if stroke else 'cs'} 1 {'SCN' if stroke else 'scn'}"


def to_pdf(res, size_mm: float | None = None, mode: str = "separation", names: list[str] | None = None,
           overprint: set[str] | None = None) -> bytes:
    """PDF: cada color es una tinta directa Separation con su nombre y alternativo CMYK (o CMYK puro)."""
    k = _mm_per_px(res, size_mm) or (1 / 72 * 25.4)          # sin dato: 1 px = 1 pt
    f = k / 25.4 * 72
    wp, hp = res.width * f, res.height * f
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(wp, hp))
    cso = _CS(pdf, mode, names)
    gs_res = pikepdf.Dictionary()
    ops = []
    for r in res.regions:
        name = (names[r.label] if names and r.label < len(names) else None) or f"Color {r.label + 1}"
        if overprint and name in overprint:
            gs_res["/GSop"] = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1)
            ops.append("/GSop gs")
        ops.append(cso.fill_op(r.label, r.lab))
        ops.append("".join(_pdf_path(l.segs, f, res.height, True) for l in _loops(res, r)) + "f*")
    for s in res.strokes:
        ops.append(cso.fill_op(s["label"], s.get("lab", (50, 0, 0)), True))
        ops.append(f"{s['width'] * f:.3f} w 0 J 1 j " + _pdf_path(s["segs"], f, res.height, False) + "S")
    fonts = pikepdf.Dictionary()
    if res.texts:
        fonts["/F1"] = pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica,
                                          Encoding=pikepdf.Name.WinAnsiEncoding)
    for t in res.texts:
        rgb = [int(t["color"][i:i + 2], 16) / 255 for i in (1, 3, 5)]
        txt = t["text"].encode("cp1252", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append("BT {:.3f} {:.3f} {:.3f} rg /F1 {:.2f} Tf {:.3f} {:.3f} Td ({}) Tj ET".format(
            *rgb, t["size"] * f, t["x"] * f, (res.height - t["y"]) * f, txt))
    page.Resources = pikepdf.Dictionary(ColorSpace=cso.res, ExtGState=gs_res, Font=fonts)
    page.Contents = pdf.make_stream("\n".join(ops).encode("latin-1", "replace"))
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def _pdf_path(segs, f, H, close) -> str:
    def P(p):
        return f"{p[0] * f:.3f} {(H - p[1]) * f:.3f}"
    out = [f"{P(segs[0][1])} m "]
    for g in segs:
        out.append(f"{P(g[2])} l " if g[0] == "L" else f"{P(g[2])} {P(g[3])} {P(g[4])} c ")
    if close:
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

    def poly(segs, layer, close):
        pts = []
        for s in segs:
            pts += _flatten(s, 0.02 / k)[:-1]
        pts.append(segs[-1][2] if segs[-1][0] == "L" else segs[-1][4])
        if len(pts) >= 2:
            msp.add_lwpolyline([(p[0] * k, (res.height - p[1]) * k) for p in pts], close=close, dxfattribs={"layer": layer})

    for r in res.regions:
        layer = f"COLOR_{r.label + 1}_{r.color.lstrip('#')}"
        doc.layers.add(layer)
        for l in _loops(res, r):
            poly(l.segs, layer, True)
    for s in res.strokes:
        layer = f"TRAZO_{s['label'] + 1}"
        doc.layers.add(layer)
        poly(s["segs"], layer, False)
    for t in res.texts:
        msp.add_text(t["text"], dxfattribs={"height": t["size"] * k, "insert": (t["x"] * k, (res.height - t["y"]) * k)})
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
    for z in res.text_zones:
        parts.append(f'<rect x="{z["x"]}" y="{z["y"]}" width="{z["w"]}" height="{z["h"]}" fill="none" stroke="#0a0" stroke-width="{r / 3:.2f}"/>')
    parts.append("</svg>")
    return "".join(parts)
