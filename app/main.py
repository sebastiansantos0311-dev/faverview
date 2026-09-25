import json
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import history
from .config import RESULTS_DIR, UPLOADS_DIR, WEB_DIR, load_config, setup_tesseract
from .loaders import ALLOWED_EXT, FileError, page_count, validate_file
from .models import Result
from .pipeline import run_comparison
from .report import build_report
from .spelling import add_to_dictionary

_JOB_RE = re.compile(r"^[0-9a-f]{12}$")
_FILE_RE = re.compile(r"^[\w.\-]+$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    history.cleanup(30)
    setup_tesseract()
    yield


app = FastAPI(title="FAVERVIEW", lifespan=lifespan)


@app.exception_handler(FileError)
async def file_error_handler(request, exc: FileError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _check_job(job_id: str) -> None:
    if not _JOB_RE.match(job_id):
        raise HTTPException(404, "Trabajo no encontrado.")


def _save_upload(up: UploadFile, dest_dir: Path, stem: str, max_mb: float) -> Path:
    ext = Path(up.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise FileError(f"Formato no admitido ({ext or 'sin extensión'}). Usa JPG, PNG, WEBP, BMP, TIFF o PDF.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stem}{ext}"
    limit = int(max_mb * 1024 * 1024)
    size = 0
    with open(dest, "wb") as f:
        while chunk := up.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise FileError(f"El archivo supera el máximo de {max_mb:g} MB.")
            f.write(chunk)
    validate_file(dest, max_mb)
    return dest


def _find_upload(job_dir: Path, stem: str) -> Path:
    for p in job_dir.glob(f"{stem}.*"):
        return p
    raise FileError("Los archivos originales de este análisis ya no están disponibles. "
                    "Vuelve a subirlos para recalcular.")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.post("/api/pages")
def pages(file: UploadFile = File(...)):
    cfg = load_config()
    tmp_dir = UPLOADS_DIR / ("tmp_" + uuid.uuid4().hex[:8])
    try:
        p = _save_upload(file, tmp_dir, "f", cfg["max_upload_mb"])
        return {"pages": page_count(p)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.post("/api/compare")
def compare(client_file: UploadFile = File(...), design_file: UploadFile = File(...),
            client_page: int = Form(1), design_page: int = Form(1),
            ssim_threshold: float | None = Form(None), delta_e_tolerance: float | None = Form(None),
            min_region_area: float | None = Form(None)):
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / job_id
    try:
        cpath = _save_upload(client_file, job_dir, "client", cfg["max_upload_mb"])
        dpath = _save_upload(design_file, job_dir, "design", cfg["max_upload_mb"])
        (job_dir / "meta.json").write_text(json.dumps(
            {"client_name": client_file.filename, "design_name": design_file.filename}), encoding="utf-8")
        result = run_comparison(
            job_id, cpath, dpath,
            {"ssim_threshold": ssim_threshold, "delta_e_tolerance": delta_e_tolerance,
             "min_region_area": min_region_area},
            client_page - 1, design_page - 1, client_file.filename or "", design_file.filename or "")
    except FileError:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    return {"job_id": job_id, "result": result.model_dump()}


class Recompute(BaseModel):
    ssim_threshold: float | None = None
    delta_e_tolerance: float | None = None
    min_region_area: float | None = None
    client_page: int = 1
    design_page: int = 1


@app.post("/api/recompute/{job_id}")
def recompute(job_id: str, body: Recompute):
    _check_job(job_id)
    job_dir = UPLOADS_DIR / job_id
    cpath, dpath = _find_upload(job_dir, "client"), _find_upload(job_dir, "design")
    meta = {}
    if (job_dir / "meta.json").exists():
        meta = json.loads((job_dir / "meta.json").read_text(encoding="utf-8"))
    result = run_comparison(
        job_id, cpath, dpath,
        {"ssim_threshold": body.ssim_threshold, "delta_e_tolerance": body.delta_e_tolerance,
         "min_region_area": body.min_region_area},
        body.client_page - 1, body.design_page - 1,
        meta.get("client_name", ""), meta.get("design_name", ""))
    return {"job_id": job_id, "result": result.model_dump()}


@app.get("/api/results/{job_id}/{filename}")
def get_result_file(job_id: str, filename: str):
    _check_job(job_id)
    if not _FILE_RE.match(filename):
        raise HTTPException(404, "Archivo no encontrado.")
    p = RESULTS_DIR / job_id / filename
    if not p.is_file():
        raise HTTPException(404, "Archivo no encontrado.")
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@app.get("/api/report/{job_id}")
def report(job_id: str):
    _check_job(job_id)
    d = RESULTS_DIR / job_id
    rj = d / "result.json"
    if not rj.exists():
        raise HTTPException(404, "Resultado no encontrado.")
    result = Result.model_validate_json(rj.read_text(encoding="utf-8"))
    out = d / "reporte.pdf"
    build_report(result, d, out)
    return FileResponse(out, media_type="application/pdf", filename=f"reporte_faverview_{job_id}.pdf")


@app.get("/api/history")
def get_history():
    return history.list_entries()


class Word(BaseModel):
    word: str


@app.post("/api/dictionary")
def dictionary(body: Word):
    if not body.word.strip():
        raise HTTPException(400, "Palabra vacía.")
    add_to_dictionary(body.word)
    return {"ok": True}


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
