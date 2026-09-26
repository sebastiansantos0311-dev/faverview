"""Rutas de Automatizar (S8): recetas, ejecución sobre un archivo o carpeta y carpetas vigiladas."""
import io
import json
import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import RESULTS_DIR, UPLOADS_DIR, load_config
from app.core import jobs
from app.core.errors import UserError
from app.core.files import check_job, save_upload
from app.modules.automation import engine

router = APIRouter(prefix="/api/automatizar")


def _recipe(receta: str | dict) -> dict:
    return engine.load_recipe(receta) if isinstance(receta, str) else receta


@router.get("/recetas")
def recipes():
    return engine.list_recipes()


@router.get("/catalogo")
def catalog():
    return engine.catalog()


@router.get("/recetas/{rid}")
def get_recipe(rid: str):
    return engine.load_recipe(rid)


class RecipeIn(BaseModel):
    receta: dict


@router.put("/recetas/{rid}")
def put_recipe(rid: str, body: RecipeIn):
    engine.save_recipe(rid, body.receta)
    return {"ok": True}


@router.delete("/recetas/{rid}")
def delete_recipe(rid: str):
    engine.delete_recipe(rid)
    return {"ok": True}


@router.post("/validar")
def validate(body: RecipeIn):
    return {"errores": engine.validate(body.receta)}


@router.post("/ejecutar")
def run_file(file: UploadFile = File(...), receta: str = Form(""), receta_json: str = Form("")):
    """Ejecuta una receta (por id o JSON) sobre un archivo subido; el resultado se descarga como ZIP."""
    cfg = load_config()
    rec = json.loads(receta_json) if receta_json else engine.load_recipe(receta)
    job_id = uuid.uuid4().hex[:12]
    d = UPLOADS_DIR / job_id
    try:
        p = save_upload(file, d, "entrada", cfg["max_upload_mb"], allowed=engine.INPUT_EXT, formats_msg="Usa PDF o imágenes (JPG, PNG, TIFF, BMP, WEBP).")
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    named = d / (Path(file.filename or "archivo").name)
    p.replace(named)
    out = RESULTS_DIR / "automatizar" / job_id

    def work(progress):
        r = engine.run_file(rec, named, out, lambda m: progress("Receta", 0.5, m))
        return r

    jobs.start(job_id, work)
    return {"job_id": job_id}


@router.get("/descargar/{job_id}")
def download(job_id: str):
    check_job(job_id)
    out = RESULTS_DIR / "automatizar" / job_id
    if not out.exists():
        raise UserError("No hay resultados para ese trabajo.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in out.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(out).as_posix())
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="resultado.zip"'})


class FolderIn(BaseModel):
    receta: str | dict
    entrada: str
    salida: str


@router.post("/carpeta")
def run_folder(body: FolderIn):
    rec = _recipe(body.receta)
    job_id = uuid.uuid4().hex[:12]

    def work(progress):
        return engine.run_folder(rec, body.entrada, body.salida, lambda m, p: progress("Lote", p, m))

    jobs.start(job_id, work)
    return {"job_id": job_id}


class WatchIn(BaseModel):
    id: str
    receta: str | dict
    entrada: str
    salida: str


@router.post("/vigilar")
def watch(body: WatchIn):
    return engine.start_watch(body.id, _recipe(body.receta), body.entrada, body.salida)


@router.delete("/vigilar/{wid}")
def unwatch(wid: str):
    engine.stop_watch(wid)
    return {"ok": True}


@router.get("/vigilar")
def watching():
    return engine.watch_status()
