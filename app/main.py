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

from . import history, jobs
from .config import DATOS_DIR, RESULTS_DIR, UPLOADS_DIR, WEB_DIR, load_config, setup_tesseract
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
            min_region_area: float | None = Form(None), wait: bool = False):
    """Sube los archivos y arranca la comparación en segundo plano (consultar /api/jobs/{id}).
    Con ?wait=1 espera y devuelve el resultado directamente."""
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / job_id
    try:
        cpath = _save_upload(client_file, job_dir, "client", cfg["max_upload_mb"])
        dpath = _save_upload(design_file, job_dir, "design", cfg["max_upload_mb"])
        (job_dir / "meta.json").write_text(json.dumps(
            {"client_name": client_file.filename, "design_name": design_file.filename}), encoding="utf-8")
    except FileError:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    params = {"ssim_threshold": ssim_threshold, "delta_e_tolerance": delta_e_tolerance,
              "min_region_area": min_region_area}

    def work(progress=None):
        return run_comparison(job_id, cpath, dpath, params, client_page - 1, design_page - 1,
                              client_file.filename or "", design_file.filename or "",
                              progress=progress).model_dump()

    if wait:
        return {"job_id": job_id, "result": work()}
    jobs.start(job_id, work)
    return {"job_id": job_id}


class Recompute(BaseModel):
    ssim_threshold: float | None = None
    delta_e_tolerance: float | None = None
    min_region_area: float | None = None
    client_page: int = 1
    design_page: int = 1
    manual_points: dict | None = None  # {"client": [[x, y] x4], "design": [[x, y] x4]}


@app.post("/api/recompute/{job_id}")
def recompute(job_id: str, body: Recompute, wait: bool = False):
    _check_job(job_id)
    job_dir = UPLOADS_DIR / job_id
    cpath, dpath = _find_upload(job_dir, "client"), _find_upload(job_dir, "design")
    meta = {}
    if (job_dir / "meta.json").exists():
        meta = json.loads((job_dir / "meta.json").read_text(encoding="utf-8"))
    params = {"ssim_threshold": body.ssim_threshold, "delta_e_tolerance": body.delta_e_tolerance,
              "min_region_area": body.min_region_area, "manual_points": body.manual_points}

    def work(progress=None):
        return run_comparison(job_id, cpath, dpath, params, body.client_page - 1, body.design_page - 1,
                              meta.get("client_name", ""), meta.get("design_name", ""),
                              progress=progress).model_dump()

    if wait:
        return {"job_id": job_id, "result": work()}
    jobs.start(job_id, work)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    _check_job(job_id)
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(404, "Trabajo no encontrado.")
    return j.public()


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


class Review(BaseModel):
    verdicts: dict[int, str] = {}  # id de error -> "real" | "falso_positivo"
    missed: list[dict] = []  # errores no detectados marcados a mano
    client_text: str | None = None
    tipo: str | None = None
    notas: str | None = None


def _next_case_dir() -> Path:
    base = DATOS_DIR / "casos"
    base.mkdir(parents=True, exist_ok=True)
    nums = [int(p.name.split("_")[1]) for p in base.glob("caso_*") if p.name.split("_")[1].isdigit()]
    d = base / f"caso_{1 + max(nums or [0]):03d}"
    d.mkdir()
    return d


@app.post("/api/cases/{job_id}")
def save_case(job_id: str, body: Review):
    """Guarda la revisión como caso de prueba en datos_locales/casos/ (no se sube a git)."""
    _check_job(job_id)
    rj = RESULTS_DIR / job_id / "result.json"
    if not rj.exists():
        raise HTTPException(404, "Resultado no encontrado.")
    result = Result.model_validate_json(rj.read_text(encoding="utf-8"))
    job_dir = UPLOADS_DIR / job_id
    cpath, dpath = _find_upload(job_dir, "client"), _find_upload(job_dir, "design")
    cdir = _next_case_dir()
    shutil.copy(cpath, cdir / f"cliente{cpath.suffix}")
    shutil.copy(dpath, cdir / f"diseno{dpath.suffix}")
    errores = []
    for d in result.differences:
        verdict = body.verdicts.get(d.id, "real")
        d.review = verdict if verdict in ("real", "falso_positivo") else "pendiente"
        if d.review == "real":
            e = {"categoria": d.category, "subtipo": d.subtype, "bbox": list(d.bbox)}
            if d.category == "text":
                e["cliente_dice"], e["diseno_dice"] = d.expected, d.found
            elif d.category == "spelling":
                e["diseno_dice"] = d.found
            errores.append(e)
    for m in body.missed:
        errores.append({k: m[k] for k in ("categoria", "subtipo", "bbox", "cliente_dice", "diseno_dice") if m.get(k)})
    esperado = {
        "caso": cdir.name, "tipo": body.tipo or result.image_type or "exportado",
        "cliente": f"cliente{cpath.suffix}", "diseno": f"diseno{dpath.suffix}",
        "pagina_cliente": result.pages.get("client", 1), "pagina_diseno": result.pages.get("design", 1),
        "errores": errores, "texto_cliente": body.client_text or "", "notas": body.notas or ""}
    (cdir / "esperado.json").write_text(json.dumps(esperado, ensure_ascii=False, indent=1), encoding="utf-8")
    rj.write_text(result.model_dump_json(indent=1), encoding="utf-8")  # conserva el veredicto de cada error
    try:
        from .learning import store
        store.record_review(result, body.model_dump(), cdir, dpath, cpath)
    except ImportError:
        pass
    return {"caso": cdir.name, "errores": len(errores)}


class Word(BaseModel):
    word: str


@app.post("/api/dictionary")
def dictionary(body: Word):
    if not body.word.strip():
        raise HTTPException(400, "Palabra vacía.")
    add_to_dictionary(body.word)
    return {"ok": True}


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
