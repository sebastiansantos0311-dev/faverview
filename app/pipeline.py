"""Orquesta toda la comparación: carga, alineación, visual, texto, ortografía, color, fuentes."""
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import history
from .align import align_images
from .compare_color import grid_color_diffs, text_color_diffs
from .compare_text import (OcrUnavailable, Word, compare_words, layout_words, ocr_words)
from .compare_visual import compare_visual, make_outputs
from .config import CFG, RESULTS_DIR, load_config
from .fonts import compare_fonts, fonts_in_design
from .loaders import extract_pdf_layout, load_as_image, page_count, validate_file
from .models import Difference, Result
from .scoring import compute_scores
from .spelling import check_spelling

TUNABLE = ("ssim_threshold", "delta_e_tolerance", "min_region_area")


def _box_mask(shape, diffs) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    for d in diffs:
        x, y, w, h = d.bbox
        m[max(0, y):y + h, max(0, x):x + w] = 1
    return m


def _intersects(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ah, by + bh) > max(ay, by)


def _dedupe(visual: list[Difference], others: list[Difference], colors: list[Difference],
            shape, text_boxes=()) -> tuple[list[Difference], list[Difference]]:
    """Quita regiones visuales ya explicadas por texto/fuente/color y colores que son en realidad
    un elemento visual faltante. Devuelve (visual, colores)."""
    mask = _box_mask(shape, others)
    tmask = np.zeros(shape, np.uint8)
    for bx, by, bw, bh in text_boxes:
        tmask[max(0, by):by + bh, max(0, bx):bx + bw] = 1
    zone_colors = [c for c in colors if c.subtype == "zona"]
    kept_v = []
    for v in visual:
        x, y, w, h = v.bbox
        region = mask[y:y + h, x:x + w]
        if region.size and region.mean() >= 0.4:
            continue
        tregion = tmask[y:y + h, x:x + w]
        if tregion.size and tregion.mean() >= 0.6:
            if v.subtype == "diferencia_visual" or any(_intersects(v.bbox, o.bbox) for o in others):
                continue
        if v.subtype in ("diferencia_visual", "color_distinto") and any(
                _intersects(v.bbox, c.bbox) for c in zone_colors):
            continue
        if v.subtype == "color_distinto" and any(_intersects(v.bbox, c.bbox) for c in colors):
            continue
        kept_v.append(v)
    element_boxes = [v.bbox for v in kept_v
                     if v.subtype in ("elemento_sobrante", "elemento_faltante", "elemento_cambiado")]
    kept_c = []
    for c in colors:
        if c.subtype == "zona":
            x, y, w, h = c.bbox
            area = max(1, w * h)
            covered = 0
            for bx, by, bw, bh in element_boxes:
                iw = min(x + w, bx + bw) - max(x, bx)
                ih = min(y + h, by + bh) - max(y, by)
                if iw > 0 and ih > 0:
                    covered = max(covered, iw * ih / area)
            if covered >= 0.5:
                continue
        kept_c.append(c)
    return kept_v, kept_c


def run_comparison(job_id: str, client_path, design_path, params: dict | None = None,
                   client_page: int = 0, design_page: int = 0,
                   client_name: str = "", design_name: str = "") -> Result:
    t0 = time.time()
    cfg = load_config()
    used = {}
    for k in TUNABLE:
        if params and params.get(k) is not None:
            cfg[k] = float(params[k])
        used[k] = cfg[k]
    dpi = float(cfg["render_dpi"])
    warnings: list[str] = []

    validate_file(client_path, cfg["max_upload_mb"])
    validate_file(design_path, cfg["max_upload_mb"])

    design = load_as_image(design_path, dpi, design_page)
    client_raw = load_as_image(client_path, dpi, client_page)
    spans = extract_pdf_layout(design_path, dpi, design_page)

    al = align_images(design, client_raw)
    client = al.aligned_client
    if al.warning:
        warnings.append(al.warning)
    H, W = design.shape[:2]

    # ---- visual
    vis = compare_visual(design, client, cfg)

    # ---- texto
    text_diffs: list[Difference] = []
    pairs, client_words, design_words = [], [], []
    matched = total = 0
    matched_keys: set[str] = set()
    text_ok = True
    try:
        if spans:
            design_words = layout_words(spans)
        else:
            warnings.append("El diseño no contiene texto vectorial (¿texto convertido a curvas o "
                            "imagen?). Se usó OCR también sobre el diseño; la precisión es menor.")
            design_words = ocr_words(design, cfg)
        client_words = ocr_words(client, cfg)
        tr = compare_words(design_words, client_words)
        text_diffs, pairs = tr.differences, tr.pairs
        matched, total, matched_keys = tr.matched, tr.total, tr.matched_design_keys
        design_words, client_words = tr.design_words, tr.client_words
    except OcrUnavailable as e:
        text_ok = False
        warnings.append(f"{e} Se omitió la comparación de texto.")
    except Exception as e:  # OCR roto no debe tumbar todo el análisis
        text_ok = False
        warnings.append(f"Falló el OCR ({e}). Se omitió la comparación de texto.")

    # ---- ortografía
    spell_diffs, spell_total = [], 0
    if text_ok:
        spell_diffs, spell_total = check_spelling(design_words, matched_keys)

    # ---- color
    text_boxes = [(int(w.bbox[0]), int(w.bbox[1]), int(w.bbox[2] - w.bbox[0]),
                   int(w.bbox[3] - w.bbox[1])) for w in design_words + client_words]
    tol = float(cfg["delta_e_tolerance"])
    color_diffs = []
    if spans and text_ok:
        color_diffs += text_color_diffs(design, client, spans, tol,
                                        [d.bbox for d in text_diffs + spell_diffs])
    zone_diffs, _ = grid_color_diffs(design, client, text_boxes, tol)
    color_diffs += zone_diffs

    # ---- fuentes
    font_diffs, font_total = [], 0
    if spans and text_ok:
        font_diffs, font_total = compare_fonts(design, client, spans, pairs,
                                               float(cfg["font_size_tolerance_pct"]))

    # ---- limpieza de duplicados
    visual_diffs, color_diffs = _dedupe(vis.differences, text_diffs + spell_diffs + font_diffs,
                                        color_diffs, (H, W), text_boxes)

    diffs = visual_diffs + text_diffs + spell_diffs + color_diffs + font_diffs
    diffs.sort(key=lambda d: (d.bbox[1], d.bbox[0]))
    for i, d in enumerate(diffs, 1):
        d.id = i

    color_area = sum(d.bbox[2] * d.bbox[3] for d in color_diffs)
    scores, status = compute_scores(
        vis.score, matched, total, color_area, W * H,
        len(spell_diffs), spell_total, len(font_diffs), font_total, cfg["weights"])

    out_dir = RESULTS_DIR / job_id
    images = make_outputs(design, client, vis.diff_strength, out_dir)

    counts: dict[str, int] = {}
    for d in diffs:
        counts[d.category] = counts.get(d.category, 0) + 1

    result = Result(
        job_id=job_id, width=W, height=H, aligned=al.aligned,
        alignment_quality=round(al.alignment_quality, 3), scores=scores, status=status,
        differences=diffs, fonts_in_design=fonts_in_design(spans), images=images,
        warnings=warnings, client_name=client_name or Path(client_path).name,
        design_name=design_name or Path(design_path).name,
        created=datetime.now().isoformat(timespec="seconds"), counts=counts, params=used,
        pages={"client": client_page + 1, "design": design_page + 1,
               "client_total": page_count(client_path), "design_total": page_count(design_path)},
        elapsed_s=round(time.time() - t0, 1))
    (out_dir / "result.json").write_text(result.model_dump_json(indent=1), encoding="utf-8")
    history.add_entry({"job_id": job_id, "created": result.created,
                       "client_name": result.client_name, "design_name": result.design_name,
                       "total": scores["total"], "status": status})
    return result
