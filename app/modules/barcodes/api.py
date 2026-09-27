"""Rutas del módulo Códigos de barras (S6)."""
import csv
import io
import shutil
import tempfile
import zipfile
from pathlib import Path

import pymupdf
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import load_config
from app.core.errors import UserError
from app.core.files import save_upload
from app.modules.barcodes import generate as g
from app.modules.barcodes import verify as v

router = APIRouter(prefix="/api/codigos")


class InkIn(BaseModel):
    name: str
    lab: list[float]


class GenIn(BaseModel):
    tipo: str = "ean13"
    datos: str = ""
    magnificacion: float = 1.0
    x_mm: float | None = None
    altura_mm: float | None = None
    bwr_um: float = 0.0
    texto_legible: bool = True
    indicador: bool = False
    tinta: InkIn | None = None
    formato: str = "vista"       # vista | pdf | svg | eps


def _build(p: GenIn):
    lab = tuple(p.tinta.lab) if p.tinta else (16.0, 0.0, 0.0)
    lay = g.layout(p.tipo, p.datos, magnificacion=p.magnificacion, x_mm=p.x_mm, altura_mm=p.altura_mm, bwr_mm=p.bwr_um / 1000,
                   texto_legible=p.texto_legible, indicador=p.indicador, ink_lab=lab)
    return lay, lab


def _attach(name):
    return {"Content-Disposition": f'attachment; filename="{name}"'}


@router.get("/tipos")
def types():
    return [{"id": k, "nombre": t[0], "x_mm": t[2], "altura_mm": t[3], "lineal": t[6]} for k, t in g.TIPOS.items()]


@router.post("/generar")
def generate(p: GenIn):
    lay, lab = _build(p)
    if p.formato == "vista":
        return {"svg": g.to_svg(lay), "avisos": lay.warnings, "ancho_mm": round(lay.width, 2), "alto_mm": round(lay.height, 2),
                "x_mm": round(lay.x_mm, 4), "texto": lay.datos}
    if p.formato == "svg":
        return Response(g.to_svg(lay), media_type="image/svg+xml", headers=_attach("codigo.svg"))
    pdf = g.to_pdf(lay, p.tinta.name if p.tinta else None, lab)
    if p.formato == "pdf":
        return Response(pdf, media_type="application/pdf", headers=_attach("codigo.pdf"))
    if p.formato == "eps":
        return Response(g.to_eps(pdf), media_type="application/postscript", headers=_attach("codigo.eps"))
    raise UserError("Formato desconocido.")


@router.post("/lote")
def batch(file: UploadFile = File(...), hoja: bool = Form(True)):
    """CSV (`tipo;datos;nombre` con cabecera opcional) → ZIP con un PDF por código y, si se pide, una hoja con todos."""
    raw = file.file.read(2_000_000).decode("utf-8-sig", "replace")
    first = raw.splitlines()[0] if raw.strip() else ""
    delim = ";" if first.count(";") >= first.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(raw), delimiter=delim) if r and any(c.strip() for c in r)]
    if rows and rows[0][0].strip().lower() in ("tipo", "type"):
        rows = rows[1:]
    if not rows:
        raise UserError("El CSV está vacío. Columnas: tipo;datos;nombre (ejemplo: ean13;590123412345;producto1).")
    if len(rows) > 500:
        raise UserError("Máximo 500 códigos por lote.")
    errors, pdfs = [], []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, r in enumerate(rows, 1):
            try:
                tipo, datos = r[0].strip().lower(), r[1].strip()
                name = (r[2].strip() if len(r) > 2 and r[2].strip() else f"{tipo}_{i}")
                lay = g.layout(tipo, datos)
                pdf = g.to_pdf(lay)
                safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
                z.writestr(f"{i:03d}_{safe}.pdf", pdf)
                pdfs.append((name, lay, pdf))
            except (UserError, IndexError) as e:
                errors.append(f"Fila {i}: {getattr(e, 'message', 'faltan columnas (tipo;datos;nombre)')}")
        if hoja and pdfs:
            z.writestr("hoja.pdf", _sheet(pdfs))
        if errors:
            z.writestr("errores.txt", "\n".join(errors))
    return Response(buf.getvalue(), media_type="application/zip", headers={**_attach("codigos.zip"), "X-Errores": str(len(errors))})


def _sheet(items) -> bytes:
    """Hoja A4 con todos los códigos en cuadrícula, con su nombre debajo."""
    A4w, A4h = 595.0, 842.0
    doc = pymupdf.open()
    page, x, y, rowh = None, 30.0, 30.0, 0.0
    for name, lay, pdf in items:
        w, h = lay.width * g.PT, lay.height * g.PT + 12
        if page is None or x + w > A4w - 30:
            x, y = 30.0, y + rowh + 14
            rowh = 0.0
        if page is None or y + h > A4h - 30:
            page = doc.new_page(width=A4w, height=A4h)
            x, y, rowh = 30.0, 30.0, 0.0
        with pymupdf.open(stream=pdf, filetype="pdf") as src:
            page.show_pdf_page(pymupdf.Rect(x, y, x + lay.width * g.PT, y + lay.height * g.PT), src, 0)
        page.insert_text((x, y + h), name[:28], fontsize=7)
        x += w + 14
        rowh = max(rowh, h)
    out = doc.tobytes()
    doc.close()
    return out


@router.post("/verificar")
def verify(file: UploadFile = File(...), dpi: int = Form(600), pagina: int = Form(1), direccion: str = Form("")):
    cfg = load_config()
    d = Path(tempfile.mkdtemp(prefix="fv_bc_"))
    try:
        p = save_upload(file, d, "f", cfg["max_upload_mb"], allowed={".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"},
                        formats_msg="Sube un PDF o una imagen.")
        return v.verify(p, min(max(dpi, 150), 1200), pagina, direccion if direccion in ("horizontal", "vertical") else None)
    finally:
        shutil.rmtree(d, ignore_errors=True)
