"""Simula el aprendizaje con casos sintéticos: curva de CER y F1 vs número de casos revisados.

    uv run python -m bench.learn_sim [--puntos 0 5 10 15 20] [--etiqueta "F7 aprendizaje"]

Para cada N: parte de un aprendizaje vacío (carpeta temporal), "revisa" N casos de entrenamiento (veredicto real /
falso positivo calculado con la verdad conocida), corre el auto-ajuste y mide sobre casos de prueba distintos.
Con casos reales el procedimiento es el mismo (modo Revisión → Guardar caso)."""
import argparse
import json
import random
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from app import config
from app.learning import imagetype, store, tuning
from app.pipeline import run_comparison

from . import metrics
from .run import OUT_DIR, SINT_DIR, evaluate, find_cases


def _all_cases():
    return find_cases(False, True, None)


def split(cases, seed=11):
    test = cases[3::4]
    train = [c for c in cases if c not in test]
    random.Random(seed).shuffle(train)
    return train, test


def review_case(cdir: Path, datos: Path, idx: int, tmp_results: Path):
    """Equivale a: comparar → revisar → «Guardar como caso de prueba»."""
    exp = json.loads((cdir / "esperado.json").read_text(encoding="utf-8"))
    res = run_comparison(f"sim_{idx}", cdir / exp["cliente"], cdir / exp["diseno"], persist=False,
                         out_dir=tmp_results / f"sim_{idx}")
    det = [d.model_dump() for d in res.differences]
    cc = metrics.case_counts(det, exp["errores"])
    fp_idx = set(cc["fp"])
    for i, d in enumerate(res.differences):
        d.review = "falso_positivo" if i in fp_idx else "real"
    tipo = res.image_type or "exportado"
    dst = datos / "casos" / f"caso_{idx:03d}"
    shutil.copytree(cdir, dst)
    exp2 = dict(exp, tipo=tipo, caso=dst.name)
    (dst / "esperado.json").write_text(json.dumps(exp2, ensure_ascii=False, indent=1), encoding="utf-8")
    store.record_review(res, {"missed": []}, dst, dst / exp["diseno"], dst / exp["cliente"])
    return len(fp_idx)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--puntos", type=int, nargs="+", default=[0, 5, 10, 15, 20])
    ap.add_argument("--etiqueta", default="F7 aprendizaje")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(argv)

    cases = _all_cases()
    train, test = split(cases)
    rows = []
    for n in a.puntos:
        datos = Path(tempfile.mkdtemp(prefix="fv_learn_"))
        import os
        os.environ["FAVERVIEW_DATOS"] = str(datos)
        config.DATOS_DIR = datos
        import app.learning.store as st_mod
        import app.learning.tuning as tun_mod
        st_mod.DATOS_DIR = datos
        tun_mod.DATOS_DIR = datos
        tmp_results = datos / "_res"
        config.RESULTS_DIR = tmp_results
        print(f"\n=== N = {n} casos revisados ===")
        for i, c in enumerate(train[:n], 1):
            review_case(c, datos, i, tmp_results)
        if n >= 5:
            print("Auto-ajuste del OCR…")
            tuning.autotune(log=lambda *_: None)
        # evaluación sobre los casos de prueba (con el aprendizaje de este punto)
        from .run import _run_case
        from concurrent.futures import ProcessPoolExecutor
        tmp = Path(tempfile.mkdtemp(prefix="fv_bench_"))
        jobs = [(c, {}, str(tmp)) for c in test]
        with ProcessPoolExecutor(a.workers) as ex:
            results = list(ex.map(_run_case, jobs))
        ev = evaluate(results, tmp / "media", tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        t = ev["totales"]
        row = {"n": n, "cer_pct": ev["global"]["cer_pct"], "fp_por_caso": ev["global"]["fp_por_caso"],
               "texto_f1": t["text"]["f1"], "texto_precision": t["text"]["precision"], "texto_recall": t["text"]["recall"],
               "todas_f1": t["todas"]["f1"], "vocabulario": len((datos / "aprendizaje" / "vocabulario.txt").read_text(
                   encoding="utf-8").splitlines()) if (datos / "aprendizaje" / "vocabulario.txt").exists() else 0,
               "confusiones": len(json.loads((datos / "aprendizaje" / "confusiones.json").read_text(encoding="utf-8"))["pares"])
               if (datos / "aprendizaje" / "confusiones.json").exists() else 0,
               "ajustes": list(store.load_json("ajustes_ocr.json", {}).keys())}
        print(row)
        rows.append(row)
        shutil.rmtree(datos, ignore_errors=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md = [f"# {a.etiqueta} – curva de aprendizaje (simulada con casos sintéticos)\n",
          f"Entrenamiento: hasta {max(a.puntos)} casos · Prueba: {len(test)} casos distintos.\n",
          "| Casos revisados | CER % | FP/caso | Texto P % | Texto R % | Texto F1 % | Vocabulario | Confusiones | Ajustes |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['n']} | {r['cer_pct']} | {r['fp_por_caso']} | {r['texto_precision']} | {r['texto_recall']} | "
                  f"{r['texto_f1']} | {r['vocabulario']} | {r['confusiones']} | {', '.join(r['ajustes']) or '—'} |")
    (OUT_DIR / f"{stamp}_{a.etiqueta.replace(' ', '_')}_curva.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (OUT_DIR / f"{stamp}_{a.etiqueta.replace(' ', '_')}_curva.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
