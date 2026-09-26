"""Generación de códigos de barras vectoriales (S6 §10.2): PDF (tinta directa o K), SVG y EPS. Nunca raster.

Los símbolos los crea zxing-cpp (módulos exactos); aquí se valida, se calcula la geometría en mm
(magnificación, reducción de barras BWR, zonas de silencio) y se dibuja en vectores."""
import io
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import numpy as np
import pikepdf
import zxingcpp as z

from app.core import colorscience as cs
from app.core import ghostscript
from app.core.errors import UserError
from app.modules.barcodes import gs1
from app.modules.separate.raster_export import _alt_cmyk

F = z.BarcodeFormat
PT = 72 / 25.4

# tipo → (nombre, formato zxing, X nominal mm, altura de barras nominal mm, silencio izq, silencio der (módulos), 1D?)
TIPOS = {
    "ean13": ("EAN-13", F.EAN13, 0.33, 22.85, 11, 7, True),
    "ean8": ("EAN-8", F.EAN8, 0.33, 18.23, 7, 7, True),
    "upca": ("UPC-A", F.UPCA, 0.33, 22.85, 9, 9, True),
    "upce": ("UPC-E", F.UPCE, 0.33, 22.85, 9, 7, True),
    "itf14": ("ITF-14", F.ITF14, 0.495, 31.75, 10, 10, True),
    "code128": ("Code 128", F.Code128, 0.33, 15.0, 10, 10, True),
    "gs1_128": ("GS1-128", F.Code128, 0.495, 20.0, 10, 10, True),
    "code39": ("Code 39", F.Code39, 0.33, 15.0, 10, 10, True),
    "databar": ("GS1 DataBar", F.DataBar, 0.264, 13.0, 1, 1, True),
    "datamatrix": ("Data Matrix", F.DataMatrix, 0.5, 0.0, 1, 1, False),
    "gs1_datamatrix": ("GS1 DataMatrix", F.DataMatrix, 0.5, 0.0, 1, 1, False),
    "qr": ("QR", F.QRCode, 0.5, 0.0, 4, 4, False),
}


@dataclass
class Layout:
    width: float                      # mm totales (con silencios)
    height: float
    rects: list                       # (x, y, w, h) mm, origen arriba-izquierda
    texts: list                       # (texto, x, y_base, tamaño_mm, alineación)
    x_mm: float
    warnings: list = field(default_factory=list)
    tipo: str = ""
    datos: str = ""


def _upce_to_upca(d: str) -> str:
    """UPC-E de 6 dígitos (más sistema y control) → UPC-A de 12 dígitos, para calcular/verificar el dígito de control."""
    ns, m, chk = d[0], d[1:7], d[7]
    last = m[5]
    if last in "012":
        a = ns + m[0:2] + last + "0000" + m[2:5]
    elif last == "3":
        a = ns + m[0:3] + "00000" + m[3:5]
    elif last == "4":
        a = ns + m[0:4] + "00000" + m[4]
    else:
        a = ns + m[0:5] + "0000" + last
    return a + chk


def normalize(tipo: str, datos: str) -> tuple[str, list[str]]:
    """Valida los datos y devuelve (texto para codificar, avisos)."""
    if tipo not in TIPOS:
        raise UserError("Tipo de código desconocido.")
    nombre = TIPOS[tipo][0]
    d = (datos or "").strip()
    if not d:
        raise UserError("Escribe los datos del código.")
    warns: list[str] = []
    if tipo == "ean13":
        d, w = gs1.ensure_check(d, 13, nombre)
    elif tipo == "ean8":
        d, w = gs1.ensure_check(d, 8, nombre)
    elif tipo == "upca":
        d, w = gs1.ensure_check(d, 12, nombre)
    elif tipo == "itf14":
        d, w = gs1.ensure_check(d, 14, nombre)
    elif tipo == "upce":
        d = "".join(d.split())
        if not d.isdigit() or len(d) not in (7, 8) or d[0] not in "01":
            raise UserError("UPC-E: 7 u 8 dígitos; el primero (sistema numérico) debe ser 0 o 1.")
        if len(d) == 7:
            chk = gs1.check_digit(_upce_to_upca(d + "0")[:-1])
            d, w = d + str(chk), f"Se calculó el dígito de control: {chk}."
        else:
            if not gs1.valid_check(_upce_to_upca(d)):
                raise UserError(f"UPC-E: el dígito de control es incorrecto (debería ser {gs1.check_digit(_upce_to_upca(d)[:-1])}).")
            w = None
    elif tipo in ("gs1_128", "gs1_datamatrix"):
        gs1.parse_ais(d)
        w = None
    elif tipo == "databar":
        gs1.parse_ais(d) if d.startswith("(") else None
        if not d.startswith("("):
            d, w = "(01)" + gs1.ensure_check(d, 14, nombre)[0], None
        w = None
    elif tipo == "code39":
        if any(ch not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%" for ch in d.upper()):
            raise UserError("Code 39 solo admite mayúsculas, dígitos y - . espacio $ / + %.")
        d, w = d.upper(), None
    else:
        w = None
    if w:
        warns.append(w)
    return d, warns


def _create(tipo: str, texto: str):
    fmt = TIPOS[tipo][1]
    kw = {"gs1": True} if tipo in ("gs1_128", "gs1_datamatrix") and texto.startswith("(") else {}
    try:
        b = z.create_barcode(texto, fmt, **kw)
    except Exception as e:
        raise UserError(f"No se pudo crear el código: {str(e)[:120]}")
    return np.asarray(b.to_image()) < 128            # True = módulo oscuro


def _runs(row: np.ndarray):
    """Elementos oscuros de una fila: [(inicio, ancho)] en módulos."""
    out, i, n = [], 0, len(row)
    while i < n:
        if row[i]:
            j = i
            while j < n and row[j]:
                j += 1
            out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


def ink_contrast(lab, paper=(95.0, 0.0, -2.0)) -> float:
    """Contraste de impresión (PCS) para luz roja: 1 − R_barra/R_papel usando el canal R lineal."""
    r_bar = float(cs.srgb_to_linear(np.asarray(cs.lab_to_srgb(lab)))[0])
    r_pap = float(cs.srgb_to_linear(np.asarray(cs.lab_to_srgb(paper)))[0])
    return 1.0 - r_bar / max(r_pap, 1e-6)


def layout(tipo: str, datos: str, *, magnificacion: float = 1.0, x_mm: float | None = None, altura_mm: float | None = None,
           bwr_mm: float = 0.0, texto_legible: bool = True, indicador: bool = False, ink_lab=(16.0, 0.0, 0.0)) -> Layout:
    """Geometría del símbolo en mm. `bwr_mm`: reducción de barras (cada barra pierde ese ancho, centrada, para compensar la ganancia)."""
    nombre, fmt, x_nom, h_nom, ql, qr_, is1d = TIPOS[tipo]
    if not 0.8 <= magnificacion <= 2.0 and tipo in ("ean13", "ean8", "upca", "upce"):
        raise UserError("La magnificación de EAN/UPC debe estar entre 80 % y 200 %.")
    texto, warns = normalize(tipo, datos)
    grid = _create(tipo, texto)
    x = (x_mm if x_mm else x_nom) * magnificacion
    if bwr_mm < 0 or bwr_mm >= x * 0.6:
        raise UserError(f"La reducción de barras debe estar entre 0 y {x * 0.6:.3f} mm para este módulo.")
    rects, texts = [], []
    if is1d:
        row = grid[grid.shape[0] // 2]
        run = _runs(row)
        first = run[0][0]
        modules = run[-1][0] + run[-1][1] - first
        h = (altura_mm if altura_mm else h_nom * (magnificacion if tipo in ("ean13", "ean8", "upca", "upce") else 1.0))
        th = 3.6 * (magnificacion if tipo in ("ean13", "ean8", "upca", "upce") else 1.0) if texto_legible else 0.0
        left = ql * x
        for s, w in run:
            bw = max(w * x - bwr_mm, 0.02)
            rects.append((left + (s - first) * x + bwr_mm / 2, 0.0, bw, h))
        width = left + modules * x + qr_ * x
        height = h + th
        if texto_legible:
            hri = _hri(tipo, texto)
            fs = 2.6 * (magnificacion if tipo in ("ean13", "ean8", "upca", "upce") else 1.0)
            if tipo in ("ean13", "upca", "ean8", "upce"):
                bl = left
                texts += _ean_texts(tipo, texto, bl, modules * x, h + th * 0.85, fs, x)
            else:
                texts.append((hri, left + modules * x / 2, h + th * 0.85, fs, "middle"))
        if indicador and tipo in ("ean13", "ean8"):
            texts.append((">", width - qr_ * x * 0.8, h + th * 0.85, 2.6, "start"))
    else:
        ys, xs = np.where(grid)
        sub = grid[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        n = sub.shape[0]
        left = ql * x
        for r, c in zip(*np.where(sub)):
            s = max(x - bwr_mm, 0.02)
            rects.append((left + c * x + bwr_mm / 2, left + r * x + bwr_mm / 2, s, s))
        width = height = (n + 2 * ql) * x
        if sub.shape[1] != n:
            width = (sub.shape[1] + 2 * ql) * x
    lay = Layout(width, height, rects, texts, x, warns, tipo, texto)
    if tipo in ("ean13", "ean8", "upca", "upce") and (x < 0.264 - 1e-6 or x > 0.66 + 1e-6):
        lay.warnings.append(f"El módulo X de {x:.3f} mm queda fuera del rango EAN/UPC (0,264–0,660 mm; 80–200 %).")
    pcs = ink_contrast(ink_lab)
    if pcs < 0.4:
        lay.warnings.append(f"Contraste insuficiente para escáneres de luz roja (≈ {pcs * 100:.0f} %): usa una tinta más oscura o mayor contraste con el sustrato.")
    if bwr_mm > 0:
        lay.warnings.append(f"BWR de {bwr_mm * 1000:.0f} µm aplicada: revisa el resultado con una prueba impresa de tu proceso.")
    return lay


def _hri(tipo, t):
    if tipo == "gs1_128":
        return t
    return t


def _ean_texts(tipo, t, left, w, y, fs, x):
    """Texto legible EAN/UPC: primer dígito fuera a la izquierda y los grupos bajo cada mitad (aproximado a OCR-B)."""
    if tipo == "ean13":
        return [(t[0], left - 5 * x, y, fs, "start"), (t[1:7], left + 3 * x + 21 * x, y, fs, "middle"),
                (t[7:], left + 50 * x + 21 * x, y, fs, "middle")]
    if tipo == "ean8":
        return [(t[:4], left + 3 * x + 14 * x, y, fs, "middle"), (t[4:], left + 36 * x + 14 * x, y, fs, "middle")]
    if tipo == "upca":
        return [(t[0], left - 5 * x, y, fs, "start"), (t[1:6], left + 10 * x + 17.5 * x, y, fs, "middle"),
                (t[6:11], left + 50 * x + 17.5 * x, y, fs, "middle"), (t[11], left + w + 1.5 * x, y, fs, "start")]
    return [(t[0], left - 5 * x, y, fs, "start"), (t[1:7], left + w / 2, y, fs, "middle"), (t[7], left + w + 1.5 * x, y, fs, "start")]


# ---------------------------------------------------------------- salidas
def to_svg(lay: Layout, color: str = "#000000") -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{lay.width:.3f}mm" height="{lay.height:.3f}mm" '
             f'viewBox="0 0 {lay.width:.3f} {lay.height:.3f}">']
    d = "".join(f"M{x:.4f} {y:.4f}h{w:.4f}v{h:.4f}h{-w:.4f}z" for x, y, w, h in lay.rects)
    parts.append(f'<path fill="{color}" d="{d}"/>')
    for t, x, y, fs, anchor in lay.texts:
        parts.append(f'<text x="{x:.3f}" y="{y:.3f}" font-family="Helvetica,Arial,sans-serif" font-size="{fs:.2f}" text-anchor="{anchor}" '
                     f'fill="{color}">{escape(t)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def to_pdf(lay: Layout, ink_name: str | None = None, ink_lab=(16.0, 0.0, 0.0)) -> bytes:
    """PDF vectorial: barras en una tinta directa (`ink_name`, con alternativo CMYK del Lab) o en K 100 %."""
    pdf = pikepdf.new()
    wp, hp = lay.width * PT, lay.height * PT
    page = pdf.add_blank_page(page_size=(wp, hp))
    ops, res = [], pikepdf.Dictionary()
    if ink_name:
        cmyk = _alt_cmyk(type("I", (), {"lab": ink_lab})())
        fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=cmyk, N=1)
        res["/ColorSpace"] = pikepdf.Dictionary(CS0=pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + ink_name.replace(" ", "_")),
                                                                   pikepdf.Name.DeviceCMYK, fn]))
        ops.append("/CS0 cs 1 scn")
    else:
        ops.append("0 0 0 1 k")
    ops += [f"{x * PT:.3f} {hp - (y + h) * PT:.3f} {w * PT:.3f} {h * PT:.3f} re" for x, y, w, h in lay.rects]
    ops.append("f")
    if lay.texts:
        res["/Font"] = pikepdf.Dictionary(F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                                 BaseFont=pikepdf.Name.Helvetica, Encoding=pikepdf.Name.WinAnsiEncoding))
        for t, x, y, fs, anchor in lay.texts:
            size = fs * PT
            wtxt = 0.556 * size * len(t)                # ancho medio de Helvetica para dígitos
            px = x * PT - (wtxt / 2 if anchor == "middle" else 0)
            safe = t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"BT /F1 {size:.2f} Tf {px:.3f} {hp - y * PT:.3f} Td ({safe}) Tj ET")
    page.Resources = res
    page.Contents = pdf.make_stream("\n".join(ops).encode("latin-1", "replace"))
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def to_eps(pdf_bytes: bytes) -> bytes:
    from app.modules.vectorize.export import to_eps as _eps
    return _eps(pdf_bytes)
