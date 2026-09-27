"""Rutas del módulo Vectorizar (S4)."""
import json
import shutil
import threading
import uuid
from collections import OrderedDict

import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import UPLOADS_DIR, load_config
from app.core import colorscience as cs
from app.core import jobs
from app.core.errors import UserError
from app.core.files import check_job, find_upload, save_upload
from app.modules.separate import raster
from app.modules.vectorize import edit, export, pipeline

router = APIRouter(prefix="/api/vectorizar")
_RES: "OrderedDict[str, pipeline.VectorResult]" = OrderedDict()
_LOCK = threading.Lock()
IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


class InkIn(BaseModel):
    name: str
    lab: list[float]


class Params(BaseModel):
    preset: str | None = None
    k_max: int = 8
    fusionar_de: float = 6.0
    detalle_min_mm: float = 0.15
    tolerancia: float = 0.8
    esquinas: float = 60.0
    suavidad: float = 1.6
    modo: str = "sin_solapes"
    bn: bool = False
    umbral_bn: int | None = None
    tintas: list[InkIn] = []
    dpi: float | None = None
    previa: bool = False
    primitivas: bool = False
    geometria_limpia: bool = False
    simetria: bool = False
    trazos: bool = False
    engrosar_mm: float = 0.0
    texto: str = "normal"
    fuente: str = "Arial"


def _colors(res):
    return [{"i": k, "nombre": ink.name, "hex": cs.lab_to_hex(ink.lab)} for k, ink in enumerate(res.palette)]


def _load(job_id):
    check_job(job_id)
    meta = json.loads((UPLOADS_DIR / job_id / "meta.json").read_text(encoding="utf-8"))
    return find_upload(UPLOADS_DIR / job_id, "original"), meta


def _get(job_id):
    check_job(job_id)
    with _LOCK:
        r = _RES.get(job_id)
    if r is None:
        raise UserError("Primero vectoriza la imagen.")
    return r


@router.post("")
def upload(file: UploadFile = File(...)):
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    d = UPLOADS_DIR / job_id
    try:
        path = save_upload(file, d, "original", cfg["max_upload_mb"], allowed=IMG_EXT, formats_msg="Usa JPG, PNG, TIFF, BMP o WEBP.")
        rgb, dpi = raster.load_image(path)
        (d / "meta.json").write_text(json.dumps({"name": file.filename, "dpi": dpi[0] if dpi else None}), encoding="utf-8")
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    h, w = rgb.shape[:2]
    return {"job_id": job_id, "nombre": file.filename, "ancho": w, "alto": h, "dpi": dpi[0] if dpi else None,
            "presets": list(pipeline.PRESETS)}


@router.post("/{job_id}/procesar")
def process(job_id: str, p: Params):
    path, meta = _load(job_id)

    def work(progress):
        progress("Vectorizando", 0.2, "Vectorizando…")
        rgb, _ = raster.load_image(path)
        dpi = p.dpi or meta.get("dpi")
        if p.previa and max(rgb.shape[:2]) > 500:
            f = 500 / max(rgb.shape[:2])
            rgb = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            dpi = dpi * f if dpi else None
        pal = [raster.Ink(i.name, tuple(i.lab)) for i in p.tintas] or None
        res = pipeline.vectorize(rgb, dpi, preset=p.preset, palette=pal, k_max=p.k_max, merge_de=p.fusionar_de,
                                 min_detail_mm=p.detalle_min_mm, fit_tol=p.tolerancia, corner_angle=p.esquinas, smooth=p.suavidad,
                                 mode=p.modo, bn=p.bn, bn_threshold=p.umbral_bn, primitives=p.primitivas,
                                 geometria_limpia=p.geometria_limpia, simetria=p.simetria, trazos=p.trazos,
                                 engrosar_mm=p.engrosar_mm, texto=p.texto, fuente=p.fuente)
        with _LOCK:
            _RES[job_id] = res
            _RES.move_to_end(job_id)
            while len(_RES) > 4:
                _RES.popitem(last=False)
        return {"stats": res.stats, "colores": _colors(res),
                "ancho": res.width, "alto": res.height, "simetria": res.symmetry, "zonas_texto": res.text_zones}

    aid = uuid.uuid4().hex[:12]
    jobs.start(aid, work)
    return {"job_id": aid}


def _png(img):
    ok, b = cv2.imencode(".png", np.asarray(img)[..., ::-1])
    return Response(b.tobytes(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/vector.svg")
def svg(job_id: str, tam_mm: float | None = None):
    return Response(export.to_svg(_get(job_id), tam_mm), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/contornos.svg")
def outline(job_id: str):
    return Response(export.to_outline_svg(_get(job_id)), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/original.png")
def original(job_id: str):
    path, _ = _load(job_id)
    res = _get(job_id)
    rgb, _ = raster.load_image(path)
    return _png(cv2.resize(rgb, (int(res.width), int(res.height)), interpolation=cv2.INTER_AREA))


@router.get("/{job_id}/diferencias.png")
def diff(job_id: str):
    path, _ = _load(job_id)
    res = _get(job_id)
    w, h = int(res.width), int(res.height)
    rgb, _ = raster.load_image(path)
    rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
    d = np.abs(rgb.astype(np.int16) - export.render(res, w, h).astype(np.int16)).max(-1)
    heat = cv2.applyColorMap(np.clip(d * 3, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)[..., ::-1]
    return _png(heat)


def _press(prensa, tol):
    if not prensa and tol is None:
        return None
    from app.core import press
    return press.resolve(prensa, tol)


@router.get("/{job_id}/traps")
def traps_info(job_id: str, tam_mm: float | None = None, trap_prensa: str | None = "serigrafia_textil_automatica", trap_tolerancia_mm: float | None = None):
    """Resumen de los traps vectoriales que se añadirían (qué tinta se expande bajo cuál y cuánto)."""
    from app.modules.vectorize import traps
    res = _get(job_id)
    pf = _press(trap_prensa, trap_tolerancia_mm)
    k = export._mm_per_px(res, tam_mm)
    groups = traps.build(res, pf, k)
    return {"perfil": pf.nombre, "tolerancia_mm": pf.tolerancia_mm, "traps": traps.summary(groups, k) if k else [],
            "avisos": ["Solo arte vectorial plano. R7 (retracción), R8 y R9 no se aplican en vectorial.", "SVG no tiene sobreimpresión: el SVG lleva traps simulados; el PDF, sobreimpresión real.",
                       "Estimación orientativa: confirma con tu imprenta."]}


def _attach(name: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


@router.get("/{job_id}/descargar")
def download(job_id: str, formato: str = "svg", tam_mm: float | None = None, pdf_modo: str = "separation", trap_prensa: str | None = None,
             trap_tolerancia_mm: float | None = None, sin_fondo: bool | None = None):
    res = _get(job_id)
    pf = _press(trap_prensa, trap_tolerancia_mm)
    if formato == "svg":
        return Response(export.to_svg(res, tam_mm, pf), media_type="image/svg+xml", headers=_attach("vector.svg"))
    names = [i.name for i in res.palette]
    if formato in ("pdf", "eps"):
        pdf = export.to_pdf(res, tam_mm, pdf_modo, names, trap=pf, sin_fondo=sin_fondo)
        if formato == "pdf":
            return Response(pdf, media_type="application/pdf", headers=_attach("vector.pdf"))
        return Response(export.to_eps(pdf), media_type="application/postscript", headers=_attach("vector.eps"))
    if formato == "dxf":
        return Response(export.to_dxf(res, tam_mm), media_type="application/dxf", headers=_attach("vector.dxf"))
    raise UserError("Formato desconocido.")


class Edit(BaseModel):
    op: str                       # unir | borrar | recolorear | zona
    a: int | None = None
    b: int | None = None
    color: str | None = None
    zona: list[int] | None = None  # x, y, ancho, alto en px del vector
    k_max: int | None = None
    fusionar_de: float = 6.0
    limpieza: float = 1.0


@router.post("/{job_id}/editar")
def edit_vector(job_id: str, e: Edit):
    res = _get(job_id)
    if e.op == "unir":
        new = edit.merge(res, e.a if e.a is not None else -1, e.b if e.b is not None else -1)
    elif e.op == "borrar":
        new = edit.delete_region(res, e.a if e.a is not None else -1)
    elif e.op == "recolorear":
        new = edit.recolor(res, e.a if e.a is not None else -1, e.color or "")
    elif e.op == "zona":
        if not e.zona or len(e.zona) != 4:
            raise UserError("Indica la zona (x, y, ancho, alto).")
        new = edit.retrace_zone(res, res.work, tuple(e.zona), k_max=e.k_max, merge_de=e.fusionar_de, denoise=e.limpieza)
    else:
        raise UserError("Operación desconocida.")
    with _LOCK:
        _RES[job_id] = new
    return {"stats": new.stats, "colores": _colors(new),
            "ancho": new.width, "alto": new.height}
