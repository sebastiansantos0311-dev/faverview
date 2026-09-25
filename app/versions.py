"""Fase 8.3 – comparar dos versiones de MI diseño (v1 vs v2) y verificar correcciones.

Ambos son PDF vectoriales: el texto se compara exacto (sin OCR), más fuentes, colores de los spans y el render visual."""
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import history
from .align import _resize_to
from .compare_color import delta_e_hex, grid_color_diffs
from .compare_text import Word, compare_words, layout_words
from .compare_visual import compare_visual, make_outputs, save_jpg
from .config import RESULTS_DIR, load_config
from .fonts import fonts_in_design
from .loaders import extract_pdf_layout, load_as_image, page_count, validate_file
from .models import Difference, Result
from .pipeline import STAGES, _dedupe, _intersects
from .scoring import compute_scores
from .spelling import check_spelling


def _v(text: str) -> str:
    return (text.replace("Cliente dice", "v1 dice").replace("Tu diseño dice", "v2 dice")
            .replace("Palabra faltante en tu diseño", "Palabra que falta en v2")
            .replace("Palabra sobrante en tu diseño", "Palabra nueva en v2")
            .replace("en tu diseño pero ausente en el arte del cliente", "en v2 pero no en v1")
            .replace("del cliente que falta en tu diseño", "de v1 que falta en v2"))


def _norm_font(name: str) -> str:
    return name.split("+")[-1].lower()


def compare_spans(spans1, spans2, tol_pct: float, de_tol: float) -> tuple[list[Difference], list[Difference], int]:
    """Empareja spans con el mismo texto (el más cercano) y compara fuente, tamaño, estilo y color."""
    font_d, color_d, evaluated = [], [], 0
    used: set[int] = set()
    for sp2 in spans2:
        best, bd = None, 1e18
        for i, sp1 in enumerate(spans1):
            if i in used or sp1.text != sp2.text:
                continue
            d = (sp1.bbox[0] - sp2.bbox[0]) ** 2 + (sp1.bbox[1] - sp2.bbox[1]) ** 2
            if d < bd:
                best, bd = i, d
        if best is None:
            continue
        used.add(best)
        sp1 = spans1[best]
        evaluated += 1
        x0, y0, x1, y1 = sp2.bbox
        bbox = (int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0)))
        det = []
        if abs(sp2.size - sp1.size) > max(0.3, sp1.size * tol_pct / 100):
            det.append(f"tamaño {sp1.size:.0f}pt → {sp2.size:.0f}pt")
        if _norm_font(sp1.font) != _norm_font(sp2.font):
            det.append(f"fuente {_norm_font(sp1.font)} → {_norm_font(sp2.font)}")
        if sp1.bold != sp2.bold or sp1.italic != sp2.italic:
            det.append("estilo (negrita/cursiva) distinto")
        if det:
            font_d.append(Difference(category="font", subtype="version", bbox=bbox, severity="media",
                                     message="Fuente distinta entre versiones: " + "; ".join(det),
                                     expected=sp1.text[:60], found=sp2.text[:60]))
        if sp1.color != sp2.color:
            de = delta_e_hex(sp1.color, sp2.color)
            if de > de_tol:
                color_d.append(Difference(
                    category="color", subtype="texto", bbox=bbox, severity="alta" if de > 3 * de_tol else "media",
                    message=f"Color de texto distinto entre versiones (ΔE {de:.1f}): «{sp2.text[:40]}»",
                    expected_hex=sp1.color, found_hex=sp2.color, delta_e=round(de, 1)))
    return font_d, color_d, evaluated


def run_versions(job_id: str, v1_path, v2_path, params: dict | None = None, page1: int = 0, page2: int = 0,
                 name1: str = "", name2: str = "", persist: bool = True, out_dir: Path | None = None,
                 progress=None) -> Result:
    t0 = time.time()
    cfg = load_config()
    for k in ("ssim_threshold", "delta_e_tolerance", "min_region_area"):
        if params and params.get(k) is not None:
            cfg[k] = float(params[k])
    dpi = float(cfg["render_dpi"])
    prog = progress or (lambda *a: None)
    warnings: list[str] = []
    validate_file(v1_path, cfg["max_upload_mb"])
    validate_file(v2_path, cfg["max_upload_mb"])

    prog("cargar", 0.05, "Cargando las dos versiones…")
    v2 = load_as_image(v2_path, dpi, page2)
    v1 = load_as_image(v1_path, dpi, page1)
    s1 = extract_pdf_layout(v1_path, dpi, page1)
    s2 = extract_pdf_layout(v2_path, dpi, page2)
    H, W = v2.shape[:2]
    if v1.shape[:2] != v2.shape[:2]:
        warnings.append("Las dos versiones tienen distinto tamaño de página; se ajustó v1 al tamaño de v2.")
        v1 = _resize_to(v1, W, H)

    prog("visual", 0.3, "Comparando el render…")
    vis = compare_visual(v2, v1, cfg)
    prog("ocr", 0.6, "Comparando el texto exacto…")
    text_diffs, matched, total, design_words = [], 0, 0, []
    if s1 and s2:
        tr = compare_words(layout_words(s2), layout_words(s1))
        text_diffs, matched, total, design_words = tr.differences, tr.matched, tr.total, tr.design_words
        for d in text_diffs:
            d.message = _v(d.message)
    else:
        warnings.append("Alguna de las versiones no tiene texto vectorial (texto convertido a curvas): "
                        "solo se comparó el render.")
    spell_diffs, spell_total = check_spelling(design_words) if design_words else ([], 0)
    prog("fuentes", 0.85, "Comparando fuentes y colores…")
    font_diffs, color_diffs, font_total = compare_spans(s1, s2, float(cfg["font_size_tolerance_pct"]),
                                                        float(cfg["delta_e_tolerance"]))
    boxes = [(int(w.bbox[0]), int(w.bbox[1]), int(w.bbox[2] - w.bbox[0]), int(w.bbox[3] - w.bbox[1]))
             for w in design_words + layout_words(s1)]
    zone_d, _ = grid_color_diffs(v2, v1, boxes, float(cfg["delta_e_tolerance"]))
    color_diffs += zone_d
    visual_diffs, color_diffs = _dedupe(vis.differences, text_diffs + spell_diffs + font_diffs, color_diffs, (H, W), boxes)
    for d in visual_diffs:
        d.message = _v(d.message)

    diffs = visual_diffs + text_diffs + spell_diffs + color_diffs + font_diffs
    diffs.sort(key=lambda d: (d.bbox[1], d.bbox[0]))
    for i, d in enumerate(diffs, 1):
        d.id = i
    color_area = sum(d.bbox[2] * d.bbox[3] for d in color_diffs)
    scores, status = compute_scores(vis.score, matched, total, color_area, W * H, len(spell_diffs), spell_total,
                                    len(font_diffs), font_total, cfg["weights"])

    out_dir = out_dir or (RESULTS_DIR / job_id)
    images = make_outputs(v2, v1, vis.diff_strength, out_dir)
    save_jpg(out_dir / "client_original.jpg", v1)
    images["client_original"] = "client_original.jpg"
    counts: dict[str, int] = {}
    for d in diffs:
        counts[d.category] = counts.get(d.category, 0) + 1
    result = Result(
        job_id=job_id, width=W, height=H, aligned=True, alignment_quality=1.0, alignment_method="mismo tamaño",
        scores=scores, status=status, differences=diffs, fonts_in_design=fonts_in_design(s2), images=images,
        warnings=warnings, client_name=name1 or Path(v1_path).name, design_name=name2 or Path(v2_path).name,
        created=datetime.now().isoformat(timespec="seconds"), counts=counts, params={"modo": "versiones"},
        pages={"client": page1 + 1, "design": page2 + 1, "client_total": page_count(v1_path),
               "design_total": page_count(v2_path)},
        elapsed_s=round(time.time() - t0, 1), mode="versiones")
    if persist:
        (out_dir / "result.json").write_text(result.model_dump_json(indent=1), encoding="utf-8")
        history.add_entry({"job_id": job_id, "created": result.created, "client_name": "v1: " + result.client_name,
                           "design_name": "v2: " + result.design_name, "total": scores["total"], "status": status})
    prog("cierre", 1.0, "Listo")
    return result


# ---------------------------------------------------------------------------------- verificar correcciones
def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = min(ax + aw, bx + bw) - max(ax, bx)
    ih = min(ay + ah, by + bh) - max(ay, by)
    if iw <= 0 or ih <= 0:
        return 0.0
    return iw * ih / (aw * ah + bw * bh - iw * ih)


def _center_in(inner, outer) -> bool:
    cx, cy = inner[0] + inner[2] / 2, inner[1] + inner[3] / 2
    return outer[0] <= cx <= outer[0] + outer[2] and outer[1] <= cy <= outer[1] + outer[3]


def _compat(c1: str, c2: str) -> bool:
    return c1 == c2 or {c1, c2} <= {"color", "visual"}


def verify_corrections(prev: Result, new: Result) -> dict:
    """Compara los errores de la revisión anterior con los de la nueva: ✔ corregidos, ✘ persisten, nuevos."""
    prev_d = [d for d in prev.differences if not d.ignored_by_zone and d.status != "no_aplica" and d.review != "falso_positivo"]
    new_d = [d for d in new.differences if not d.ignored_by_zone]
    used: set[int] = set()
    corregidos, persisten = [], []
    for p in prev_d:
        hit = None
        for n in new_d:
            if n.id in used or not _compat(p.category, n.category):
                continue
            if _iou(p.bbox, n.bbox) >= 0.3 or _center_in(p.bbox, n.bbox) or _center_in(n.bbox, p.bbox):
                hit = n
                break
        row = {"id": p.id, "category": p.category, "message": p.message[:140], "bbox": list(p.bbox)}
        if hit is None:
            corregidos.append(row)
        else:
            used.add(hit.id)
            row["nuevo_id"] = hit.id
            persisten.append(row)
            hit.status, hit.comment = p.status, p.comment  # conserva el estado del checklist
    nuevos = [n.id for n in new_d if n.id not in used]
    return {"job_anterior": prev.job_id, "corregidos": corregidos, "persisten": persisten, "nuevos": nuevos,
            "resumen": f"{len(corregidos)} corregidos · {len(persisten)} siguen · {len(nuevos)} nuevos"}
