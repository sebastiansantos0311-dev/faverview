"""Rutas del módulo Preflight (S6)."""
import json
import re
import shutil
import uuid

import cv2
import numpy as np
import pymupdf
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import UPLOADS_DIR, load_config
from app.core import jobs
from app.core.errors import UserError
from app.core.files import check_job, find_upload, save_upload
from app.modules.preflight import engine, fixes, report

router = APIRouter(prefix="/api/preflight")


def _pdf(job_id):
    check_job(job_id)
    d = UPLOADS_DIR / job_id
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    ed = d / "corregido.pdf"
    return (ed if ed.exists() else find_upload(d, "original")), meta


@router.get("/perfiles")
def profiles():
    return engine.list_profiles()


@router.get("/perfiles/{pid}")
def get_profile(pid: str):
    return engine.load_profile(pid)


class ProfileIn(BaseModel):
    id: str
    perfil: dict


@router.post("/perfiles")
def save_profile(p: ProfileIn):
    engine.save_profile(p.id, p.perfil)
    return {"ok": True}


@router.get("/correcciones")
def available_fixes():
    return fixes.AVAILABLE


@router.post("")
def upload(file: UploadFile = File(...)):
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    d = UPLOADS_DIR / job_id
    try:
        p = save_upload(file, d, "original", cfg["max_upload_mb"], allowed={".pdf"}, formats_msg="Sube un archivo PDF.")
        (d / "meta.json").write_text(json.dumps({"name": file.filename}), encoding="utf-8")
        with pymupdf.open(str(p)) as doc:
            n = len(doc)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return {"job_id": job_id, "nombre": file.filename, "paginas": n}


@router.post("/{job_id}/revisar")
def run(job_id: str, perfil: str = "offset_hoja"):
    path, meta = _pdf(job_id)

    def work(progress):
        res = engine.run_preflight(path, perfil, progress)
        (UPLOADS_DIR / job_id / "ultimo_resultado.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        return res

    aid = uuid.uuid4().hex[:12]
    jobs.start(aid, work)
    return {"job_id": aid}


@router.get("/{job_id}/pagina.png")
def page_png(job_id: str, pagina: int = 1, dpi: int = engine.DPI):
    path, _ = _pdf(job_id)
    with pymupdf.open(str(path)) as doc:
        if not 1 <= pagina <= len(doc):
            raise UserError("Esa página no existe.")
        pix = doc[pagina - 1].get_pixmap(dpi=min(max(dpi, 30), 300), alpha=False)
        return Response(pix.tobytes("png"), media_type="image/png", headers={"Cache-Control": "no-store"})


class FixesIn(BaseModel):
    correcciones: dict
    perfil: str = "offset_hoja"


@router.post("/{job_id}/corregir")
def fix(job_id: str, body: FixesIn):
    check_job(job_id)
    d = UPLOADS_DIR / job_id
    src = find_upload(d, "original")
    tmp = d / "corregido_tmp.pdf"
    res = fixes.apply_fixes(src, tmp, body.correcciones, body.perfil)
    tmp.replace(d / "corregido.pdf")
    return res


@router.post("/{job_id}/deshacer")
def undo(job_id: str):
    check_job(job_id)
    (UPLOADS_DIR / job_id / "corregido.pdf").unlink(missing_ok=True)
    return {"ok": True}


@router.get("/{job_id}/descargar")
def download(job_id: str):
    path, meta = _pdf(job_id)
    stem = re.sub(r"\.pdf$", "", meta.get("name", "documento"), flags=re.I)
    return FileResponse(path, media_type="application/pdf", filename=f"{stem}_faverview.pdf")


@router.get("/{job_id}/reporte")
def report_pdf(job_id: str, perfil: str = "offset_hoja"):
    path, meta = _pdf(job_id)
    f = UPLOADS_DIR / job_id / "ultimo_resultado.json"
    res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else engine.run_preflight(path, perfil)
    data = report.build_report(path, res, meta.get("name", ""))
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="preflight.pdf"'})
