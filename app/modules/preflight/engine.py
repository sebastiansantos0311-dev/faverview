"""Motor de preflight (S6 §10.1): reglas con perfiles JSON, sobre PyMuPDF/pikepdf y el análisis de placas de S2."""
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image

from app.config import DATOS_DIR
from app.core import ghostscript
from app.core.errors import UserError
from app.core.pdfinfo import read_pdf_info
from app.core.units import mm_to_pt, pt_to_mm
from app.modules.separate import analysis
from app.modules.separate.pdf_inks import read_inventory
from app.modules.separate.pdf_render import render_plates

PROFILES_DIR = Path(__file__).with_name("perfiles")
USER_PROFILES = DATOS_DIR / "preflight_perfiles"
DPI = 150          # los bbox de los hallazgos son px a esta resolución (igual que la separación de S2)
SEV_ORDER = {"error": 0, "advertencia": 1, "info": 2}

RULE_NAMES = {
    "fuentes_no_incrustadas": "Fuentes no incrustadas", "fuentes_type3": "Fuentes Type 3", "resolucion": "Resolución de imágenes",
    "espacios_color": "Espacios de color", "tintas_directas_max": "Número de tintas directas", "tintas_duplicadas": "Tintas duplicadas",
    "tac": "Cobertura total (TAC)", "linea_fina": "Líneas finas", "texto_pequeno": "Texto pequeño",
    "negro_enriquecido_texto": "Negro enriquecido en texto", "sobreimpresion": "Sobreimpresión (blanco, barniz, técnicas)",
    "sangrado": "Sangrado", "trimbox_ausente": "TrimBox ausente", "zona_segura": "Objetos cerca del corte",
    "transparencias": "Transparencias", "capas_ocultas": "Capas ocultas", "anotaciones": "Anotaciones y formularios",
    "pdfx": "Versión PDF/X", "output_intent": "OutputIntent", "jpeg_calidad": "Compresión JPEG fuerte",
}


@dataclass
class Finding:
    regla: str
    severidad: str
    mensaje: str
    pagina: int = 1
    bbox: list | None = None       # [x, y, w, h] en px a DPI

    def to_dict(self) -> dict:
        return {"regla": self.regla, "nombre": RULE_NAMES.get(self.regla, self.regla), "severidad": self.severidad,
                "mensaje": self.mensaje, "pagina": self.pagina, "bbox": self.bbox}


# ---------------------------------------------------------------- perfiles
def list_profiles() -> list[dict]:
    out = []
    for d, own in ((PROFILES_DIR, False), (USER_PROFILES, True)):
        if d.exists():
            for f in sorted(d.glob("*.json")):
                try:
                    p = json.loads(f.read_text(encoding="utf-8"))
                    out.append({"id": f.stem, "nombre": p.get("nombre", f.stem), "descripcion": p.get("descripcion", ""), "propio": own})
                except Exception:
                    pass
    return out


def load_profile(pid: str) -> dict:
    if not re.match(r"^[\w\-]+$", pid or ""):
        raise UserError("Perfil no válido.")
    for d in (USER_PROFILES, PROFILES_DIR):
        f = d / f"{pid}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    raise UserError("No existe ese perfil de preflight.")


def save_profile(pid: str, prof: dict) -> None:
    if not re.match(r"^[\w\-]+$", pid or ""):
        raise UserError("El identificador del perfil solo admite letras, números, _ y -.")
    USER_PROFILES.mkdir(parents=True, exist_ok=True)
    (USER_PROFILES / f"{pid}.json").write_text(json.dumps(prof, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- utilidades
def _bbox_px(rect, page_rect=None, dpi=DPI):
    s = dpi / 72.0
    r = pymupdf.Rect(rect)
    if page_rect is not None:
        r = pymupdf.Rect(r.x0 - page_rect.x0, r.y0 - page_rect.y0, r.x1 - page_rect.x0, r.y1 - page_rect.y0)
    return [int(r.x0 * s), int(r.y0 * s), max(2, int(r.width * s)), max(2, int(r.height * s))]


def jpeg_quality(data: bytes) -> float | None:
    """Estimación de la calidad JPEG (1–100) por la tabla de cuantización de luminancia."""
    try:
        q = Image.open(io.BytesIO(data)).quantization[0]
    except Exception:
        return None
    std = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
           18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
    scale = 100.0 * sum(q) / sum(std)
    return round(5000 / scale if scale > 100 else (200 - scale) / 2, 1)


# ---------------------------------------------------------------- reglas
class Ctx:
    def __init__(self, path, prof):
        self.path = Path(path)
        self.prof = prof
        self.rules = prof.get("reglas", {})
        self.doc = pymupdf.open(str(path))
        self.info = read_pdf_info(path)
        self.inv = read_inventory(path)
        self.findings: list[Finding] = []
        self.notes: list[str] = []

    def on(self, rid):
        r = self.rules.get(rid) or {}
        return r.get("activa", False), r

    def add(self, rid, r, msg, page=1, bbox=None, sev=None):
        self.findings.append(Finding(rid, sev or r.get("severidad", "advertencia"), msg, page, bbox))


def rule_fonts(c: Ctx):
    on1, r1 = c.on("fuentes_no_incrustadas")
    on2, r2 = c.on("fuentes_type3")
    seen = set()
    for pno, page in enumerate(c.doc, 1):
        for f in page.get_fonts(full=True):
            xref, ext, ftype, base = f[0], f[1], f[2], f[3]
            if xref in seen:
                continue
            seen.add(xref)
            if on1 and ext == "n/a" and ftype != "Type3":
                c.add("fuentes_no_incrustadas", r1, f"La fuente «{base}» no está incrustada (página {pno}). Incrústala al exportar el PDF.", pno)
            if on2 and ftype == "Type3":
                c.add("fuentes_type3", r2, f"La fuente «{base}» es de tipo Type 3: puede imprimirse peor y no se puede editar.", pno)


def rule_images(c: Ctx):
    on, r = c.on("resolucion")
    onj, rj = c.on("jpeg_calidad")
    if not (on or onj):
        return
    seen_j = set()
    for pno, page in enumerate(c.doc, 1):
        for im in page.get_image_info(xrefs=True):
            bb = pymupdf.Rect(im["bbox"])
            if bb.width < 1 or bb.height < 1:
                continue
            if on:
                ppi = min(im["width"] / (bb.width / 72), im["height"] / (bb.height / 72))
                n, bpc = im.get("colorspace", 3), im.get("bpc", 8)
                kind, need = ("bn", r.get("bn_min", 800)) if bpc == 1 else (("gris", r.get("gris_min", 250)) if n == 1 else ("color", r.get("color_min", 250)))
                if ppi < need:
                    c.add("resolucion", r, f"Imagen de {ppi:.0f} ppi al tamaño colocado (mínimo {need} para {kind}).", pno, _bbox_px(bb, page.rect))
            xref = im.get("xref")
            if onj and xref and xref not in seen_j:
                seen_j.add(xref)
                try:
                    if "DCTDecode" in (c.doc.xref_get_key(xref, "Filter")[1] or ""):
                        q = jpeg_quality(c.doc.xref_stream_raw(xref))
                        if q is not None and q < rj.get("min", 60):
                            c.add("jpeg_calidad", rj, f"Imagen JPEG con compresión fuerte (calidad estimada ≈ {q:.0f}, mínimo {rj.get('min', 60)}).",
                                  pno, _bbox_px(bb, page.rect))
                except Exception:
                    pass


def rule_inks(c: Ctx):
    on, r = c.on("espacios_color")
    if on:
        names = {"DeviceRGB": "RGB", "ICC-RGB": "RGB (ICC)", "Lab": "Lab"}
        forb = set(r.get("prohibidos", []))
        for k, n in c.inv.process_used.items():
            lab = names.get(k)
            if lab and (lab.split(" ")[0] in forb):
                c.add("espacios_color", r, f"Hay {n} objeto(s) en {lab}: conviértelos a las tintas de impresión.")
    on, r = c.on("tintas_directas_max")
    if on:
        spots = [i for i in c.inv.inks if i.kind == "spot"]
        if len(spots) > r.get("max", 4):
            c.add("tintas_directas_max", r, f"El trabajo usa {len(spots)} tintas directas (máximo del perfil: {r.get('max')}).")
    on, r = c.on("tintas_duplicadas")
    if on:
        for i in c.inv.inks:
            if len(i.variants) > 1:
                c.add("tintas_duplicadas", r, f"La tinta «{i.name}» aparece con nombres distintos: {', '.join(sorted(i.variants))}.")


def rule_boxes(c: Ctx):
    on, r = c.on("sangrado")
    ont, rt = c.on("trimbox_ausente")
    for b in c.info.boxes:
        if ont and not b.has_trim:
            c.add("trimbox_ausente", rt, "La página no tiene TrimBox: no se sabe dónde se corta.", b.index + 1)
        if on:
            if not b.has_bleed:
                c.add("sangrado", r, "La página no define BleedBox (sangrado).", b.index + 1)
            else:
                m = min(b.bleed_mm().values())
                if m < r.get("min_mm", 3) - 0.01:
                    c.add("sangrado", r, f"Sangrado de {m:.1f} mm (mínimo {r.get('min_mm', 3)} mm).", b.index + 1)
    on, r = c.on("zona_segura")
    if on:
        safe = mm_to_pt(r.get("mm", 3))
        for pno, page in enumerate(c.doc, 1):
            try:
                trim = pymupdf.Rect(page.trimbox)
                if trim.is_empty or trim == page.rect:
                    continue
            except Exception:
                continue
            inner = pymupdf.Rect(trim.x0 + safe, trim.y0 + safe, trim.x1 - safe, trim.y1 - safe)
            for b in page.get_text("blocks"):
                bb = pymupdf.Rect(b[:4])
                if trim.contains(bb) and not inner.contains(bb) and str(b[4]).strip():
                    c.add("zona_segura", r, f"Texto a menos de {r.get('mm', 3)} mm del corte: «{str(b[4]).strip()[:30]}».", pno,
                          _bbox_px(bb, page.rect))


def rule_structure(c: Ctx):
    on, r = c.on("transparencias")
    if on and c.info.has_transparency:
        c.add("transparencias", r, f"Hay transparencias en las páginas {', '.join(map(str, c.info.transparency_pages))}.")
    on, r = c.on("capas_ocultas")
    if on:
        for l in c.info.layers:
            if not l["visible"]:
                c.add("capas_ocultas", r, f"La capa «{l['nombre']}» está oculta pero sigue en el archivo.")
    on, r = c.on("anotaciones")
    if on:
        for pno, page in enumerate(c.doc, 1):
            for a in list(page.annots() or []) + list(page.widgets() or []):
                c.add("anotaciones", r, f"Anotación o campo de formulario en la página {pno} (puede imprimirse o estorbar).", pno,
                      _bbox_px(a.rect, page.rect))
    on, r = c.on("pdfx")
    if on and r.get("requerido"):
        if not c.info.pdfx_version or r["requerido"].replace("PDF/", "") not in c.info.pdfx_version.replace("PDF/", ""):
            c.add("pdfx", r, f"Se pedía {r['requerido']} y el archivo declara: {c.info.pdfx_version or 'ninguna versión PDF/X'}.")
    on, r = c.on("output_intent")
    if on and not c.info.output_intents:
        c.add("output_intent", r, "El PDF no tiene OutputIntent (condición de impresión).")


def rule_plates(c: Ctx):
    """Reglas que necesitan las placas (TAC, líneas finas, texto pequeño, sobreimpresión)."""
    keys = ("tac", "linea_fina", "texto_pequeno", "negro_enriquecido_texto", "sobreimpresion")
    if not any(c.on(k)[0] for k in keys):
        return
    if not ghostscript.available():
        c.notes.append("No se comprobó cobertura, líneas, texto ni sobreimpresión: falta Ghostscript.")
        return
    for pno in range(min(len(c.doc), 20)):
        plates = render_plates(c.path, pno, DPI)
        meta = {i.name: {"tipo": i.kind} for i in c.inv.inks}
        page = pno + 1
        on, r = c.on("tac")
        if on:
            for reg in analysis.tac_regions(analysis.tac_map(plates, meta), r.get("limite", 300), plates.dpi):
                c.add("tac", r, f"Cobertura total de {reg['max']:.0f} % (límite {r.get('limite', 300)} %).", page, reg["bbox"])
        on, r = c.on("linea_fina")
        if on:
            for f in analysis.check_thin_lines(plates, c.path, pno, r.get("min_mm", 0.1)):
                c.add("linea_fina", r, f.mensaje, page, f.bbox)
        ont, rt = c.on("texto_pequeno")
        onn, rn = c.on("negro_enriquecido_texto")
        if ont or onn:
            for f in analysis.check_text(plates, c.path, pno, rn.get("max_pt", 12), rt.get("min_pt", 6)):
                if f.id == "texto_pequeno_multitinta" and ont:
                    c.add("texto_pequeno", rt, f.mensaje, page, f.bbox)
                elif f.id == "negro_enriquecido" and onn:
                    c.add("negro_enriquecido_texto", rn, f.mensaje, page, f.bbox)
            if ont:
                for size, text, bbox in analysis._text_spans(c.path, pno, plates.dpi):
                    if size < rt.get("min_pt", 6):
                        c.add("texto_pequeno", rt, f"Texto de {size:.1f} pt (mínimo {rt.get('min_pt', 6)} pt): «{text[:30]}».", page, bbox)
        on, r = c.on("sobreimpresion")
        if on:
            for f in analysis.check_overprint(plates, c.path, pno, c.inv, meta):
                c.add("sobreimpresion", r, f.mensaje, page, f.bbox, "error" if f.severidad == "error" else None)


RULES = [rule_fonts, rule_images, rule_inks, rule_boxes, rule_structure, rule_plates]


def run_preflight(path, profile: str | dict = "offset_hoja", progress=None) -> dict:
    prof = load_profile(profile) if isinstance(profile, str) else profile
    try:
        c = Ctx(path, prof)
    except UserError:
        raise
    except Exception:
        raise UserError("El PDF está dañado o no se puede abrir.")
    try:
        for i, fn in enumerate(RULES):
            if progress:
                progress("Revisando", 0.1 + 0.8 * i / len(RULES), fn.__doc__.split(".")[0] if fn.__doc__ else "Revisando el PDF…")
            fn(c)
    finally:
        pages = len(c.doc)
        c.doc.close()
    finds = sorted(c.findings, key=lambda f: (SEV_ORDER.get(f.severidad, 9), f.pagina, f.regla))
    return {"perfil": prof.get("nombre", ""), "paginas": pages, "hallazgos": [f.to_dict() for f in finds],
            "resumen": {s: sum(1 for f in finds if f.severidad == s) for s in SEV_ORDER}, "notas": c.notes, "dpi": DPI}
