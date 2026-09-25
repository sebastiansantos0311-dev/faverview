"""Nivel 3 – auto-ajuste del preprocesado del OCR por tipo de imagen.

Las etiquetas salen gratis: en las líneas donde el usuario NO marcó un error de texto, el arte del cliente dice
exactamente lo que dice el PDF del diseño. Se busca (búsqueda por coordenadas sobre una rejilla) la combinación de
parámetros de preprocesado que minimiza el CER en esas líneas, por tipo de imagen."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
from rapidfuzz.distance import Levenshtein

from ..config import DATOS_DIR, load_config, setup_tesseract
from . import store

OPTIONS = {
    "target_px": [40, 50, 60, 80],
    "method": ["sauvola", "otsu"],
    "k": [0.1, 0.2, 0.3],
    "blur": [0.0, 1.0],
    "psm": [7, 13],
    "margin": [0.15, 0.25, 0.4],
}
MIN_LINES = 12  # líneas mínimas por tipo
MIN_CASES = 3  # casos distintos mínimos (la validación se hace con casos que el ajuste NO vio)
MIN_GAIN = 0.05  # se adopta solo si el CER baja al menos 5% (relativo)
_running = threading.Event()


def params_for(tipo: str | None) -> dict | None:
    if not tipo or not store.enabled():
        return None
    ent = store.load_json("ajustes_ocr.json", {}).get(tipo)
    return ent["params"] if ent else None


def _norm(t: str) -> str:
    return " ".join(t.lower().split())


def collect_samples(tipo: str | None, max_per_case: int = 8, max_total: int = 45) -> dict[str, list]:
    """Recortes de líneas 'de verdad conocida' agrupados por tipo de imagen."""
    from ..align import align_images
    from ..loaders import extract_pdf_layout, load_as_image
    from ..ocr_guided import Line, lines_from_layout
    from ..photometry import normalize_illumination

    cfg = load_config()
    dpi = float(cfg["render_dpi"])
    casos = DATOS_DIR / "casos"
    out: dict[str, list] = {}
    if not casos.exists():
        return out
    for cdir in sorted(casos.iterdir()):
        ej = cdir / "esperado.json"
        if not ej.exists():
            continue
        exp = json.loads(ej.read_text(encoding="utf-8"))
        t = exp.get("tipo", "exportado")
        if tipo and t != tipo:
            continue
        if len(out.get(t, [])) >= max_total:
            continue
        try:
            design_p, client_p = cdir / exp["diseno"], cdir / exp["cliente"]
            pd, pc = exp.get("pagina_diseno", 1) - 1, exp.get("pagina_cliente", 1) - 1
            design = load_as_image(design_p, dpi, pd)
            client_raw = load_as_image(client_p, dpi, pc)
            spans = extract_pdf_layout(design_p, dpi, pd)
            al = align_images(design, client_raw)
            client, _ = normalize_illumination(design, al.aligned_client, al.valid_mask)
        except Exception:
            continue
        errs = [e["bbox"] for e in exp.get("errores", []) if e.get("categoria") in ("text", "spelling")]
        lines = lines_from_layout(spans)
        good = []
        for ln in lines:
            x0, y0, x1, y1 = ln.bbox
            if any(min(x1, bx + bw) > max(x0, bx) and min(y1, by + bh) > max(y0, by) for bx, by, bw, bh in errs):
                continue
            good.append(ln)
        rng = np.random.default_rng(len(good))
        if len(good) > max_per_case:
            good = [good[i] for i in rng.choice(len(good), max_per_case, replace=False)]
        H, W = client.shape[:2]
        for ln in good:
            h = max(ln.h, 8.0)
            mx, my = int(0.6 * (ln.bbox[2] - ln.bbox[0])) + 20, int(1.2 * h)
            x0, y0 = max(0, int(ln.bbox[0]) - mx), max(0, int(ln.bbox[1]) - my)
            x1, y1 = min(W, int(ln.bbox[2]) + mx), min(H, int(ln.bbox[3]) + my)
            sub = client[y0:y1, x0:x1].copy()
            rel = Line(ln.spans, [type(w)(w.text, (w.bbox[0] - x0, w.bbox[1] - y0, w.bbox[2] - x0, w.bbox[3] - y0))
                                  for w in ln.words],
                       (ln.bbox[0] - x0, ln.bbox[1] - y0, ln.bbox[2] - x0, ln.bbox[3] - y0))
            out.setdefault(t, []).append((sub, rel, al.alignment_quality, cdir.name))
    return out


def evaluate(params: dict, samples: list, cfg: dict, extra: str = "") -> float:
    """CER medio de leer las líneas con estos parámetros."""
    from ..ocr_guided import read_line

    setup_tesseract(cfg)

    def one(s):
        sub, ln, q = s[:3]
        H, W = sub.shape[:2]
        words, _ = read_line(sub, ln, cfg, q, extra, None, params)
        want = _norm(" ".join(w.text for w in ln.words))
        got = _norm(" ".join(w.text for w in sorted(words, key=lambda w: w.bbox[0])))
        return Levenshtein.distance(want, got) / max(1, len(want))

    with ThreadPoolExecutor(max_workers=4) as ex:
        vals = list(ex.map(one, samples))
    return float(np.mean(vals)) if vals else 1.0


def pipeline_guard(case_names: list[str], params: dict, log=print) -> dict:
    """Comprobación a nivel de TODO el pipeline con los casos de validación: corre la comparación completa con los
    valores de fábrica y con el ajuste candidato. Devuelve errores de texto (FP+FN) y CER de cada uno."""
    import tempfile

    from bench import metrics
    from ..pipeline import run_comparison

    out = {"base": {"err": 0, "cer": []}, "nuevo": {"err": 0, "cer": []}}
    for name in case_names:
        cdir = DATOS_DIR / "casos" / name
        exp = json.loads((cdir / "esperado.json").read_text(encoding="utf-8"))
        for label, tune in (("base", {}), ("nuevo", params)):
            res = run_comparison(f"guard_{name}", cdir / exp["cliente"], cdir / exp["diseno"], {"tune": tune},
                                 exp.get("pagina_cliente", 1) - 1, exp.get("pagina_diseno", 1) - 1, persist=False,
                                 out_dir=Path(tempfile.mkdtemp(prefix="fv_guard_")))
            det = [d.model_dump() for d in res.differences if d.category == "text" and d.subtype != "ocr_dudoso"]
            esp = [e for e in exp.get("errores", []) if e.get("categoria") == "text"]
            c = metrics.case_counts(det, esp)["counts"]["text"]
            out[label]["err"] += c["fp"] + c["fn"]
            if exp.get("texto_cliente"):
                out[label]["cer"].append(metrics.cer(exp["texto_cliente"], res.client_text or ""))
    for k in out:
        cers = out[k].pop("cer")
        out[k]["cer"] = float(np.mean(cers)) if cers else None
    return out


def tune_type(tipo: str, samples: list, log=print) -> dict:
    """Busca los mejores parámetros con ~2/3 de los casos y los VALIDA con el resto (casos que no vio): solo se
    adoptan si allí también mejoran (evita sobreajustar a unos pocos diseños)."""
    from ..ocr_guided import DEFAULT_TUNE
    from . import vocab

    cfg = load_config()
    extra = vocab.ocr_extra_config()
    # la validación usa CASOS distintos a los del ajuste (mismo diseño en ambos lados daría una mejora engañosa)
    cases = sorted({smp[3] for smp in samples})
    val_cases = set(cases[::3])
    val = [smp for smp in samples if smp[3] in val_cases]
    train = [smp for smp in samples if smp[3] not in val_cases]
    cur = dict(DEFAULT_TUNE)
    base_tr = evaluate(cur, train, cfg, extra)
    best = base_tr
    log(f"[{tipo}] {len(train)} líneas de ajuste + {len(val)} de validación · CER inicial {base_tr * 100:.2f}%")
    for _ in range(2):  # dos pasadas de búsqueda por coordenadas
        improved = False
        for key, values in OPTIONS.items():
            for v in values:
                if v == cur[key]:
                    continue
                trial = {**cur, key: v}
                c = evaluate(trial, train, cfg, extra)
                if c < best - 0.002:
                    best, cur, improved = c, trial, True
                    log(f"  {key}={v} → CER {c * 100:.2f}%")
        if not improved:
            break
    val_before = evaluate(dict(DEFAULT_TUNE), val, cfg, extra)
    val_after = evaluate(cur, val, cfg, extra) if cur != DEFAULT_TUNE else val_before
    adopted = cur != DEFAULT_TUNE and val_after <= val_before * (1 - MIN_GAIN) and (val_before - val_after) >= 0.003
    guard = None
    if adopted:  # segunda barrera: no debe empeorar el pipeline completo en los casos de validación
        try:
            guard = pipeline_guard(sorted(val_cases), cur, log)
            b, n = guard["base"], guard["nuevo"]
            worse = n["err"] > b["err"] or (b["cer"] is not None and n["cer"] is not None and n["cer"] > b["cer"] * 1.02)
            adopted = not worse
            log(f"  pipeline completo (casos de validación): errores de texto {b['err']} → {n['err']}"
                + (f" · CER {b['cer'] * 100:.2f}% → {n['cer'] * 100:.2f}%" if b["cer"] is not None and n["cer"] is not None else ""))
        except Exception as e:  # si no se puede comprobar, no se adopta
            adopted = False
            log(f"  no se pudo comprobar con el pipeline completo ({e}); descartado")
    log(f"  validación: {val_before * 100:.2f}% → {val_after * 100:.2f}% · {'ADOPTADO' if adopted else 'descartado'}")
    return {"params": cur, "cer_antes": round(val_before, 4), "cer_despues": round(val_after, 4),
            "lineas": len(samples), "fecha": datetime.now().isoformat(timespec="seconds"), "adoptado": adopted,
            "pipeline": guard}


def autotune(tipo: str | None = None, log=print) -> dict:
    """Ajusta el preprocesado para cada tipo con suficientes líneas revisadas. Devuelve un resumen."""
    if _running.is_set():
        return {"estado": "ya se está ejecutando"}
    _running.set()
    try:
        groups = collect_samples(tipo)
        ajustes = store.load_json("ajustes_ocr.json", {})
        resumen = {}
        for t, samples in groups.items():
            if len(samples) < MIN_LINES or len({smp[3] for smp in samples}) < MIN_CASES:
                resumen[t] = {"estado": f"pocos datos ({len(samples)} líneas de {len({smp[3] for smp in samples})} casos; "
                                        f"hacen falta {MIN_LINES} líneas y {MIN_CASES} casos)"}
                continue
            res = tune_type(t, samples, log)
            resumen[t] = res
            if res["adoptado"]:
                ajustes[t] = {k: res[k] for k in ("params", "cer_antes", "cer_despues", "lineas", "fecha")}
            else:
                ajustes.pop(t, None)
        store.save_json("ajustes_ocr.json", ajustes)
        st = store.state()
        st["ultimo_autoajuste_en"] = st["casos_revisados"]
        st["ultimo_autoajuste"] = datetime.now().isoformat(timespec="seconds")
        store.save_json("estado.json", st)
        return resumen
    finally:
        _running.clear()


def is_running() -> bool:
    return _running.is_set()


def autotune_background() -> None:
    """Se ejecuta cada N casos revisados, en segundo plano."""
    if _running.is_set():
        return
    threading.Thread(target=lambda: autotune(log=lambda *_: None), daemon=True).start()
