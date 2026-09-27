"""Rutas de «Separar colores → Imagen» (S3)."""
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
from app.core import jobs
from app.core.errors import UserError
from app.core.files import check_job, find_upload, save_upload
from app.modules.separate import raster, raster_export

router = APIRouter(prefix="/api/separar/img")
_RES: "OrderedDict[str, tuple]" = OrderedDict()      # job → (SepResult, dpi, params)
_LOCK = threading.Lock()
IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


class InkIn(BaseModel):
    name: str
    lab: list[float]
    opacity: float = 0.0


class Params(BaseModel):
    modo: str = "planas"                  # planas | proceso | indice | cmyk
    sustrato: str = "Papel blanco"
    sustrato_lab: list[float] | None = None
    tintas: list[InkIn] = []
    k_max: int = 8
    fusionar_de: float = 6.0
    area_min_mm2: float = 0.05
    bordes_suaves: bool = False
    lam: float = 4.0
    n_yn: float = 1.7
    punto_min: float = 3.0
    punto_max: float = 100.0
    gamma: float = 1.0
    choke_px: int = 0
    blanco_base: bool = True
    perfil: str | None = None
    intencion: str = "relativa"
    tac: float = 300.0
    negro_sombras: bool = False
    difusion: str = "fs"
    dpi: float | None = None
    previa: bool = False
    trama: dict | None = None
    dpi_salida: float = 600.0
    auto_trap: bool = False
    prensa: str | None = None
    tolerancia_mm: float | None = None


def _substrate(p: Params):
    return tuple(p.sustrato_lab) if p.sustrato_lab else raster.SUBSTRATES.get(p.sustrato, raster.PAPER)


def _load(job_id: str):
    check_job(job_id)
    meta = json.loads((UPLOADS_DIR / job_id / "meta.json").read_text(encoding="utf-8"))
    return find_upload(UPLOADS_DIR / job_id, "original"), meta


def run(rgb: np.ndarray, dpi: float | None, p: Params) -> raster.SepResult:
    res = _run(rgb, dpi, p)
    if p.auto_trap:
        from app.core import press
        from app.modules.separate import autotrap
        pf = press.resolve(p.prensa, p.tolerancia_mm)
        res = autotrap.apply_raster(res, dpi, pf, _substrate(p), p.modo)
    return res


def _run(rgb: np.ndarray, dpi: float | None, p: Params) -> raster.SepResult:
    sub = _substrate(p)
    inks = [raster.Ink(i.name, tuple(i.lab), i.opacity) for i in p.tintas]
    if p.modo == "planas":
        return raster.separate_flat(rgb, dpi, inks or None, p.k_max, p.fusionar_de, p.area_min_mm2, p.bordes_suaves, substrate=sub)
    if p.modo == "proceso":
        white = next((k for k, i in enumerate(inks) if i.opacity >= 1), None)
        return raster.separate_process(rgb, inks, sub, p.lam, p.n_yn, p.punto_min / 100, p.punto_max / 100, p.gamma,
                                       p.choke_px, white)
    if p.modo == "indice":
        return raster.separate_index(rgb, inks or None, p.k_max, p.difusion, sub)
    if p.modo == "cmyk":
        return raster.separate_cmyk(rgb, p.perfil, p.intencion, p.tac, p.negro_sombras)
    raise UserError("Modo desconocido.")


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
            "sustratos": {k: list(v) for k, v in raster.SUBSTRATES.items()},
            "perfiles_icc": list(raster.find_cmyk_profiles())}


def _trap_info(res):
    from app.modules.separate import autotrap
    if res.trap is None:
        return None
    return {"traps": res.trap.traps, "registro": autotrap.registro_texto(res), "ok": res.reg_after.filetes_px == 0 if res.reg_after else None,
            "filetes_mm2": round(res.reg_after.filetes_mm2, 3) if res.reg_after else None,
            "antes_mm2": round(res.reg_before.filetes_mm2, 3) if res.reg_before else None, "perfil": res.trap.press.nombre if res.trap.press else ""}


@router.post("/{job_id}/procesar")
def process(job_id: str, p: Params):
    path, meta = _load(job_id)

    def work(progress):
        progress("Separando", 0.1, "Separando en tintas…")
        rgb, _ = raster.load_image(path)
        dpi = p.dpi or meta.get("dpi")
        if p.previa and max(rgb.shape[:2]) > 700:
            f = 700 / max(rgb.shape[:2])
            rgb = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
            dpi = dpi * f if dpi else None
        warns = []
        if dpi and dpi < 150 and not p.previa:
            warns.append(f"La resolución ({dpi:.0f} ppi) es menor de 150 ppi: el resultado puede verse pixelado.")
        res = run(rgb, dpi, p)
        res.warnings += warns
        with _LOCK:
            _RES[job_id] = (res, dpi or 200.0, p.model_dump())
            while len(_RES) > 4:
                _RES.popitem(last=False)
        return {"nombres": res.names, "stats": res.stats, "avisos": res.warnings, "ancho": rgb.shape[1], "alto": rgb.shape[0],
                "cobertura": {n: round(float(res.channels[n].mean()) / 255 * 100, 2) for n in res.names},
                "paleta": [{"nombre": i.name, "lab": list(i.lab), "opacidad": i.opacity} for i in res.palette],
                "de": res.de_map is not None, "trap": _trap_info(res)}

    aid = uuid.uuid4().hex[:12]
    jobs.start(aid, work)
    return {"job_id": aid}


def _get(job_id: str):
    check_job(job_id)
    with _LOCK:
        r = _RES.get(job_id)
    if not r:
        raise UserError("Primero procesa la imagen.")
    return r


def _png(img) -> Response:
    img = np.asarray(img)
    ok, buf = cv2.imencode(".png", img[..., ::-1] if img.ndim == 3 else img)
    return Response(buf.tobytes(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/simulacion.png")
def sim(job_id: str):
    return _png(_get(job_id)[0].sim)


@router.get("/{job_id}/original.png")
def original(job_id: str):
    path, _ = _load(job_id)
    rgb, _ = raster.load_image(path)
    res = _get(job_id)[0]
    h, w = res.sim.shape[:2]
    if rgb.shape[:2] != (h, w):
        rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
    return _png(rgb)


@router.get("/{job_id}/canal.png")
def channel(job_id: str, nombre: str, negativo: bool = False):
    res = _get(job_id)[0]
    if nombre not in res.channels:
        raise UserError("Ese canal no existe.")
    a = res.channels[nombre]
    return _png(a if negativo else 255 - a)


@router.get("/{job_id}/trap.png")
def trap_png(job_id: str):
    res = _get(job_id)[0]
    if res.trap is None:
        raise UserError("Activa el auto-trap para ver el mapa de traps.")
    return _png(res.trap.trap_map)


@router.get("/{job_id}/prueba.png")
def reg_png(job_id: str):
    from app.modules.tools import registration_check as rc
    res = _get(job_id)[0]
    if res.reg_after is None:
        raise UserError("La prueba de movimiento no está disponible para este modo.")
    return _png(rc.side_by_side(res.reg_before, res.reg_after))


@router.get("/{job_id}/de.png")
def de_png(job_id: str):
    res = _get(job_id)[0]
    if res.de_map is None:
        raise UserError("Este modo no calcula ΔE.")
    return _png(raster.de_heatmap(res.de_map))


class Export(BaseModel):
    trama: dict | None = None
    dpi_salida: float = 600.0
    pdf: bool = True


@router.post("/{job_id}/exportar")
def export(job_id: str, body: Export):
    res, dpi, params = _get(job_id)
    data = raster_export.export_zip(res, dpi, params, body.trama, body.pdf, body.dpi_salida)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="separacion.zip"'})
