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

from . import history, jobs, updates
from .version import get_version
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
    updates.check_background()  # aviso de versión nueva (1 vez al día, sin bloquear el arranque)
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


@app.get("/favicon.ico")
def favicon():
    return FileResponse(WEB_DIR.parent / "assets" / "faverview.ico")


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
            min_region_area: float | None = Form(None), template: str | None = Form(None), wait: bool = False):
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
              "min_region_area": min_region_area, "template": template or None}

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
    zones: list[dict] | None = None  # zonas a ignorar dibujadas a mano (relativas 0–1)
    template: str | None = None  # nombre de una plantilla de zonas


@app.post("/api/recompute/{job_id}")
def recompute(job_id: str, body: Recompute, wait: bool = False):
    _check_job(job_id)
    job_dir = UPLOADS_DIR / job_id
    cpath, dpath = _find_upload(job_dir, "client"), _find_upload(job_dir, "design")
    meta = {}
    if (job_dir / "meta.json").exists():
        meta = json.loads((job_dir / "meta.json").read_text(encoding="utf-8"))
    params = {"ssim_threshold": body.ssim_threshold, "delta_e_tolerance": body.delta_e_tolerance,
              "min_region_area": body.min_region_area, "manual_points": body.manual_points,
              "zones": body.zones, "template": body.template}

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


@app.get("/api/version")
def version():
    return {"version": get_version()}


@app.get("/api/update")
def update_status():
    return {**updates.status(), "version": get_version()}


@app.post("/api/update/apply")
def update_apply():
    return updates.apply()


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
    aprendizaje = {"autoajuste": False}
    try:
        from .learning import store
        aprendizaje = store.record_review(result, body.model_dump(), cdir, dpath, cpath)
    except ImportError:
        pass
    return {"caso": cdir.name, "errores": len(errores), **aprendizaje}


# ---------------------------------------------------------------------------------- aprendizaje (Fase 7)
_LEARN_LOG: dict = {"running": None, "log": [], "resultado": None}


def _bg(name: str, fn):
    """Ejecuta una tarea larga del aprendizaje en un hilo y guarda su registro."""
    import threading
    if _LEARN_LOG["running"]:
        raise HTTPException(409, f"Ya hay una tarea en curso: {_LEARN_LOG['running']}.")
    _LEARN_LOG.update(running=name, log=[], resultado=None)

    def run():
        try:
            _LEARN_LOG["resultado"] = fn(lambda *a: _LEARN_LOG["log"].append(" ".join(str(x) for x in a)))
        except Exception as e:
            _LEARN_LOG["resultado"] = {"ok": False, "mensaje": f"Error: {e}"}
        finally:
            _LEARN_LOG["running"] = None

    threading.Thread(target=run, daemon=True).start()


@app.get("/api/learning")
def learning_summary():
    from .learning import cli as lcli, confusions, tuning, vocab
    r = lcli.resumen()
    r["confusiones_lista"] = confusions.summary()[:60]
    r["vocabulario_lista"] = [{"palabra": w, "veces": c} for w, c in sorted(vocab.counts().items(), key=lambda kv: -kv[1])[:80]]
    r["autoajuste_en_curso"] = tuning.is_running()
    r["tarea"] = {"en_curso": _LEARN_LOG["running"], "registro": _LEARN_LOG["log"][-12:], "resultado": _LEARN_LOG["resultado"]}
    r["activo"] = load_config().get("learning_enabled", True)
    return r


@app.delete("/api/learning/confusion")
def learning_del_confusion(key: str):
    from .learning import confusions
    confusions.remove(key)
    return {"ok": True}


@app.delete("/api/learning/vocab")
def learning_del_vocab(word: str):
    from .learning import vocab
    vocab.remove_word(word)
    return {"ok": True}


@app.post("/api/learning/tune")
def learning_tune():
    from .learning import tuning
    _bg("Ajustando el preprocesado del OCR", lambda log: tuning.autotune(log=log))
    return {"ok": True}


@app.post("/api/learning/train")
def learning_train():
    from .learning import finetune

    def work(log):
        info = finetune.train(log=log)
        if info.get("ok"):
            info = finetune.ab_test(log=log)
        return info

    _bg("Re-entrenando el modelo de OCR", work)
    return {"ok": True}


class ModelToggle(BaseModel):
    activo: bool


@app.post("/api/learning/model")
def learning_model(body: ModelToggle):
    from .learning import finetune
    finetune.activate(body.activo)
    return {"ok": True, "activo": finetune.is_active()}


@app.get("/api/learning/export")
def learning_export(recortes: bool = False):
    from fastapi.responses import Response
    from .learning import portability
    return Response(portability.export_zip(recortes), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="aprendizaje_faverview.zip"'})


@app.post("/api/learning/import")
def learning_import(file: UploadFile = File(...)):
    from .learning import portability
    try:
        return {"ok": True, "agregado": portability.import_zip(file.file.read())}
    except Exception:
        raise HTTPException(400, "El archivo no es una exportación válida de aprendizaje.")


# ---------------------------------------------------------------------------------- plantillas de zonas
class TemplateIn(BaseModel):
    nombre: str
    zonas: list[dict]
    ancho: int | None = None
    alto: int | None = None


@app.get("/api/templates")
def templates_list():
    from . import ignore_zones
    return ignore_zones.list_templates()


@app.get("/api/templates/suggest")
def templates_suggest(filename: str = "", w: int | None = None, h: int | None = None):
    from . import ignore_zones
    return ignore_zones.suggest(filename, w, h)


@app.get("/api/templates/{nombre}")
def templates_get(nombre: str):
    from . import ignore_zones
    t = ignore_zones.load_template(nombre)
    if not t:
        raise HTTPException(404, "Plantilla no encontrada.")
    return t


@app.post("/api/templates")
def templates_save(body: TemplateIn):
    from . import ignore_zones
    try:
        return ignore_zones.save_template(body.nombre, body.zonas, body.ancho, body.alto)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e) if isinstance(e, ValueError) else "Zonas inválidas.")


@app.delete("/api/templates/{nombre}")
def templates_delete(nombre: str):
    from . import ignore_zones
    ignore_zones.delete_template(nombre)
    return {"ok": True}


# ---------------------------------------------------------------------------------- versiones, correcciones, lotes
def _clean_name(up: UploadFile) -> str:
    return up.filename or ""


@app.post("/api/compare-versions")
def compare_versions(v1_file: UploadFile = File(...), v2_file: UploadFile = File(...),
                     v1_page: int = Form(1), v2_page: int = Form(1), wait: bool = False):
    """Compara dos versiones de MI diseño (PDF vs PDF): texto exacto, fuentes, colores y render."""
    from .versions import run_versions
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / job_id
    try:
        p1 = _save_upload(v1_file, job_dir, "client", cfg["max_upload_mb"])
        p2 = _save_upload(v2_file, job_dir, "design", cfg["max_upload_mb"])
        (job_dir / "meta.json").write_text(json.dumps({"client_name": v1_file.filename, "design_name": v2_file.filename}),
                                           encoding="utf-8")
    except FileError:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    def work(progress=None):
        return run_versions(job_id, p1, p2, None, v1_page - 1, v2_page - 1, _clean_name(v1_file), _clean_name(v2_file),
                            progress=progress).model_dump()

    if wait:
        return {"job_id": job_id, "result": work()}
    jobs.start(job_id, work)
    return {"job_id": job_id}


@app.post("/api/compare-fix")
def compare_fix(previous_job_id: str = Form(...), design_file: UploadFile = File(...), design_page: int = Form(1),
                wait: bool = False):
    """Verifica correcciones: recompara el mismo arte del cliente con un diseño nuevo y dice qué errores de la
    revisión anterior quedaron corregidos ✔ y cuáles siguen ✘."""
    from .versions import verify_corrections
    _check_job(previous_job_id)
    prev_json = RESULTS_DIR / previous_job_id / "result.json"
    if not prev_json.exists():
        raise HTTPException(404, "No se encontró la revisión anterior.")
    prev = Result.model_validate_json(prev_json.read_text(encoding="utf-8"))
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / job_id
    old = _find_upload(UPLOADS_DIR / previous_job_id, "client")
    try:
        dpath = _save_upload(design_file, job_dir, "design", cfg["max_upload_mb"])
        cpath = job_dir / f"client{old.suffix}"
        shutil.copy(old, cpath)
        (job_dir / "meta.json").write_text(json.dumps({"client_name": prev.client_name, "design_name": design_file.filename}),
                                           encoding="utf-8")
    except FileError:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    params = {k: v for k, v in (prev.params or {}).items() if k in ("ssim_threshold", "delta_e_tolerance", "min_region_area",
                                                                    "zones", "template", "manual_points")}

    def work(progress=None):
        res = run_comparison(job_id, cpath, dpath, params, prev.pages.get("client", 1) - 1, design_page - 1,
                             prev.client_name, design_file.filename or "", progress=progress)
        res.fix_report = verify_corrections(prev, res)
        (RESULTS_DIR / job_id / "result.json").write_text(res.model_dump_json(indent=1), encoding="utf-8")
        return res.model_dump()

    if wait:
        return {"job_id": job_id, "result": work()}
    jobs.start(job_id, work)
    return {"job_id": job_id}


@app.post("/api/compare-batch")
def compare_batch(client_file: UploadFile = File(...), design_file: UploadFile = File(...),
                  template: str | None = Form(None), wait: bool = False):
    """Compara TODAS las páginas (emparejadas por orden o, si el número difiere, por similitud visual)."""
    from .batch import run_batch
    cfg = load_config()
    batch_id = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / batch_id
    try:
        cpath = _save_upload(client_file, job_dir, "client", cfg["max_upload_mb"])
        dpath = _save_upload(design_file, job_dir, "design", cfg["max_upload_mb"])
    except FileError:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    def work(progress=None):
        return run_batch(batch_id, cpath, dpath, client_file.filename or "", design_file.filename or "",
                         {"template": template or None}, progress)

    if wait:
        return {"job_id": batch_id, "result": work()}
    jobs.start(batch_id, work, {"batch": True})
    return {"job_id": batch_id}


@app.get("/api/report-batch/{batch_id}")
def report_batch(batch_id: str):
    from .batch import merge_reports
    _check_job(batch_id)
    if not (RESULTS_DIR / batch_id / "batch.json").exists():
        raise HTTPException(404, "Lote no encontrado.")
    out = RESULTS_DIR / batch_id / "reporte_lote.pdf"
    merge_reports(batch_id, out)
    return FileResponse(out, media_type="application/pdf", filename=f"reporte_lote_{batch_id}.pdf")


# ---------------------------------------------------------------------------------- checklist de aprobación (8.5)
class ChecklistIn(BaseModel):
    items: dict[int, dict]  # id -> {"status": pendiente|corregido|no_aplica, "comment": str}


def _checklist_summary(result: Result) -> dict:
    vivos = [d for d in result.differences if not d.ignored_by_zone]
    pend = sum(d.status == "pendiente" for d in vivos)
    return {"pendientes": pend, "corregidos": sum(d.status == "corregido" for d in vivos),
            "no_aplica": sum(d.status == "no_aplica" for d in vivos), "listo": pend == 0}


@app.patch("/api/results/{job_id}/checklist")
def checklist(job_id: str, body: ChecklistIn):
    _check_job(job_id)
    rj = RESULTS_DIR / job_id / "result.json"
    if not rj.exists():
        raise HTTPException(404, "Resultado no encontrado.")
    result = Result.model_validate_json(rj.read_text(encoding="utf-8"))
    by_id = {d.id: d for d in result.differences}
    for i, it in body.items.items():
        d = by_id.get(i)
        if d is None:
            continue
        if it.get("status") in ("pendiente", "corregido", "no_aplica"):
            d.status = it["status"]
        if "comment" in it:
            d.comment = (it["comment"] or "")[:500] or None
    rj.write_text(result.model_dump_json(indent=1), encoding="utf-8")
    summ = _checklist_summary(result)
    history.update_entry(job_id, {"pendientes": summ["pendientes"], "listo": summ["listo"]})
    return summ


class Word(BaseModel):
    word: str


@app.post("/api/dictionary")
def dictionary(body: Word):
    if not body.word.strip():
        raise HTTPException(400, "Palabra vacía.")
    add_to_dictionary(body.word)
    return {"ok": True}


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
