"""Salidas de la separación de imágenes (S3 §7.8): canales, placas tramadas, PDF DeviceN, simulación e informe."""
import io
import zipfile
from datetime import datetime

import cv2
import numpy as np
import pikepdf
from PIL import Image

from app.core import colorscience as cs
from app.modules.separate import halftone
from app.modules.separate.export import _safe
from app.modules.separate.raster import Ink, SepResult


def _tiff(arr: np.ndarray, dpi: float, one_bit: bool) -> bytes:
    """Convención de película: negro = tinta."""
    buf = io.BytesIO()
    if one_bit:
        Image.fromarray(((~arr) * 255).astype(np.uint8)).convert("1").save(buf, "TIFF", dpi=(dpi, dpi), compression="group4")
    else:
        Image.fromarray(255 - arr, "L").save(buf, "TIFF", dpi=(dpi, dpi), compression="tiff_lzw")
    return buf.getvalue()


def _png(rgb) -> bytes:
    ok, b = cv2.imencode(".png", np.asarray(rgb)[..., ::-1])
    return b.tobytes()


def _alt_cmyk(ink: Ink) -> list[float]:
    r, g, b = [float(x) for x in np.asarray(cs.lab_to_srgb(ink.lab))]
    k = 1 - max(r, g, b)
    if k >= 1:
        return [0, 0, 0, 1]
    return [round((1 - r - k) / (1 - k), 4), round((1 - g - k) / (1 - k), 4), round((1 - b - k) / (1 - k), 4), round(k, 4)]


def _tint_ps(inks: list[Ink]) -> str:
    n = len(inks)
    parts = []
    alts = [_alt_cmyk(i) for i in inks]
    for o in range(4):
        parts.append("0")
        for j in range(n):
            depth = o + 1 + (n - 1 - j)
            parts.append(f"{depth} index {alts[j][o]} mul add")
        parts.append("dup 1 gt {pop 1} if")
    parts.append(f"{n + 4} 4 roll")
    parts.append(" ".join(["pop"] * n))
    return "{ " + " ".join(parts) + " }"


def devicen_pdf(res: SepResult, dpi: float, inks: list[Ink] | None = None) -> bytes:
    """PDF con una imagen de n canales (DeviceN con los nombres de las tintas y alternativo CMYK)."""
    inks = inks or res.palette
    if not inks or len(inks) > 8:
        raise ValueError("El PDF DeviceN necesita entre 1 y 8 tintas.")
    h, w = next(iter(res.channels.values())).shape
    data = np.stack([res.channels[i.name] for i in inks], -1).tobytes()
    pdf = pikepdf.new()
    fn = pdf.make_stream(_tint_ps(inks).encode(), FunctionType=4, Domain=[0, 1] * len(inks), Range=[0, 1] * 4)
    cs_arr = pikepdf.Array([pikepdf.Name.DeviceN, pikepdf.Array([pikepdf.Name("/" + i.name.replace(" ", "_")) for i in inks]),
                            pikepdf.Name.DeviceCMYK, fn])
    img = pdf.make_stream(data, Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image, Width=w, Height=h,
                          ColorSpace=cs_arr, BitsPerComponent=8)
    wp, hp = w * 72 / dpi, h * 72 / dpi
    page = pdf.add_blank_page(page_size=(wp, hp))
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=img))
    page.Contents = pdf.make_stream(f"q {wp:.3f} 0 0 {hp:.3f} 0 0 cm /Im0 Do Q".encode())
    out = io.BytesIO()
    pdf.save(out, compress_streams=True)
    return out.getvalue()


def report_text(res: SepResult, params: dict, dpi: float) -> str:
    lines = [f"Informe de separación de imagen — {datetime.now():%Y-%m-%d %H:%M}",
             "Valores orientativos (simulación no espectral).", f"Resolución de trabajo: {dpi:g} ppi", ""]
    lines += [f"{k}: {v}" for k, v in res.stats.items()]
    lines += ["", "Tintas (orden de impresión) y cobertura media:"]
    for n in res.names:
        lines.append(f"- {n}: {res.channels[n].mean() / 255 * 100:.2f} %")
    lines += ["", "Parámetros: " + ", ".join(f"{k}={v}" for k, v in params.items())]
    lines += [f"Aviso: {w}" for w in res.warnings]
    return "\n".join(lines)


def export_zip(res: SepResult, dpi: float, params: dict, halftone_cfg: dict | None = None, pdf: bool = True,
               out_dpi: float | None = None) -> bytes:
    """ZIP con canales 8 bits, placas tramadas (si `halftone_cfg`), PDF DeviceN, simulación e informe."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in res.names:
            z.writestr(f"canales/{_safe(n)}.tif", _tiff(res.channels[n], dpi, False))
        if halftone_cfg:
            od = out_dpi or 600
            f = od / dpi
            for i, n in enumerate(res.names):
                a = res.channels[n]
                big = cv2.resize(a, None, fx=f, fy=f, interpolation=cv2.INTER_LINEAR) if abs(f - 1) > 1e-3 else a
                ht = halftone.halftone(big, od, index=i, **halftone_cfg)
                z.writestr(f"placas_1bit/{_safe(n)}.tif", _tiff(ht, od, True))
        z.writestr("simulacion.png", _png(res.sim))
        if pdf and res.palette and len(res.palette) <= 8:
            z.writestr("canales_devicen.pdf", devicen_pdf(res, dpi))
        z.writestr("informe.txt", report_text(res, params, dpi))
    return buf.getvalue()
