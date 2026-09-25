"""Banco de pruebas.  Uso:

    uv run python -m bench.run [--real] [--sinteticos] [--caso caso_007] [--etiqueta "antes de F6"]
                               [--workers 3] [--ci] [--set ocr_mode=pagina]
"""
import argparse
import json
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from app.config import DATOS_DIR
from app.pipeline import run_comparison

from . import metrics
from .report import load_previous, render_html, render_markdown

ROOT = Path(__file__).resolve().parent.parent
SINT_DIR = ROOT / "tests" / "sinteticos"
REAL_DIR = DATOS_DIR / "casos"
OUT_DIR = DATOS_DIR / "bench_resultados"
CI_FILE = Path(__file__).resolve().parent / "umbral_ci.json"


def find_cases(real: bool, sint: bool, only: str | None) -> list[Path]:
    dirs = []
    if real and REAL_DIR.exists():
        dirs += sorted(p for p in REAL_DIR.iterdir() if (p / "esperado.json").exists())
    if sint and SINT_DIR.exists():
        dirs += sorted(p for p in SINT_DIR.iterdir() if (p / "esperado.json").exists())
    if only:
        dirs = [d for d in dirs if only in d.name]
    return dirs


def _run_case(args):
    cdir, overrides, tmp = args
    exp = json.loads((cdir / "esperado.json").read_text(encoding="utf-8"))
    out = Path(tmp) / cdir.name
    try:
        res = run_comparison(
            "bench_" + cdir.name, cdir / exp["cliente"], cdir / exp["diseno"],
            {"overrides": overrides}, exp.get("pagina_cliente", 1) - 1, exp.get("pagina_diseno", 1) - 1,
            persist=False, out_dir=out)
        return cdir.name, exp, res.model_dump(), None
    except Exception as e:  # un caso roto no debe tumbar el banco
        return cdir.name, exp, None, f"{type(e).__name__}: {e}"


def _thumb(media_dir: Path, tmp: Path, case: str, bbox, name: str) -> str | None:
    def read(p):
        return cv2.imdecode(np.frombuffer(p.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    try:
        d, c = read(tmp / case / "design.png"), read(tmp / case / "client_aligned.png")
    except Exception:
        return None
    H, W = d.shape[:2]
    x, y, w, h = (int(v) for v in bbox)
    pad = 20
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    tiles = []
    for im in (c, d):
        t = im[y0:y1, x0:x1]
        s = min(220 / max(t.shape[1], 1), 90 / max(t.shape[0], 1), 3.0)
        tiles.append(cv2.resize(t, None, fx=s, fy=s))
    hh = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, hh - t.shape[0], 0, 6, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
    media_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(media_dir / name), np.hstack(tiles))
    return name


def evaluate(results, media_dir: Path, tmp: Path) -> dict:
    per_case, errors = [], []
    thumbs = 0
    for case, exp, res, err in results:
        if err:
            errors.append(f"{case}: {err}")
            continue
        det = [d for d in res["differences"] if not d.get("ignored_by_zone") and d.get("subtype") != "ocr_dudoso"]
        expected = exp.get("errores", [])
        cc = metrics.case_counts(det, expected)
        cer = metrics.cer(exp["texto_cliente"], res.get("client_text") or "") if exp.get("texto_cliente") else None
        fp_list, fn_list = [], []
        for n, i in enumerate(cc["fp"]):
            d = dict(det[i])
            d["thumb"] = _thumb(media_dir, tmp, case, d["bbox"], f"{case}_fp{n}.png") if thumbs < 400 else None
            thumbs += 1
            fp_list.append({k: d.get(k) for k in ("category", "subtype", "message", "bbox", "thumb")})
        for n, j in enumerate(cc["fn"]):
            e = dict(expected[j])
            e["thumb"] = _thumb(media_dir, tmp, case, e["bbox"], f"{case}_fn{n}.png") if thumbs < 400 else None
            thumbs += 1
            fn_list.append(e)
        per_case.append({
            "caso": case, "tipo": exp.get("tipo", "?"), "counts": cc["counts"], "n_expected": len(expected),
            "status": res["status"], "total": res["scores"]["total"], "cer": cer, "elapsed_s": res["elapsed_s"],
            "timings": res["timings"], "fp_list": fp_list, "fn_list": fn_list, "warnings": res["warnings"]})
    por_tipo = {}
    for t in sorted({c["tipo"] for c in per_case}):
        sub = [c for c in per_case if c["tipo"] == t]
        agg = metrics.aggregate(sub)["todas"]
        gs = metrics.global_stats(sub)
        por_tipo[t] = {"casos": len(sub), "recall": agg["recall"], "precision": agg["precision"],
                       "fp_por_caso": gs["fp_por_caso"], "cer_pct": gs["cer_pct"]}
    return {"por_caso": per_case, "totales": metrics.aggregate(per_case), "global": metrics.global_stats(per_case),
            "por_tipo": por_tipo, "fallos": errors}


def check_ci(run: dict) -> int:
    if not CI_FILE.exists():
        print("No hay bench/umbral_ci.json; se omite la comprobación.")
        return 0
    thr = json.loads(CI_FILE.read_text(encoding="utf-8"))
    bad = []
    for cat, minimum in thr.items():
        got = run["totales"].get(cat, {}).get("f1")
        if got is not None and got < minimum - 2:
            bad.append(f"{cat}: F1 {got} < umbral {minimum} - 2")
    if run["fallos"]:
        bad += run["fallos"]
    if bad:
        print("CI FALLA:\n  " + "\n  ".join(bad))
        return 1
    print("CI OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bench.run")
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--sinteticos", action="store_true")
    ap.add_argument("--caso")
    ap.add_argument("--etiqueta", default="sin_etiqueta")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ci", action="store_true")
    ap.add_argument("--set", action="append", default=[], metavar="clave=valor",
                    help="sobrescribe un valor de config.json solo para esta corrida")
    ap.add_argument("--contra", help="compara contra la corrida anterior cuya etiqueta contenga este texto")
    ap.add_argument("--salida-json", help="además guarda el resultado en esta ruta (uso interno)")
    ap.add_argument("--guardar-umbral", action="store_true", help="guarda los F1 actuales en bench/umbral_ci.json")
    a = ap.parse_args(argv)
    if not a.real and not a.sinteticos:
        a.real = a.sinteticos = True

    overrides = {}
    for kv in a.set:
        k, v = kv.split("=", 1)
        try:
            v = json.loads(v)
        except ValueError:
            pass
        overrides[k] = v

    cases = find_cases(a.real, a.sinteticos, a.caso)
    if a.limit:
        cases = cases[:a.limit]
    if not cases:
        print("No hay casos. Genera los sintéticos con: uv run python -m bench.synth")
        return 1
    scope = "+".join(s for s, on in (("real", a.real), ("sinteticos", a.sinteticos)) if on)
    if a.caso:
        scope += f":{a.caso}"
    print(f"{len(cases)} casos ({scope}) con {a.workers} procesos…")

    tmp = Path(tempfile.mkdtemp(prefix="fv_bench_"))
    try:
        jobs = [(c, overrides, str(tmp)) for c in cases]
        if a.workers > 1:
            with ProcessPoolExecutor(a.workers) as ex:
                results = list(ex.map(_run_case, jobs))
        else:
            results = [_run_case(j) for j in jobs]
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in a.etiqueta)
        name = f"{stamp}_{safe}"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        media = OUT_DIR / f"{name}_media"
        run = evaluate(results, media, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    run.update({"etiqueta": a.etiqueta, "fecha": datetime.now().isoformat(timespec="seconds"), "scope": scope,
                "overrides": overrides})
    prev = load_previous(OUT_DIR, name, scope, a.contra)
    md = render_markdown(run, prev, media.name)
    (OUT_DIR / f"{name}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / f"{name}.md").write_text(md, encoding="utf-8")
    (OUT_DIR / f"{name}.html").write_text(render_html(md, name), encoding="utf-8")

    if a.salida_json:
        Path(a.salida_json).write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    t = run["totales"]
    print(f"\nTexto: P {t['text']['precision']}% R {t['text']['recall']}% · Color+visual: R {t['color_visual']['recall']}% "
          f"· Ortografía R {t['spelling']['recall']}% · Fuente R {t['font']['recall']}%")
    g = run["global"]
    print(f"FP/caso {g['fp_por_caso']} · idénticos aprobados {g['identicos_aprobados_pct']}% · CER {g['cer_pct']}% "
          f"· {g['tiempo_medio_s']} s/caso")
    if run["fallos"]:
        print("Casos con error:", *run["fallos"], sep="\n  ")
    print("Reporte:", OUT_DIR / f"{name}.md")
    if a.guardar_umbral:
        CI_FILE.write_text(json.dumps({k: run["totales"][k]["f1"] for k in metrics.CATEGORIES}, indent=1), encoding="utf-8")
        print("Umbral CI guardado en", CI_FILE)
    return check_ci(run) if a.ci else 0


if __name__ == "__main__":
    sys.exit(main())
