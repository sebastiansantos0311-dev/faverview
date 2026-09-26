"""Correcciones seguras de preflight (S6 §10.1): siempre sobre una copia, cada una opcional, con comprobación antes/después.

No se intenta incrustar fuentes que faltan (no están disponibles): solo se reporta."""
from pathlib import Path

import numpy as np
import pikepdf
import pymupdf

from app.core import inks as inkmod
from app.core.errors import UserError
from app.core.units import mm_to_pt
from app.modules.preflight.engine import run_preflight
from app.modules.separate import pdf_edit
from app.modules.separate.pdf_inks import _name, read_inventory

AVAILABLE = {
    "eliminar_anotaciones": "Eliminar anotaciones y campos de formulario",
    "unir_duplicadas": "Unir tintas duplicadas",
    "cajas": "Añadir TrimBox y BleedBox (indica el sangrado en mm)",
    "sobreimpresion_tecnicas": "Poner en sobreimpresión las tintas técnicas y el negro 100 % K",
}


def remove_annotations(pdf) -> int:
    n = 0
    for page in pdf.pages:
        if "/Annots" in page.obj:
            n += len(page.obj["/Annots"])
            del page.obj["/Annots"]
    if "/AcroForm" in pdf.Root:
        del pdf.Root["/AcroForm"]
    return n


def set_boxes(pdf, bleed_mm: float, trim_inset_mm: float | None = None) -> int:
    """TrimBox = CropBox reducida `trim_inset_mm` por lado (por defecto igual al sangrado); BleedBox = CropBox."""
    inset = mm_to_pt(bleed_mm if trim_inset_mm is None else trim_inset_mm)
    for page in pdf.pages:
        crop = [float(v) for v in (page.obj.get("/CropBox") or page.obj.get("/MediaBox"))]
        page.obj["/BleedBox"] = pikepdf.Array(crop)
        page.obj["/TrimBox"] = pikepdf.Array([crop[0] + inset, crop[1] + inset, crop[2] - inset, crop[3] - inset])
    return len(pdf.pages)


def set_overprint(pdf, tech_norms: set[str], black_k: bool) -> int:
    """Inserta `gs` de sobreimpresión al pintar con tintas técnicas (o negro 100 % K) y lo quita al cambiar de color."""
    count = [0]
    done = set()
    OP = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1)
    NO = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, OP=False, op=False)

    def ensure_res(res_owner):
        res = res_owner.get("/Resources")
        if res is None:
            res_owner["/Resources"] = res = pikepdf.Dictionary()
        egs = res.get("/ExtGState")
        if egs is None:
            res["/ExtGState"] = egs = pikepdf.Dictionary()
        egs["/FVop"] = OP
        egs["/FVno"] = NO
        return res

    def is_tech(res, name_obj):
        try:
            cso = res["/ColorSpace"][name_obj]
        except Exception:
            return False
        return isinstance(cso, pikepdf.Array) and str(cso[0]) == "/Separation" and inkmod.normalize_name(_name(cso[1])) in tech_norms

    def process(stream, owner):
        res = ensure_res(owner)
        try:
            ops = pikepdf.parse_content_stream(stream)
        except Exception:
            return
        out, stack = [], []
        st = {"tech": {"cs": False, "CS": False}, "over": False}
        changed = False

        def set_over(want):
            nonlocal changed
            if want != st["over"]:
                out.append(pikepdf.ContentStreamInstruction([pikepdf.Name("/FVop" if want else "/FVno")], pikepdf.Operator("gs")))
                st["over"] = want
                changed = True
                count[0] += 1 if want else 0

        for operands, op in ops:
            o = str(op)
            if o == "q":
                stack.append((dict(st["tech"]), st["over"]))
            elif o == "Q" and stack:
                t, ov = stack.pop()
                st["tech"], st["over"] = t, ov
            out.append(pikepdf.ContentStreamInstruction(operands, op))
            if o in ("cs", "CS"):
                st["tech"][o] = is_tech(res, operands[0])
                set_over(st["tech"][o])
            elif o in ("scn", "sc", "SCN", "SC"):
                set_over(st["tech"]["cs" if o.islower() else "CS"])
            elif o in ("g", "rg", "G", "RG"):
                st["tech"]["cs" if o.islower() else "CS"] = False
                set_over(False)
            elif o in ("k", "K"):
                st["tech"]["cs" if o == "k" else "CS"] = False
                vals = [float(v) for v in operands]
                set_over(bool(black_k and vals[:3] == [0.0, 0.0, 0.0] and vals[3] == 1.0))
            elif o == "Do":
                xo = (res.get("/XObject") or {}).get(operands[0])
                if xo is not None and str(xo.get("/Subtype")) == "/Form" and xo.objgen not in done:
                    done.add(xo.objgen)
                    process(xo, xo)
        if changed:
            stream.write(pikepdf.unparse_content_stream(out))

    for page in pdf.pages:
        contents = page.obj.get("/Contents")
        if contents is None:
            continue
        data = b"\n".join(s.read_bytes() for s in (contents if isinstance(contents, pikepdf.Array) else [contents]))
        page.obj["/Contents"] = pdf.make_stream(data)
        process(page.obj["/Contents"], page.obj)
    return count[0]


def visual_similarity(a, b, dpi: int = 72) -> float:
    """SSIM medio (0–1) entre los renders de ambos PDF; 1 = idénticos."""
    from skimage.metrics import structural_similarity
    da, db = pymupdf.open(str(a)), pymupdf.open(str(b))
    try:
        vals = []
        for i in range(min(len(da), len(db), 5)):
            pa = da[i].get_pixmap(dpi=dpi, alpha=False)
            pb = db[i].get_pixmap(dpi=dpi, alpha=False)
            xa = np.frombuffer(pa.samples, np.uint8).reshape(pa.height, pa.width, 3)
            xb = np.frombuffer(pb.samples, np.uint8).reshape(pb.height, pb.width, 3)
            if xa.shape != xb.shape:
                return 0.0
            vals.append(structural_similarity(xa, xb, channel_axis=2, data_range=255))
        return float(np.mean(vals)) if vals else 1.0
    finally:
        da.close()
        db.close()


def apply_fixes(src, dst, fixes: dict, profile: str | dict = "offset_hoja") -> dict:
    """Aplica las correcciones pedidas a la copia `dst` y devuelve qué se hizo, el preflight antes/después y la similitud visual."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise UserError("No se puede sobrescribir el PDF original.")
    unknown = set(fixes) - set(AVAILABLE)
    if unknown:
        raise UserError("Corrección desconocida: " + ", ".join(sorted(unknown)))
    before = run_preflight(src, profile)
    done = {}
    inv = read_inventory(src)
    try:
        pdf = pikepdf.open(str(src))
    except Exception:
        raise UserError("El PDF está dañado o no se puede abrir.")
    with pdf:
        if fixes.get("eliminar_anotaciones"):
            done["anotaciones_eliminadas"] = remove_annotations(pdf)
        if fixes.get("cajas"):
            mm = float(fixes["cajas"] if not isinstance(fixes["cajas"], dict) else fixes["cajas"].get("sangrado_mm", 3))
            done["paginas_con_cajas"] = set_boxes(pdf, mm)
        if fixes.get("sobreimpresion_tecnicas"):
            tech = {i.norm for i in inv.inks if i.kind in ("technical", "varnish")}
            done["objetos_sobreimpresion"] = set_overprint(pdf, tech, True)
        if fixes.get("unir_duplicadas"):
            m = {v: i.name for i in inv.inks if len(i.variants) > 1 for v in i.variants if v != i.name}
            if m:
                done["tintas_renombradas"] = pdf_edit.rename_inks(pdf, m)
        pdf.save(str(dst))
    after = run_preflight(dst, profile)
    return {"hecho": done, "antes": before["resumen"], "despues": after["resumen"],
            "similitud_visual": round(visual_similarity(src, dst), 4), "hallazgos_despues": after["hallazgos"]}
