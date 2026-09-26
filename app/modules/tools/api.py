"""Rutas de Herramientas (S7): trapping, step & repeat, distorsión flexo, braille, gama extendida y prueba en pantalla."""
import io
import json
import shutil
import threading
import uuid
import zipfile
from collections import OrderedDict

import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import UPLOADS_DIR, load_config
from app.core import inks as inkmod
from app.core import jobs
from app.core.errors import UserError
from app.core.files import check_job, find_upload, save_upload
from app.modules.separate import export as sep_export
from app.modules.separate import raster
from app.modules.separate.pdf_inks import read_inventory
from app.modules.separate.pdf_render import Plates, render_plates
from app.modules.tools import braille, flexo, gamut, imposition, trapping

router = APIRouter(prefix="/api/herramientas")
_TRAPS: "OrderedDict[str, tuple]" = OrderedDict()
_LOCK = threading.Lock()


def _pdf(job_id):
    check_job(job_id)
    d = UPLOADS_DIR / job_id
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    return find_upload(d, "original"), meta, d


def _meta(plates, pdf):
    by = {i.norm: i for i in read_inventory(pdf).inks}
    out = {}
    for n in plates.names:
        i = by.get(inkmod.normalize_name(n))
        if i is not None:
            out[n] = {"tipo": i.kind, "lab": i.lab}
    return out


def _png(img):
    img = np.asarray(img)
    ok, b = cv2.imencode(".png", img[..., ::-1] if img.ndim == 3 else img)
    return Response(b.tobytes(), media_type="image/png", headers={"Cache-Control": "no-store"})


def _attach(name):
    return {"Content-Disposition": f'attachment; filename="{name}"'}


@router.post("/pdf")
def upload(file: UploadFile = File(...)):
    cfg = load_config()
    job_id = uuid.uuid4().hex[:12]
    d = UPLOADS_DIR / job_id
    try:
        p = save_upload(file, d, "original", cfg["max_upload_mb"], allowed={".pdf"}, formats_msg="Sube un archivo PDF.")
        (d / "meta.json").write_text(json.dumps({"name": file.filename}), encoding="utf-8")
        inv = read_inventory(p)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return {"job_id": job_id, "nombre": file.filename, "tintas": [{"nombre": i.name, "tipo": i.kind, "lab": i.lab} for i in inv.inks]}


# ---------------------------------------------------------------- trapping
class TrapIn(BaseModel):
    proceso: str = "flexo"
    ancho_mm: float | None = None
    porcentaje: float = 100.0
    tac_max: float | None = 300.0
    dpi: float = 600.0
    pagina: int = 1
    tabla: list[list] | None = None      # [[A, B, mm], ...]


@router.post("/{job_id}/trapping")
def trap(job_id: str, p: TrapIn):
    pdf, meta, d = _pdf(job_id)

    def work(progress):
        progress("Separando", 0.1, "Separando en placas…")
        plates = render_plates(pdf, p.pagina - 1, p.dpi)
        m = _meta(plates, pdf)
        progress("Trapping", 0.6, "Calculando los traps…")
        tabla = {(a, b): float(mm) for a, b, mm in (p.tabla or [])}
        res = trapping.trap(plates, m, proceso=p.proceso, ancho_mm=p.ancho_mm, tabla=tabla, porcentaje=p.porcentaje, tac_max=p.tac_max)
        with _LOCK:
            _TRAPS[job_id] = (plates, res, m)
            while len(_TRAPS) > 3:
                _TRAPS.popitem(last=False)
        return {"traps": res.traps, "avisos": res.warnings, "placas": plates.names, "dpi": plates.dpi}

    aid = uuid.uuid4().hex[:12]
    jobs.start(aid, work)
    return {"job_id": aid}


def _trap_state(job_id):
    check_job(job_id)
    with _LOCK:
        s = _TRAPS.get(job_id)
    if not s:
        raise UserError("Primero calcula el trapping.")
    return s


@router.get("/{job_id}/trapping/mapa.png")
def trap_map(job_id: str):
    return _png(_trap_state(job_id)[1].trap_map)


@router.get("/{job_id}/trapping/registro.png")
def misreg(job_id: str, tinta: str, dx_um: float = 100.0, dy_um: float = 0.0, con_trap: bool = True):
    from app.modules.separate.pdf_render import compose
    plates, res, m = _trap_state(job_id)
    base = res.plates if con_trap else plates
    shifted = trapping.misregistration(base, tinta, dx_um, dy_um)
    return _png(compose(shifted, m))


@router.post("/{job_id}/trapping/exportar")
def trap_export(job_id: str):
    plates, res, m = _trap_state(job_id)
    data = sep_export.export_zip(res.plates, m, "tiff8", [])
    z = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            zout.writestr(n, zin.read(n))
        ok, b = cv2.imencode(".png", res.trap_map[..., ::-1])
        zout.writestr("mapa_de_traps.png", b.tobytes())
        zout.writestr("placas.pdf", sep_export.plates_pdf(res.plates))
        zout.writestr("traps.txt", "\n".join(f"{t['de']} bajo {t['bajo']}: {t['ancho_mm']} mm ({t['pixeles']} px)" for t in res.traps) + "\n" + "\n".join(res.warnings))
    return Response(z.getvalue(), media_type="application/zip", headers=_attach("trapping.zip"))


# ---------------------------------------------------------------- step & repeat
class StepIn(BaseModel):
    hoja_ancho: float = 300.0
    hoja_alto: float = 200.0
    columnas: int | None = None
    filas: int | None = None
    gap_x: float = 3.0
    gap_y: float = 3.0
    margen: list[float] = [10, 10, 10, 10]
    rot_filas: list[int] = [0]
    rot_columnas: list[int] = [0]
    desfase_fila_mm: float = 0.0
    desfase_col_mm: float = 0.0
    marcas: dict = {}
    trabajo: str = ""


@router.post("/{job_id}/imponer")
def step(job_id: str, p: StepIn):
    pdf, meta, d = _pdf(job_id)
    r = imposition.step_repeat(pdf, d / "imposicion.pdf", sheet_w=p.hoja_ancho, sheet_h=p.hoja_alto, cols=p.columnas, rows=p.filas,
                               gap_x=p.gap_x, gap_y=p.gap_y, margin=tuple(p.margen), rot_by_row=p.rot_filas, rot_by_col=p.rot_columnas,
                               stagger_row_mm=p.desfase_fila_mm, stagger_col_mm=p.desfase_col_mm, marks=p.marcas,
                               job_name=p.trabajo or meta.get("name", ""))
    return r


@router.get("/{job_id}/imposicion.pdf")
def step_pdf(job_id: str):
    _, _, d = _pdf(job_id)
    f = d / "imposicion.pdf"
    if not f.exists():
        raise UserError("Primero genera la imposición.")
    return FileResponse(f, media_type="application/pdf", filename="imposicion.pdf")


@router.get("/{job_id}/imposicion.png")
def step_png(job_id: str, dpi: int = 80):
    import pymupdf
    _, _, d = _pdf(job_id)
    f = d / "imposicion.pdf"
    if not f.exists():
        raise UserError("Primero genera la imposición.")
    with pymupdf.open(str(f)) as doc:
        return Response(doc[0].get_pixmap(dpi=min(max(dpi, 30), 200), alpha=False).tobytes("png"), media_type="image/png")


# ---------------------------------------------------------------- flexo
@router.get("/flexo/calcular")
def flexo_calc(k: float, repeticion: float):
    return {"distorsion_pct": round(flexo.distortion_pct(k, repeticion), 4), "nota": flexo.NOTE}


class FlexoIn(BaseModel):
    distorsion_pct: float | None = None
    k: float | None = None
    repeticion: float | None = None
    direccion: str = "vertical"
    nota: bool = True


@router.post("/{job_id}/flexo")
def flexo_apply(job_id: str, p: FlexoIn):
    pdf, meta, d = _pdf(job_id)
    pct = p.distorsion_pct
    if pct is None:
        if p.k is None or p.repeticion is None:
            raise UserError("Indica la distorsión en % o bien k y la repetición.")
        pct = flexo.distortion_pct(p.k, p.repeticion)
    return flexo.apply_distortion(pdf, d / "flexo.pdf", pct, p.direccion, p.nota)


@router.get("/{job_id}/flexo.pdf")
def flexo_pdf(job_id: str):
    _, _, d = _pdf(job_id)
    f = d / "flexo.pdf"
    if not f.exists():
        raise UserError("Primero aplica la distorsión.")
    return FileResponse(f, media_type="application/pdf", filename="distorsion_flexo.pdf")


# ---------------------------------------------------------------- braille
class BrailleIn(BaseModel):
    texto: str
    ancho_mm: float = 60.0
    formato: str = "vista"
    geometria: dict | None = None
    tinta: str = "Braille"


@router.post("/braille")
def braille_make(p: BrailleIn):
    lay = braille.layout(p.texto, p.ancho_mm, p.geometria)
    if p.formato == "vista":
        return {"svg": braille.to_svg(lay), "unicode": lay["unicode"], "ancho_mm": lay["ancho_mm"], "alto_mm": lay["alto_mm"],
                "celdas": lay["celdas"], "lineas": lay["lineas"], "avisos": lay["avisos"]}
    if p.formato == "svg":
        return Response(braille.to_svg(lay), media_type="image/svg+xml", headers=_attach("braille.svg"))
    if p.formato == "pdf":
        return Response(braille.to_pdf(lay, p.tinta), media_type="application/pdf", headers=_attach("braille.pdf"))
    raise UserError("Formato desconocido.")


# ---------------------------------------------------------------- gama extendida
class InkIn(BaseModel):
    name: str
    lab: list[float]
    opacity: float = 0.0


class GamutIn(BaseModel):
    fijas: list[InkIn]
    max_tintas: int = 3
    solo_reproducibles: bool = True


@router.post("/{job_id}/gamut")
def gamut_table(job_id: str, p: GamutIn):
    pdf, meta, d = _pdf(job_id)
    inv = read_inventory(pdf)
    targets = [{"name": i.name, "lab": i.lab} for i in inv.inks if i.kind == "spot" and i.lab]
    if not targets:
        raise UserError("El PDF no tiene tintas directas con color alternativo para convertir.")
    fijas = [raster.Ink(i.name, tuple(i.lab), i.opacity) for i in p.fijas]

    def work(progress):
        progress("Calculando", 0.2, "Buscando recetas…")
        tabla = gamut.recipes(targets, fijas, max_inks=p.max_tintas)
        (d / "gamut.json").write_text(json.dumps({"tabla": tabla, "fijas": [i.model_dump() for i in p.fijas]}), encoding="utf-8")
        return {"tabla": tabla, "nota": gamut.NOTE}

    aid = uuid.uuid4().hex[:12]
    jobs.start(aid, work)
    return {"job_id": aid}


@router.post("/{job_id}/gamut/aplicar")
def gamut_apply(job_id: str, solo_reproducibles: bool = True):
    pdf, meta, d = _pdf(job_id)
    f = d / "gamut.json"
    if not f.exists():
        raise UserError("Primero calcula la tabla de recetas.")
    st = json.loads(f.read_text(encoding="utf-8"))
    fijas = [raster.Ink(i["name"], tuple(i["lab"]), i.get("opacity", 0.0)) for i in st["fijas"]]
    return gamut.apply_to_pdf(pdf, d / "gamut.pdf", st["tabla"], fijas, solo_reproducibles)


@router.get("/{job_id}/gamut.pdf")
def gamut_pdf(job_id: str):
    _, _, d = _pdf(job_id)
    f = d / "gamut.pdf"
    if not f.exists():
        raise UserError("Primero aplica la gama extendida.")
    return FileResponse(f, media_type="application/pdf", filename="gama_extendida.pdf")


# ---------------------------------------------------------------- prueba en pantalla
@router.get("/{job_id}/prueba.png")
def soft_proof(job_id: str, sustrato: str = "Papel blanco", textura: str = "ninguna", ganancia: float = 0.0, sin_blanco: bool = False,
               dpi: float = 100.0, pagina: int = 1):
    pdf, _, _ = _pdf(job_id)
    plates = render_plates(pdf, pagina - 1, dpi)
    sub = raster.SUBSTRATES.get(sustrato, raster.PAPER)
    return _png(gamut.soft_proof(plates, _meta(plates, pdf), substrate_lab=sub, default_gain=ganancia / 100, sin_blanco=sin_blanco, textura=textura))


@router.get("/sustratos")
def substrates():
    return {k: list(v) for k, v in raster.SUBSTRATES.items()}


# ---------------------------------------------------------------- calibración (S3 §7.6)
class CalIn(BaseModel):
    tintas: list[InkIn]


@router.post("/calibracion/grafico")
def cal_chart(p: CalIn):
    from app.modules.separate import calibration
    return Response(calibration.chart_pdf([raster.Ink(i.name, tuple(i.lab)) for i in p.tintas]), media_type="application/pdf", headers=_attach("grafico_calibracion.pdf"))


@router.post("/calibracion/plantilla")
def cal_template(p: CalIn):
    from app.modules.separate import calibration
    return Response(calibration.template_csv([raster.Ink(i.name, tuple(i.lab)) for i in p.tintas]).encode("utf-8-sig"), media_type="text/csv",
                    headers=_attach("plantilla_medidas.csv"))


@router.post("/calibracion/ajustar")
def cal_fit(file: UploadFile = File(...), tintas: str = "", nombre: str = "Mi perfil"):
    from app.modules.separate import calibration
    lst = [raster.Ink(i["name"], tuple(i["lab"])) for i in json.loads(tintas or "[]")]
    if not lst:
        raise UserError("Indica las tintas del gráfico.")
    prof = calibration.fit(lst, calibration.parse_measurements(file.file.read(500_000).decode("utf-8-sig", "replace")))
    calibration.save_profile(nombre, prof)
    return prof


@router.get("/calibracion/perfiles")
def cal_profiles():
    from app.modules.separate import calibration
    return calibration.list_profiles()
