"""Métricas del banco de pruebas: emparejar detectado vs esperado, precisión/recall/F1 y CER."""
import re
from collections import defaultdict

import numpy as np
from rapidfuzz.distance import Levenshtein
from scipy.optimize import linear_sum_assignment

CATEGORIES = ["text", "spelling", "color", "visual", "font"]
GROUP = {"visual": "cv", "color": "cv"}  # color y elemento visual se pueden confundir entre sí


def iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = min(ax + aw, bx + bw) - max(ax, bx)
    ih = min(ay + ah, by + bh) - max(ay, by)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    return inter / (aw * ah + bw * bh - inter)


def _center_in(inner, outer) -> bool:
    cx, cy = inner[0] + inner[2] / 2, inner[1] + inner[3] / 2
    return outer[0] <= cx <= outer[0] + outer[2] and outer[1] <= cy <= outer[1] + outer[3]


def compatible(cat_a: str, cat_b: str) -> bool:
    return cat_a == cat_b or (GROUP.get(cat_a) and GROUP.get(cat_a) == GROUP.get(cat_b))


def is_match(det, exp, min_iou=0.3) -> bool:
    if not compatible(det["category"], exp["categoria"]):
        return False
    d, e = det["bbox"], exp["bbox"]
    return iou(d, e) >= min_iou or _center_in(e, d) or _center_in(d, e)


def match(detected: list[dict], expected: list[dict]):
    """Devuelve (pares[(i_det, j_esp)], fp[i_det], fn[j_esp]) con emparejamiento óptimo por IoU."""
    if not detected or not expected:
        return [], list(range(len(detected))), list(range(len(expected)))
    score = np.zeros((len(detected), len(expected)))
    for i, d in enumerate(detected):
        for j, e in enumerate(expected):
            if is_match(d, e):
                score[i, j] = 1.0 + iou(d["bbox"], e["bbox"])
    rows, cols = linear_sum_assignment(-score)
    pairs = [(int(i), int(j)) for i, j in zip(rows, cols) if score[i, j] > 0]
    used_d, used_e = {i for i, _ in pairs}, {j for _, j in pairs}
    fp = [i for i in range(len(detected)) if i not in used_d]
    fn = [j for j in range(len(expected)) if j not in used_e]
    return pairs, fp, fn


def case_counts(detected: list[dict], expected: list[dict]) -> dict:
    """TP/FN se cuentan por categoría del error esperado; FP por categoría de lo detectado."""
    pairs, fp, fn = match(detected, expected)
    c = {k: {"tp": 0, "fp": 0, "fn": 0} for k in CATEGORIES}
    for _, j in pairs:
        c[expected[j]["categoria"]]["tp"] += 1
    for i in fp:
        c[detected[i]["category"]]["fp"] += 1
    for j in fn:
        c[expected[j]["categoria"]]["fn"] += 1
    return {"counts": c, "pairs": pairs, "fp": fp, "fn": fn}


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p * 100, 1), "recall": round(r * 100, 1),
            "f1": round(f * 100, 1)}


def aggregate(case_results: list[dict]) -> dict:
    tot = {k: {"tp": 0, "fp": 0, "fn": 0} for k in CATEGORIES}
    for cr in case_results:
        for k in CATEGORIES:
            for m in ("tp", "fp", "fn"):
                tot[k][m] += cr["counts"][k][m]
    out = {k: prf(**v) for k, v in tot.items()}
    cv = {m: tot["color"][m] + tot["visual"][m] for m in ("tp", "fp", "fn")}
    out["color_visual"] = prf(**cv)
    allc = {m: sum(tot[k][m] for k in CATEGORIES) for m in ("tp", "fp", "fn")}
    out["todas"] = prf(**allc)
    return out


def _norm_text(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = _norm_text(reference), _norm_text(hypothesis)
    if not ref:
        return 0.0
    return min(1.0, Levenshtein.distance(ref, hyp) / len(ref))


def global_stats(case_results: list[dict]) -> dict:
    n = max(1, len(case_results))
    fp_total = sum(sum(v["fp"] for v in cr["counts"].values()) for cr in case_results)
    clean = [cr for cr in case_results if cr["n_expected"] == 0]
    cers = [cr["cer"] for cr in case_results if cr.get("cer") is not None]
    stage = defaultdict(list)
    for cr in case_results:
        for k, v in (cr.get("timings") or {}).items():
            stage[k].append(v)
    return {
        "casos": len(case_results),
        "fp_por_caso": round(fp_total / n, 2),
        "identicos": len(clean),
        "identicos_aprobados_pct": round(100 * sum(1 for c in clean if c["status"] == "aprobado") / len(clean), 1)
        if clean else None,
        "cer_pct": round(100 * float(np.mean(cers)), 2) if cers else None,
        "tiempo_medio_s": round(float(np.mean([cr["elapsed_s"] for cr in case_results])), 2) if case_results else 0,
        "tiempo_max_s": round(max([cr["elapsed_s"] for cr in case_results] or [0]), 2),
        "etapas_s": {k: round(float(np.mean(v)), 2) for k, v in stage.items()},
    }
