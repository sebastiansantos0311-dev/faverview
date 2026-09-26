"""Rutas del módulo Comparar (las mismas URL de la v2)."""
import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import history
from app.config import DATOS_DIR, RESULTS_DIR, UPLOADS_DIR, load_config
from app.core import jobs
from app.core.files import FILE_RE, JOB_RE, check_job, find_upload, save_upload
from app.loaders import FileError, page_count
from app.modules.compare.models import Result
from app.modules.compare.pipeline import run_comparison
from app.modules.compare.report import build_report
from app.modules.compare.spelling import add_to_dictionary

router = APIRouter()

@router.post("/api/pages")
def pages(file: UploadFile = File(...)):
    cfg = load_config()
    tmp_dir = UPLOADS_DIR / ("tmp_" + uuid.uuid4().hex[:8])
    try:
        p = save_upload(file, tmp_dir, "f", cfg["max_upload_mb"])
        return {"pages": page_count(p)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/api/compare")
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
        cpath = save_upload(client_file, job_dir, "client", cfg["max_upload_mb"])
        dpath = save_upload(design_file, job_dir, "design", cfg["max_upload_mb"])
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


@router.post("/api/recompute/{job_id}")
def recompute(job_id: str, body: Recompute, wait: bool = False):
    check_job(job_id)
    job_dir = UPLOADS_DIR / job_id
    cpath, dpath = find_upload(job_dir, "client"), find_upload(job_dir, "design")
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


@router.get("/api/results/{job_id}/{filename}")
def get_result_file(job_id: str, filename: str):
    check_job(job_id)
    if not FILE_RE.match(filename):
        raise HTTPException(404, "Archivo no encontrado.")
    p = RESULTS_DIR / job_id / filename
    if not p.is_file():
        raise HTTPException(404, "Archivo no encontrado.")
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@router.get("/api/report/{job_id}")
def report(job_id: str):
    check_job(job_id)
    d = RESULTS_DIR / job_id
    rj = d / "result.json"
    if not rj.exists():
        raise HTTPException(404, "Resultado no encontrado.")
    result = Result.model_validate_json(rj.read_text(encoding="utf-8"))
    out = d / "reporte.pdf"
    build_report(result, d, out)
    return FileResponse(out, media_type="application/pdf", filename=f"reporte_faverview_{job_id}.pdf")


@router.get("/api/history")
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


@router.post("/api/cases/{job_id}")
def save_case(job_id: str, body: Review):
    """Guarda la revisión como caso de prueba en datos_locales/casos/ (no se sube a git)."""
    check_job(job_id)
    rj = RESULTS_DIR / job_id / "result.json"
    if not rj.exists():
        raise HTTPException(404, "Resultado no encontrado.")
    result = Result.model_validate_json(rj.read_text(encoding="utf-8"))
    job_dir = UPLOADS_DIR / job_id
    cpath, dpath = find_upload(job_dir, "client"), find_upload(job_dir, "design")
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
        from app.learning import store
        aprendizaje = store.record_review(result, body.model_dump(), cdir, dpath, cpath)
    except ImportError:
        pass
    return {"caso": cdir.name, "errores": len(errores), **aprendizaje}


# ---------------------------------------------------------------------------------- plantillas de zonas
class TemplateIn(BaseModel):
    nombre: str
    zonas: list[dict]
    ancho: int | None = None
    alto: int | None = None


@router.get("/api/templates")
def templates_list():
    from . import ignore_zones
    return ignore_zones.list_templates()


@router.get("/api/templates/suggest")
def templates_suggest(filename: str = "", w: int | None = None, h: int | None = None):
    from . import ignore_zones
    return ignore_zones.suggest(filename, w, h)


@router.get("/api/templates/{nombre}")
def templates_get(nombre: str):
    from . import ignore_zones
    t = ignore_zones.load_template(nombre)
    if not t:
        raise HTTPException(404, "Plantilla no encontrada.")
    return t


@router.post("/api/templates")
def templates_save(body: TemplateIn):
    from . import ignore_zones
    try:
        return ignore_zones.save_template(body.nombre, body.zonas, body.ancho, body.alto)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e) if isinstance(e, ValueError) else "Zonas inválidas.")


@router.delete("/api/templates/{nombre}")
def templates_delete(nombre: str):
    from . import ignore_zones
    ignore_zones.delete_template(nombre)
    return {"ok": True}


# ---------------------------------------------------------------------------------- versiones, correcciones, lotes
def _clean_name(up: UploadFile) -> str:
    return up.filename or ""


@router.post("/api/compare-versions")
def compare_versions(v1_file: UploadFile = File(...), v2_file: UploadFile = File(...),
                     v1_page: int = Form(1), v2_page: int = Form(1), wait: bool = False):
    """Compara dos versiones de MI diseño (PDF vs PDF): texto exacto, fuentes, colores y render."""
    from .versions import run_versions
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / job_id
    try:
        p1 = save_upload(v1_file, job_dir, "client", cfg["max_upload_mb"])
        p2 = save_upload(v2_file, job_dir, "design", cfg["max_upload_mb"])
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


@router.post("/api/compare-fix")
def compare_fix(previous_job_id: str = Form(...), design_file: UploadFile = File(...), design_page: int = Form(1),
                wait: bool = False):
    """Verifica correcciones: recompara el mismo arte del cliente con un diseño nuevo y dice qué errores de la
    revisión anterior quedaron corregidos ✔ y cuáles siguen ✘."""
    from .versions import verify_corrections
    check_job(previous_job_id)
    prev_json = RESULTS_DIR / previous_job_id / "result.json"
    if not prev_json.exists():
        raise HTTPException(404, "No se encontró la revisión anterior.")
    prev = Result.model_validate_json(prev_json.read_text(encoding="utf-8"))
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / job_id
    old = find_upload(UPLOADS_DIR / previous_job_id, "client")
    try:
        dpath = save_upload(design_file, job_dir, "design", cfg["max_upload_mb"])
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


@router.post("/api/compare-batch")
def compare_batch(client_file: UploadFile = File(...), design_file: UploadFile = File(...),
                  template: str | None = Form(None), wait: bool = False):
    """Compara TODAS las páginas (emparejadas por orden o, si el número difiere, por similitud visual)."""
    from .batch import run_batch
    cfg = load_config()
    batch_id = uuid.uuid4().hex[:12]
    job_dir = UPLOADS_DIR / batch_id
    try:
        cpath = save_upload(client_file, job_dir, "client", cfg["max_upload_mb"])
        dpath = save_upload(design_file, job_dir, "design", cfg["max_upload_mb"])
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


@router.get("/api/report-batch/{batch_id}")
def report_batch(batch_id: str):
    from .batch import merge_reports
    check_job(batch_id)
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


@router.patch("/api/results/{job_id}/checklist")
def checklist(job_id: str, body: ChecklistIn):
    check_job(job_id)
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


@router.post("/api/dictionary")
def dictionary(body: Word):
    if not body.word.strip():
        raise HTTPException(400, "Palabra vacía.")
    add_to_dictionary(body.word)
    return {"ok": True}


