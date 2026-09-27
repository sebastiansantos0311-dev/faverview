"""Rutas orientadas al plugin de Illustrator (PLUGIN P0). Finas: reutilizan los módulos de la suite.

Convenciones para el plugin:
- Todos los bbox salen en **puntos PDF de la página enviada**: `[x0, y0, x1, y1]`, origen abajo-izquierda, sin rotación, más `page_size_pt`.
- Las operaciones largas son trabajos (`/api/jobs/{id}`, con progreso y cancelar); los archivos resultantes se bajan de
  `/api/plugin/{trabajo}/archivo/{nombre}`.
- Todas las rutas exigen el token (`X-FAVERVIEW-Token`)."""
import json
import re
import shutil
import uuid
from pathlib import Path

import cv2
import pymupdf
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import RESULTS_DIR, UPLOADS_DIR, load_config
from app.core import jobs, plugin_auth, tools
from app.core.errors import UserError
from app.core.files import check_job, save_upload
from app.version import get_version

router = APIRouter(prefix="/api/plugin")
OUT_DIR = RESULTS_DIR / "plugin"
NAME_RE = re.compile(r"^[\w.\-]+$")


# ---------------------------------------------------------------- utilidades
def page_info(pdf_path, page: int = 0) -> dict:
    with pymupdf.open(str(pdf_path)) as doc:
        r = doc[min(max(page, 0), len(doc) - 1)].rect
        return {"page_size_pt": [round(r.width, 3), round(r.height, 3)], "paginas": len(doc)}


def px_to_pt_bbox(bbox_xywh, dpi: float, page_h_pt: float) -> list[float]:
    """[x, y, w, h] en px (origen arriba-izquierda) a [x0, y0, x1, y1] en pt (origen abajo-izquierda)."""
    x, y, w, h = bbox_xywh
    k = 72.0 / dpi
    return [round(x * k, 3), round(page_h_pt - (y + h) * k, 3), round((x + w) * k, 3), round(page_h_pt - y * k, 3)]


def _job_dir(job_id: str) -> Path:
    d = OUT_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(file: UploadFile, dest_dir: Path, stem: str, allowed):
    cfg = load_config()
    return save_upload(file, dest_dir, stem, cfg["max_upload_mb"], allowed=allowed)


IMG = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def _new_job() -> tuple[str, Path]:
    jid = uuid.uuid4().hex[:12]
    return jid, _job_dir(jid)


def _files(d: Path, names) -> list[dict]:
    return [{"nombre": n, "url": f"/api/plugin/{d.name}/archivo/{n}"} for n in names if (d / n).exists()]


# ---------------------------------------------------------------- generales
@router.get("/handshake")
def handshake():
    st = tools.status()
    modulos = {}
    for k, m in tools.MODULOS.items():
        falta = [h for h in m["requiere"] if not st[h]["ok"]]
        modulos[k] = {"nombre": m["nombre"], "habilitado": not falta}
    return {"version": get_version(), "api_version": plugin_auth.API_VERSION, "modulos": modulos, "max_upload_mb": load_config()["max_upload_mb"],
            "herramientas": {k: {"ok": v["ok"], "version": v["version"]} for k, v in st.items()}}


@router.get("/{job_id}/archivo/{nombre}")
def get_file(job_id: str, nombre: str):
    check_job(job_id)
    if not NAME_RE.match(nombre):
        raise UserError("Nombre de archivo no válido.")
    f = OUT_DIR / job_id / nombre
    if not f.exists():
        raise UserError("Ese archivo no existe (¿el trabajo terminó?).")
    return FileResponse(f)


# ---------------------------------------------------------------- vectorizar
@router.post("/vectorizar")
def vectorize(file: UploadFile = File(...), parametros: str = Form("{}"), tamano_mm: float | None = Form(None)):
    """Imagen → PDF vectorial con tintas directas (y capa de traps opcional). `parametros`: JSON del vectorizador."""
    p = json.loads(parametros or "{}")
    jid, d = _new_job()
    src = _save(file, d, "entrada", IMG)

    def work(progress):
        from app.core import press
        from app.modules.separate import raster
        from app.modules.vectorize import export, pipeline
        progress("Vectorizando", 0.2, "Vectorizando…")
        rgb, dpi = raster.load_image(src)
        d0 = p.get("dpi") or (dpi[0] if dpi else None)
        pal = [raster.Ink(i["name"], tuple(i["lab"])) for i in p.get("tintas", [])] or None
        res = pipeline.vectorize(rgb, d0, preset=p.get("preset"), palette=pal, k_max=p.get("k_max", 8), min_detail_mm=p.get("detalle_min_mm", 0.15),
                                 geometria_limpia=bool(p.get("geometria_limpia")), primitives=bool(p.get("primitivas")), mode="sin_solapes")
        pf = press.resolve(p.get("trap_prensa"), p.get("trap_tolerancia_mm")) if (p.get("trap_prensa") or p.get("trap_tolerancia_mm") is not None) else None
        names = [i.name for i in res.palette]
        (d / "vector.pdf").write_bytes(export.to_pdf(res, tamano_mm, "separation", names, trap=pf))
        (d / "vector.svg").write_text(export.to_svg(res, tamano_mm), encoding="utf-8")
        ok, png = cv2.imencode(".png", export.render(res, min(int(res.width), 800), int(min(int(res.width), 800) * res.height / res.width))[..., ::-1])
        (d / "vista.png").write_bytes(png.tobytes())
        return {"estadisticas": res.stats, "colores": [{"nombre": i.name, "lab": list(i.lab)} for i in res.palette], "con_trap": pf is not None,
                "archivos": _files(d, ["vector.pdf", "vista.png"])}

    jobs.start(jid, work)
    return {"job_id": jid}


# ---------------------------------------------------------------- preflight
@router.post("/preflight")
def preflight(file: UploadFile = File(...), perfil: str = Form("offset_hoja")):
    jid, d = _new_job()
    src = _save(file, d, "entrada", {".pdf"})

    def work(progress):
        from app.modules.preflight import engine
        info = page_info(src)
        res = engine.run_preflight(src, perfil, progress)
        with pymupdf.open(str(src)) as doc:
            heights = [pg.rect.height for pg in doc]
        for f in res["hallazgos"]:
            if f.get("bbox"):
                f["bbox_pt"] = px_to_pt_bbox(f["bbox"], res["dpi"], heights[min(f["pagina"] - 1, len(heights) - 1)])
        return {**res, **info}

    jobs.start(jid, work)
    return {"job_id": jid}


# ---------------------------------------------------------------- separar
@router.post("/separar")
def separate(file: UploadFile = File(...), pagina: int = Form(1), dpi: float = Form(150), perfil_maquina: str | None = Form(None),
             tolerancia_mm: float | None = Form(None), limite_tac: float = Form(300)):
    """Sube el PDF al módulo Separar y lanza el análisis. Devuelve el `job_id` del PDF (para las URLs de placas y mapas) y el del análisis."""
    from app.modules.separate import api as sep
    up = sep.upload(file)
    aid = sep.analyze(up["job_id"], pagina, dpi, limite_tac)["job_id"]
    base = f"/api/separar/pdf/{up['job_id']}"
    tq = f"&prensa={perfil_maquina}" if perfil_maquina else ""
    tq += f"&tolerancia_mm={tolerancia_mm}" if tolerancia_mm is not None else ""
    return {"job_id": up["job_id"], "analisis_id": aid, "inventario": up["inventario"], "paginas": up["paginas"],
            "urls": {"composicion": f"{base}/composicion.png?pagina={pagina}&dpi={dpi}", "placa": f"{base}/placa.png?pagina={pagina}&dpi={dpi}&nombre=",
                     "tac": f"{base}/tac.png?pagina={pagina}&dpi={dpi}&limite={limite_tac}", "sonda": f"{base}/sonda?pagina={pagina}&dpi={dpi}",
                     "exportar": f"{base}/exportar", "trap": f"{base}/trap.png?pagina={pagina}&dpi={max(dpi, 300)}{tq}"}}


@router.post("/separar/hallazgos_pt")
def findings_pt(hallazgos: list[dict], alto_pt: float, dpi: float = 150):
    """Convierte los hallazgos del análisis de separación (bbox en px) a puntos PDF."""
    out = []
    for f in hallazgos:
        g = dict(f)
        if f.get("bbox"):
            g["bbox_pt"] = px_to_pt_bbox(f["bbox"], dpi, alto_pt)
        out.append(g)
    return out


# ---------------------------------------------------------------- comparar
@router.post("/comparar")
def compare(arte: UploadFile = File(...), mesa: UploadFile = File(...), pagina: int = Form(1)):
    """Arte del cliente (imagen o PDF) contra la mesa de trabajo exportada (PDF)."""
    jid, d = _new_job()
    up = UPLOADS_DIR / jid
    a = _save(arte, up, "client", IMG | {".pdf"})
    b = _save(mesa, up, "design", {".pdf"})

    def work(progress):
        from app.modules.compare.pipeline import run_comparison
        info = page_info(b, pagina - 1)
        res = run_comparison(jid, a, b, {}, 0, pagina - 1, arte.filename or "", mesa.filename or "", persist=False, out_dir=d, progress=progress)
        w_pt, h_pt = info["page_size_pt"]
        diffs = []
        for x in res.differences:
            bx, by, bw, bh = x.bbox
            kx, ky = w_pt / res.width, h_pt / res.height
            diffs.append({"id": x.id, "categoria": x.category, "subtipo": x.subtype, "severidad": x.severity, "mensaje": x.message,
                          "esperado": x.expected, "encontrado": x.found,
                          "bbox_pt": [round(bx * kx, 3), round(h_pt - (by + bh) * ky, 3), round((bx + bw) * kx, 3), round(h_pt - by * ky, 3)]})
        return {"estado": res.status, "puntajes": res.scores, "conteo": res.counts, "diferencias": diffs, "avisos": res.warnings, **info}

    jobs.start(jid, work)
    return {"job_id": jid}


# ---------------------------------------------------------------- códigos y braille
class CodigoIn(BaseModel):
    tipo: str = "ean13"
    datos: str = ""
    magnificacion: float = 1.0
    x_mm: float | None = None
    altura_mm: float | None = None
    bwr_um: float = 0.0
    texto_legible: bool = True
    tinta: dict | None = None          # {"name": ..., "lab": [L, a, b]}
    vista: bool = False                # true: JSON con SVG y avisos (validación en vivo); false: el PDF


@router.post("/codigo")
def barcode(p: CodigoIn):
    from app.modules.barcodes import generate as g
    lab = tuple(p.tinta["lab"]) if p.tinta else (16.0, 0.0, 0.0)
    lay = g.layout(p.tipo, p.datos, magnificacion=p.magnificacion, x_mm=p.x_mm, altura_mm=p.altura_mm, bwr_mm=p.bwr_um / 1000,
                   texto_legible=p.texto_legible, ink_lab=lab)
    if p.vista:
        return {"svg": g.to_svg(lay), "avisos": lay.warnings, "ancho_mm": round(lay.width, 3), "alto_mm": round(lay.height, 3), "texto": lay.datos}
    pdf = g.to_pdf(lay, p.tinta["name"] if p.tinta else None, lab)
    return Response(pdf, media_type="application/pdf", headers={"X-Ancho-mm": f"{lay.width:.3f}", "X-Alto-mm": f"{lay.height:.3f}"})


class BrailleIn(BaseModel):
    texto: str
    ancho_mm: float = 60.0
    geometria: dict | None = None
    tinta: str = "Braille"
    vista: bool = False


@router.post("/braille")
def braille(p: BrailleIn):
    from app.modules.tools import braille as br
    lay = br.layout(p.texto, p.ancho_mm, p.geometria)
    if p.vista:
        return {"svg": br.to_svg(lay), "unicode": lay["unicode"], "ancho_mm": lay["ancho_mm"], "alto_mm": lay["alto_mm"], "avisos": lay["avisos"]}
    return Response(br.to_pdf(lay, p.tinta), media_type="application/pdf", headers={"X-Ancho-mm": str(lay["ancho_mm"]), "X-Alto-mm": str(lay["alto_mm"])})


@router.post("/codigos/verificar")
def verify_codes(file: UploadFile = File(...), dpi: int = Form(600), direccion: str = Form("")):
    """Verifica los códigos de una mesa exportada; añade el bbox en pt de cada código."""
    from app.modules.barcodes import verify as v
    jid, d = _new_job()
    src = _save(file, d, "entrada", {".pdf"} | IMG)
    r = v.verify(src, min(max(dpi, 150), 1200), 1, direccion if direccion in ("horizontal", "vertical") else None)
    if src.suffix.lower() == ".pdf":
        h = page_info(src)["page_size_pt"][1]
        for c in r["codigos"]:
            c["bbox_pt"] = px_to_pt_bbox(c["bbox"], r["dpi"], h)
    shutil.rmtree(d, ignore_errors=True)
    return r


class NombresIn(BaseModel):
    nombres: list[str]


@router.post("/tintas/clasificar")
def classify_inks(p: NombresIn):
    """Tipo (proceso, directa, blanco, barniz, técnica) y nombre normalizado de cada tinta (para las correcciones nativas del plugin)."""
    from app.core import inks as inkmod
    return {n: {"tipo": inkmod.classify_ink(n), "norm": inkmod.normalize_name(n)} for n in p.nombres[:500]}


@router.post("/trap")
def trap(file: UploadFile = File(...), perfil: str = Form("serigrafia_textil_automatica"), tolerancia_mm: float | None = Form(None),
         crear_vectorial: bool = Form(False), pagina: int = Form(1), dpi: float = Form(600)):
    """Analiza el registro de la mesa (prueba de movimiento) y, si se pide y el arte es plano, crea el PDF de traps vectoriales."""
    jid, d = _new_job()
    src = _save(file, d, "entrada", {".pdf"})

    def work(progress):
        from app.core import press
        from app.modules.plugin import vector_trap as vt
        pf = press.resolve(perfil, tolerancia_mm)
        info = page_info(src, pagina - 1)
        progress("Analizando", 0.2, "Separando y comprobando el registro…")
        plates, meta, r = vt.analyze(src, pf, pagina - 1, dpi)
        out = {"perfil": pf.nombre, "tolerancia_mm": pf.tolerancia_mm, "registro": r.to_dict(), "filetes": vt.filete_boxes(r, plates, info["page_size_pt"][1]),
               "ok": r.filetes_px == 0, "avisos": ["Estimación orientativa: confirma con tu imprenta."], **info}
        flat = vt.is_flat_art(src, pagina - 1)
        out["arte_plano"] = flat.plano
        out["vectorial"] = {"disponible": flat.plano, "motivos": flat.motivos}
        if crear_vectorial:
            if not flat.plano:
                out["vectorial"]["mensaje"] = "Este arte tiene " + ", ".join(flat.motivos) + ": usa la exportación de placas con trap (ráster) en FAVERVIEW."
            else:
                progress("Trap vectorial", 0.6, "Creando los traps vectoriales…")
                pdf, resumen, avisos = vt.build_trap_pdf(src, pf, pagina - 1, dpi)
                out["avisos"] += avisos
                if pdf:
                    (d / "traps.pdf").write_bytes(pdf)
                    out["vectorial"].update({"resumen": resumen, "archivos": _files(d, ["traps.pdf"])})
        return out

    jobs.start(jid, work)
    return {"job_id": jid}


@router.get("/prensas")
def presses():
    from app.core import press
    return press.list_profiles()
