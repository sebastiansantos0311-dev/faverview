"""Trap vectorial de un PDF de arte plano para el plugin (PLUGIN P7): render → mapa planar → cadenas → trazos de trap en sobreimpresión.

Solo arte vectorial plano. Con degradados, transparencias o imágenes se avisa y se ofrece la exportación de placas con trap (ráster)."""
import re
from dataclasses import dataclass

import numpy as np
import pikepdf
import pymupdf

from app.core.press import PressProfile
from app.modules.separate import raster
from app.modules.separate.pdf_inks import read_inventory
from app.modules.separate.pdf_render import render_plates
from app.modules.tools import registration_check as rc
from app.modules.vectorize import boundaries, export, pipeline, traps

PAPER = (95.0, 0.0, -2.0)


@dataclass
class FlatCheck:
    plano: bool
    motivos: list


def is_flat_art(pdf_path, page: int = 0) -> FlatCheck:
    """Arte plano: sin imágenes, sombreados (degradados), transparencias ni patrones."""
    motivos = []
    with pymupdf.open(str(pdf_path)) as doc:
        if doc[page].get_images(full=True):
            motivos.append("imágenes")
    with pikepdf.open(str(pdf_path)) as pdf:
        pg = pdf.pages[page].obj
        res = pg.get("/Resources") or pikepdf.Dictionary()
        if "/Shading" in res and len(res["/Shading"]):
            motivos.append("degradados")
        if "/Pattern" in res and len(res["/Pattern"]):
            motivos.append("patrones")
        if "/Group" in pg and str(pg["/Group"].get("/S")) == "/Transparency" and re.search(rb"/(ca|CA)\s+0?\.\d", pg.Contents.read_bytes() if not isinstance(pg.get("/Contents"), pikepdf.Array) else b""):
            motivos.append("transparencias")
        for k, egs in (res.get("/ExtGState") or {}).items():
            for key in ("/ca", "/CA"):
                if key in egs and float(egs[key]) < 1:
                    motivos.append("transparencias")
            if "/SMask" in egs and str(egs["/SMask"]) != "/None":
                motivos.append("transparencias")
    return FlatCheck(not motivos, sorted(set(motivos)))


def analyze(pdf_path, press: PressProfile, page: int = 0, dpi: float = 600):
    """Prueba de movimiento del PDF tal cual: filetes (mm² y bbox en pt) y el mapa."""
    plates = render_plates(pdf_path, page, dpi)
    inv = read_inventory(pdf_path)
    meta = {i.name: {"tipo": i.kind, "lab": i.lab} for i in inv.inks}
    r = rc.check(plates, press, meta)
    return plates, meta, r


def filete_boxes(r, plates, page_h_pt: float, max_n: int = 40) -> list[dict]:
    """Zonas con filetes como bbox en pt PDF (origen abajo-izquierda)."""
    import cv2
    mask = (r.mapa == np.array([255, 0, 200])).all(-1).astype(np.uint8)
    mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask)
    k = 72.0 / plates.dpi
    out = []
    for i in range(1, min(n, max_n + 1)):
        x, y, w, h = [int(v) for v in st[i, :4]]
        out.append({"bbox_pt": [round(x * k, 3), round(page_h_pt - (y + h) * k, 3), round((x + w) * k, 3), round(page_h_pt - y * k, 3)],
                    "mm2": round(float(np.count_nonzero((lab == i) & (mask > 0))) / (plates.dpi / 25.4) ** 2, 4)})
    return out


def build_trap_pdf(pdf_path, press: PressProfile, page: int = 0, dpi: float = 600) -> tuple[bytes, list, list]:
    """PDF (mismo tamaño que la mesa) con SOLO los trazos de trap, en las mismas tintas directas (mismos nombres), en sobreimpresión."""
    plates = render_plates(pdf_path, page, dpi)
    inv = read_inventory(pdf_path)
    kinds = {i.name: i.kind for i in inv.inks}
    labs = {i.name: i.lab for i in inv.inks}
    names = [n for n in plates.names if not plates.empty(n) and kinds.get(n, "process") not in ("technical", "varnish", "white")]
    if len(names) < 2:
        return b"", [], ["El arte tiene menos de dos tintas que se toquen: no hace falta trap."]
    stack = np.stack([plates.arrays[n] for n in names])
    top = stack.argmax(0)
    inked = stack.max(0) >= 128
    paper_id = len(names)
    labels = np.where(inked, top, paper_id).astype(np.int32)
    pal = [raster.Ink(n, tuple(labs.get(n) or _default_lab(n))) for n in names] + [raster.Ink("Papel", PAPER)]
    regs, strokes, edges = pipeline.trace(labels, pal, fit_tol=0.8, corner_angle=60.0, smooth=1.6, scale=1.0, prims=False, clean=True, mode="sin_solapes")
    h, w = labels.shape
    res = pipeline.VectorResult(w, h, plates.dpi, pal, regs, {}, "sin_solapes", 1.0, labels, {}, [], [], [], None, edges, None)
    with pymupdf.open(str(pdf_path)) as doc:
        r = doc[page].rect
        width_mm = r.width / 72 * 25.4
    groups = traps.build(res, press, 25.4 / plates.dpi)
    if not groups:
        return b"", [], ["Con este perfil no se generó ningún trap (¿tolerancia 0 o sin bordes entre tintas?)."]
    pdf = export.to_pdf(res, width_mm, "separation", [i.name for i in pal], trap=press, sin_fondo=True, solo_traps=True, exact_names=True)
    return pdf, traps.summary(groups, 25.4 / plates.dpi), []


def _default_lab(name: str):
    from app.core import inks as inkmod
    ref = {i.name: i for i in inkmod.builtin_library().inks}.get(name)
    return tuple(ref.lab) if ref and ref.lab else (50.0, 0.0, 0.0)
