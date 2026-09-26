"""Rutas de «Separar colores → PDF» (S2)."""
import json
import re
import shutil
import threading
import uuid
from collections import OrderedDict

import cv2
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import UPLOADS_DIR, load_config
from app.core import inks as inkmod
from app.core import jobs
from app.core.errors import UserError
from app.core.files import check_job, find_upload, save_upload
from app.core.pdfinfo import page_size_mm, read_pdf_info
from app.modules.separate import analysis, export, pdf_edit
from app.modules.separate.pdf_inks import read_inventory
from app.modules.separate.pdf_render import Plates, compose, render_plates

router = APIRouter(prefix="/api/separar/pdf")
_CACHE: "OrderedDict[tuple, Plates]" = OrderedDict()
_LOCK = threading.Lock()


def _job_pdf(job_id: str):
    check_job(job_id)
    d = UPLOADS_DIR / job_id
    meta = d / "meta.json"
    name = json.loads(meta.read_text(encoding="utf-8")).get("name", "") if meta.exists() else ""
    ed = d / "editado.pdf"          # si hay una versión editada activa se usa esa
    return (ed if ed.exists() else find_upload(d, "original")), name


def _plates(job_id: str, page: int, dpi: float, cancel=None) -> Plates:
    pdf, _ = _job_pdf(job_id)
    key = (job_id, pdf.name, pdf.stat().st_mtime_ns, page, dpi)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    p = render_plates(pdf, page, dpi, cancel=cancel)
    with _LOCK:
        _CACHE[key] = p
        while len(_CACHE) > 3:
            _CACHE.popitem(last=False)
    return p


def _plate_meta(plates: Plates, job_id: str) -> dict:
    """Por nombre de placa: tipo y Lab según el inventario del PDF (por nombre normalizado)."""
    pdf, _ = _job_pdf(job_id)
    by_norm = {i.norm: i for i in read_inventory(pdf).inks}
    out = {}
    for n in plates.names:
        i = by_norm.get(inkmod.normalize_name(n))
        if i is not None:
            out[n] = {"tipo": i.kind, "lab": i.lab}
    return out


def _png(img) -> Response:
    ok, buf = cv2.imencode(".png", img[..., ::-1] if img.ndim == 3 else img)
    return Response(buf.tobytes(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("")
def upload(file: UploadFile = File(...)):
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    d = UPLOADS_DIR / job_id
    try:
        p = save_upload(file, d, "original", cfg["max_upload_mb"], allowed={".pdf"}, formats_msg="Sube un archivo PDF.")
        (d / "meta.json").write_text(json.dumps({"name": file.filename}), encoding="utf-8")
        info = read_pdf_info(p)
        inv = read_inventory(p)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    n = len(info.boxes)
    return {"job_id": job_id, "nombre": file.filename, "paginas": n,
            "tamano_mm": page_size_mm(p, 0), "inventario": inv.to_dict()}


@router.get("/{job_id}/inventario")
def inventory(job_id: str):
    pdf, _ = _job_pdf(job_id)
    return read_inventory(pdf).to_dict()


@router.post("/{job_id}/analizar")
def analyze(job_id: str, pagina: int = 1, dpi: float = 150, limite_tac: float = 300, linea_min_mm: float = 0.1):
    pdf, _ = _job_pdf(job_id)

    def work(progress):
        progress("Separando", 0.1, "Separando en placas con Ghostscript…")
        plates = _plates(job_id, pagina - 1, dpi)
        progress("Analizando", 0.7, "Analizando cobertura y problemas…")
        inv = read_inventory(pdf)
        meta = _plate_meta(plates, job_id)
        tac = analysis.tac_map(plates, meta)
        finds = analysis.run_checks(plates, pdf, pagina - 1, inv, meta, limite_tac, linea_min_mm)
        cov = analysis.coverage_pct(plates)
        return {"placas": [{"nombre": n, "cobertura": cov[n], "vacia": plates.empty(n),
                            "tipo": (meta.get(n) or {}).get("tipo", "spot"),
                            "lab": (meta.get(n) or {}).get("lab")} for n in plates.names],
                "ancho": plates.width, "alto": plates.height, "dpi": plates.dpi, "pagina": pagina,
                "tac": analysis.tac_stats(tac), "limite_tac": limite_tac,
                "hallazgos": [f.to_dict() for f in finds], "avisos": plates.warnings,
                "inventario": inv.to_dict()}

    aid = uuid.uuid4().hex[:12]
    jobs.start(aid, work)
    return {"job_id": aid}


@router.get("/{job_id}/composicion.png")
def composition(job_id: str, pagina: int = 1, dpi: float = 150, ocultas: str = "", solo: str = "", escala: float = 1.0):
    plates = _plates(job_id, pagina - 1, dpi)
    hidden = {x for x in ocultas.split("|") if x}
    visible = {n for n in plates.names if n not in hidden}
    if solo:
        visible &= {solo}
    return _png(compose(plates, _plate_meta(plates, job_id), visible, scale=min(max(escala, 0.05), 1.0)))


@router.get("/{job_id}/placa.png")
def plate_png(job_id: str, nombre: str, pagina: int = 1, dpi: float = 150, negativo: bool = False):
    plates = _plates(job_id, pagina - 1, dpi)
    if nombre not in plates.arrays:
        raise UserError("Esa tinta no existe en el PDF.")
    a = plates.arrays[nombre]
    return _png(a if negativo else 255 - a)


@router.get("/{job_id}/tac.png")
def tac_png(job_id: str, pagina: int = 1, dpi: float = 150, limite: float = 300):
    plates = _plates(job_id, pagina - 1, dpi)
    return _png(analysis.tac_heatmap(analysis.tac_map(plates, _plate_meta(plates, job_id)), limite))


@router.get("/{job_id}/sonda")
def probe(job_id: str, x: float, y: float, pagina: int = 1, dpi: float = 150):
    return analysis.probe(_plates(job_id, pagina - 1, dpi), x, y)


class Edits(BaseModel):
    renombrar: dict[str, str] = {}
    convertir: list[str] = []
    eliminar_no_usadas: bool = False


@router.post("/{job_id}/editar")
def edit(job_id: str, body: Edits):
    check_job(job_id)
    d = UPLOADS_DIR / job_id
    src = d / "editado.pdf" if (d / "editado.pdf").exists() else find_upload(d, "original")
    tmp = d / "editado_tmp.pdf"
    summary = pdf_edit.apply_edits(src, tmp, rename=body.renombrar, convert=body.convertir,
                                   delete_unused=body.eliminar_no_usadas)
    tmp.replace(d / "editado.pdf")
    return summary


@router.post("/{job_id}/deshacer")
def undo(job_id: str):
    check_job(job_id)
    (UPLOADS_DIR / job_id / "editado.pdf").unlink(missing_ok=True)
    return {"ok": True}


@router.get("/{job_id}/descargar")
def download(job_id: str):
    pdf, name = _job_pdf(job_id)
    stem = re.sub(r"\.pdf$", "", name or "documento", flags=re.I)
    return FileResponse(pdf, media_type="application/pdf", filename=f"{stem}_faverview.pdf")


class Export(BaseModel):
    formato: str = "tiff8"     # tiff8 | tiff1 | pdf | informe
    pagina: int = 1
    dpi: float = 150
    umbral: int = 128
    limite_tac: float = 300


@router.post("/{job_id}/exportar")
def export_plates(job_id: str, body: Export):
    if body.formato not in ("tiff8", "tiff1", "pdf", "informe"):
        raise UserError("Formato de exportación desconocido.")
    pdf, name = _job_pdf(job_id)
    plates = _plates(job_id, body.pagina - 1, body.dpi)
    meta = _plate_meta(plates, job_id)
    finds = [f.to_dict() for f in analysis.run_checks(plates, pdf, body.pagina - 1, read_inventory(pdf), meta, body.limite_tac)]
    data = export.export_zip(plates, meta, body.formato, finds, body.umbral)
    stem = re.sub(r"\.pdf$", "", name or "documento", flags=re.I)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="' + stem + '_placas.zip"'})
