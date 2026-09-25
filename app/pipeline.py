"""Orquesta toda la comparación: carga, alineación, visual, texto, ortografía, color, fuentes."""
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import history, ignore_zones
from .align import align_images
from .compare_color import grid_color_diffs, text_color_diffs
from .compare_text import (OcrUnavailable, Word, _missing_diff, compare_words, layout_words, ocr_words)
from .compare_visual import compare_visual, make_outputs, save_jpg
from .config import CFG, RESULTS_DIR, load_config
from .fonts import compare_fonts, fonts_in_design
from .learning import confusions, store as learning_store, tuning, vocab
from .learning.imagetype import classify as classify_image
from .photometry import normalize_illumination
from .ocr_guided import compare_guided, ocr_page_adaptive, read_region
from .loaders import color_space, extract_pdf_layout, load_as_image, page_count, validate_file
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
        # región sobre texto, en la misma línea que un error de texto/fuente: la explican (p. ej. las palabras
        # que se corren al quitar una)
        if tregion.size and tregion.mean() >= 0.4 and any(
                min(y + h, o.bbox[1] + o.bbox[3]) - max(y, o.bbox[1]) >= 0.5 * min(h, o.bbox[3])
                for o in others):
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


STAGES = [("cargar", "Cargando archivos…", 0.05), ("alinear", "Alineando las imágenes…", 0.15),
          ("visual", "Comparando visualmente…", 0.30), ("ocr", "Leyendo el texto (OCR)…", 0.75),
          ("ortografia", "Revisando la ortografía…", 0.80), ("color", "Comparando colores…", 0.88),
          ("fuentes", "Analizando fuentes…", 0.93), ("cierre", "Generando resultados…", 0.99)]


class _Timer:
    def __init__(self, progress=None):
        self.t = {}
        self._last = time.time()
        self._cb = progress
        if progress:
            progress(*STAGES[0][:1], 0.0, STAGES[0][1])

    def mark(self, name: str):
        now = time.time()
        self.t[name] = round(self.t.get(name, 0.0) + now - self._last, 2)
        self._last = now
        if self._cb:
            keys = [k for k, _, _ in STAGES]
            if name in keys:
                i = keys.index(name)
                nxt = STAGES[min(i + 1, len(STAGES) - 1)]
                self._cb(nxt[0], STAGES[i][2], nxt[1])


def _resolve_zones(params: dict | None) -> tuple[list[dict], str | None]:
    """Zonas de la plantilla indicada + zonas dibujadas a mano (coordenadas relativas 0–1)."""
    zones, template = [], None
    p = params or {}
    if p.get("template"):
        t = ignore_zones.load_template(p["template"])
        if t:
            zones += t["zonas"]
            template = t["nombre"]
    zones += [ignore_zones.normalize_zone(z) for z in (p.get("zones") or [])]
    return zones, template


def run_comparison(job_id: str, client_path, design_path, params: dict | None = None,
                   client_page: int = 0, design_page: int = 0,
                   client_name: str = "", design_name: str = "",
                   persist: bool = True, out_dir: Path | None = None, progress=None) -> Result:
    t0 = time.time()
    tm = _Timer(progress)
    cfg = load_config()
    used = {}
    if (params or {}).get("manual_points"):
        used["manual_points"] = params["manual_points"]
    cfg.update((params or {}).get("overrides") or {})
    for k in TUNABLE:
        if params and params.get(k) is not None:
            cfg[k] = float(params[k])
        used[k] = cfg[k]
    dpi = float(cfg["render_dpi"])
    warnings: list[str] = []
    notes_flags: list[str] = []

    validate_file(client_path, cfg["max_upload_mb"])
    validate_file(design_path, cfg["max_upload_mb"])

    design = load_as_image(design_path, dpi, design_page)
    client_raw = load_as_image(client_path, dpi, client_page)
    spans = extract_pdf_layout(design_path, dpi, design_page)

    tm.mark("cargar")
    manual = (params or {}).get("manual_points")
    al = align_images(design, client_raw, manual)
    client = al.aligned_client
    if al.warning:
        warnings.append(al.warning)
    H, W = design.shape[:2]

    # ---- visual
    valid = al.valid_mask
    client, normalized = normalize_illumination(design, client, valid)
    if normalized:
        notes_flags.append("iluminación corregida")
    tm.mark("alinear")
    # zonas a ignorar (Fase 8.1): en la comparación visual y de color esas zonas se igualan al diseño
    zones, template = _resolve_zones(params)
    if zones:
        used["zones"] = zones
        if template:
            used["template"] = template
    client_full = client
    client_v = client
    if zones:
        m_all = ignore_zones.zone_mask(zones, W, H, ("todo",))
        client_v = client.copy()
        client_v[m_all] = design[m_all]
    vis = compare_visual(design, client_v, cfg, valid)
    tm.mark("visual")

    # ---- texto
    text_diffs: list[Difference] = []
    pairs, client_words, design_words = [], [], []
    matched = total = 0
    matched_keys: set[str] = set()
    text_ok = True
    quality = al.alignment_quality if al.aligned else 0.0
    # tipo de arte y aprendizaje (Fase 7): vocabulario, ajustes por tipo
    learn_on = bool(cfg.get("learning_enabled", True))
    perspective = False
    if al.homography is not None:
        Hh = al.homography
        perspective = abs(Hh[2, 0]) * W > 0.02 or abs(Hh[2, 1]) * H > 0.02 or abs(Hh[1, 0]) > 0.026
    image_type = classify_image(client_path, framed=any("marco" in n for n in al.notes),
                                illumination_fixed=normalized, perspective=perspective)
    tune = tuning.params_for(image_type) if learn_on else None
    extra = vocab.ocr_extra_config() if learn_on else ""
    try:
        if spans and cfg.get("ocr_mode", "guiado") == "guiado":
            tr = compare_guided(spans, client, cfg, quality, extra, tune)
        else:
            if spans:
                design_words = layout_words(spans)
            else:
                warnings.append("El diseño no contiene texto vectorial (¿texto convertido a curvas o "
                                "imagen?). Se usó OCR también sobre el diseño; la precisión es menor.")
                design_words = ocr_page_adaptive(design, cfg)
            client_words = (ocr_words(client, cfg) if spans else ocr_page_adaptive(client, cfg))
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

    # confusiones aprendidas: si la diferencia se explica SOLO con ellas (y no es dígito↔dígito) no es un error real
    if learn_on and text_ok:
        min_c = int(cfg.get("learning_min_confusion_count", 3))
        for d in text_diffs:
            if d.subtype == "cambiada" and confusions.explains(d.expected or "", d.found or "", min_c):
                d.subtype, d.severity = "ocr_dudoso", "baja"
                d.message = f"Posible error de lectura del OCR: leyó «{d.expected}», el diseño dice «{d.found}»"
                matched += 1
    # una tilde que falta en el diseño (el cliente la tiene) también es un error de ortografía
    from .ocr_guided import is_tilde_missing
    tilde_diffs: list[Difference] = []
    for d in list(text_diffs):
        if is_tilde_missing(d):
            tilde_diffs.append(Difference(
                category="spelling", subtype="tilde_faltante", bbox=d.bbox, severity="alta",
                message=f"Falta la tilde: «{d.found}» → «{d.expected}»", found=d.found, suggestions=[d.expected]))
    # regiones visuales sobre papel en blanco del diseño que en realidad son texto del cliente que falta
    if text_ok and spans:
        dboxes = np.zeros((H, W), np.uint8)
        for w_ in design_words:
            x0_, y0_, x1_, y1_ = (int(v) for v in w_.bbox)
            dboxes[max(0, y0_):y1_, max(0, x0_):x1_] = 1
        for v in list(vis.differences):
            if v.subtype not in ("elemento_faltante", "elemento_cambiado"):
                continue
            x, y, w, h = v.bbox
            if dboxes[max(0, y - 10):y + h + 10, max(0, x - 10):x + w + 10].any():  # hay texto del diseño ahí
                continue
            if any(_intersects(v.bbox, t.bbox) for t in text_diffs):  # ya explicado por un error de texto
                continue
            found = read_region(client, v.bbox, cfg)
            if found:
                vis.differences.remove(v)
                for wd in found:
                    text_diffs.append(_missing_diff(wd))
                    client_words.append(wd)
    # una misma palabra del cliente hallada por dos caminos cuenta una sola vez
    uniq: list[Difference] = []
    for d in text_diffs:
        if d.subtype == "faltante" and any(u.subtype == "faltante" and _intersects(u.bbox, d.bbox) for u in uniq):
            continue
        uniq.append(d)
    text_diffs = uniq
    tm.mark("ocr")
    # ---- ortografía
    spell_diffs, spell_total = [], 0
    if text_ok:
        spell_diffs, spell_total = check_spelling(design_words, matched_keys)
        spell_diffs = tilde_diffs + [d for d in spell_diffs
                                     if not any(_intersects(d.bbox, t.bbox) for t in tilde_diffs)]

    tm.mark("ortografia")
    # ---- color
    text_boxes = [(int(w.bbox[0]), int(w.bbox[1]), int(w.bbox[2] - w.bbox[0]),
                   int(w.bbox[3] - w.bbox[1])) for w in design_words + client_words]
    tol = float(cfg["delta_e_tolerance"])
    color_diffs = []
    if spans and text_ok:
        color_diffs += text_color_diffs(design, client, spans, tol,
                                        [d.bbox for d in text_diffs + spell_diffs])
    client_c = client
    if zones:
        m_col = ignore_zones.zone_mask(zones, W, H, ("todo", "color"))
        client_c = client.copy()
        client_c[m_col] = design[m_col]
    zone_diffs, _ = grid_color_diffs(design, client_c, text_boxes, tol, valid)
    color_diffs += zone_diffs

    tm.mark("color")
    # ---- fuentes
    font_diffs, font_total = [], 0
    if spans and text_ok:
        font_diffs, font_total = compare_fonts(design, client, spans, pairs,
                                               float(cfg["font_size_tolerance_pct"]))

    tm.mark("fuentes")
    # ---- limpieza de duplicados
    visual_diffs, color_diffs = _dedupe(vis.differences, text_diffs + spell_diffs + font_diffs,
                                        color_diffs, (H, W), text_boxes)

    diffs = visual_diffs + text_diffs + spell_diffs + color_diffs + font_diffs
    diffs.sort(key=lambda d: (d.bbox[1], d.bbox[0]))
    for i, d in enumerate(diffs, 1):
        d.id = i

    # diferencias dentro de zonas ignoradas: quedan marcadas y NO cuentan en los porcentajes
    if zones:
        for d in diffs:
            d.ignored_by_zone = ignore_zones.affected(d, zones, W, H)
    ign = {id(d) for d in diffs if d.ignored_by_zone}
    matched += sum(1 for d in text_diffs if id(d) in ign)
    spell_kept = [d for d in spell_diffs if id(d) not in ign]
    font_kept = [d for d in font_diffs if id(d) not in ign]
    color_kept = [d for d in color_diffs if id(d) not in ign]
    color_area = sum(d.bbox[2] * d.bbox[3] for d in color_kept)
    scores, status = compute_scores(
        vis.score, matched, total, color_area, W * H,
        len(spell_kept), spell_total, len(font_kept), font_total, cfg["weights"])

    out_dir = out_dir or (RESULTS_DIR / job_id)
    images = make_outputs(design, client_full, vis.diff_strength, out_dir)
    save_jpg(out_dir / "client_original.jpg", client_raw)  # para la alineación manual
    images["client_original"] = "client_original.jpg"
    cs = {"design": color_space(design_path, design_page), "client": color_space(client_path, client_page)}
    if cs["client"].startswith("CMYK (sin perfil"):
        warnings.append("El arte del cliente está en CMYK sin perfil de color: la conversión a pantalla es "
                        "aproximada y los colores pueden variar.")

    counts: dict[str, int] = {}
    for d in diffs:
        if not d.ignored_by_zone:
            counts[d.category] = counts.get(d.category, 0) + 1

    result = Result(
        job_id=job_id, width=W, height=H, aligned=al.aligned,
        alignment_quality=round(al.alignment_quality, 3), alignment_method=al.method, scores=scores, status=status,
        differences=diffs, fonts_in_design=fonts_in_design(spans), images=images,
        warnings=warnings, client_name=client_name or Path(client_path).name,
        design_name=design_name or Path(design_path).name,
        created=datetime.now().isoformat(timespec="seconds"), counts=counts, params=used,
        pages={"client": client_page + 1, "design": design_page + 1,
               "client_total": page_count(client_path), "design_total": page_count(design_path)},
        elapsed_s=round(time.time() - t0, 1), timings=tm.t,
        color_spaces=cs, image_type=image_type, template=template,
        learning_version=learning_store.fingerprint() if learn_on else None,
        client_text=" ".join(w.text for w in client_words) if text_ok else None)
    if not persist:
        return result
    (out_dir / "result.json").write_text(result.model_dump_json(indent=1), encoding="utf-8")
    history.add_entry({"job_id": job_id, "created": result.created,
                       "client_name": result.client_name, "design_name": result.design_name,
                       "total": scores["total"], "status": status})
    return result
