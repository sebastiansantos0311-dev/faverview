"""Nivel 4 – re-entrenamiento (fine-tuning) del modelo `spa` de Tesseract con las líneas revisadas.

Cada línea revisada aporta un recorte del arte del cliente + el texto correcto (del PDF del diseño).
Requiere ≥ 300 líneas y las herramientas de entrenamiento del instalador UB-Mannheim (lstmtraining.exe,
combine_tessdata.exe). El modelo nuevo solo se activa si mejora el banco de pruebas (prueba A/B)."""
import json
import random
import shutil
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from ..config import BASE_DIR, DATOS_DIR, find_tesseract, load_config
from . import store

MIN_LINES = 300


def lines_dir() -> Path:
    d = store.root() / "lineas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = store.root() / "modelos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def count_lines() -> int:
    return len(list(lines_dir().glob("*.gt.txt")))


def save_lines(result, body: dict, job_dir: Path, design_path, case_name: str) -> int:
    """Guarda (recorte binarizado, texto correcto) de las líneas SIN error de texto confirmado."""
    from ..loaders import extract_pdf_layout
    from ..ocr_guided import lines_from_layout, prep_crop, DEFAULT_TUNE
    from .tuning import params_for

    img_p = job_dir / "client_aligned.png"
    if not img_p.exists():
        return 0
    client = cv2.cvtColor(cv2.imdecode(np.frombuffer(img_p.read_bytes(), np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    errs = [d.bbox for d in result.differences if d.category in ("text", "spelling") and d.review == "real"]
    errs += [m["bbox"] for m in body.get("missed", []) if m.get("categoria") in ("text", "spelling")]
    spans = extract_pdf_layout(design_path, 200, result.pages.get("design", 1) - 1)
    t = {**DEFAULT_TUNE, **(params_for(result.image_type) or {})}
    H, W = client.shape[:2]
    n = 0
    for i, ln in enumerate(lines_from_layout(spans)):
        x0, y0, x1, y1 = ln.bbox
        if any(min(x1, bx + bw) > max(x0, bx) and min(y1, by + bh) > max(y0, by) for bx, by, bw, bh in errs):
            continue
        text = " ".join(w.text for w in ln.words).strip()
        if len(text) < 3:
            continue
        h = max(ln.h, 8.0)
        cx0, cy0 = max(0, int(x0 - 0.25 * h)), max(0, int(y0 - 0.25 * h))
        cx1, cy1 = min(W, int(x1 + 0.25 * h)), min(H, int(y1 + 0.25 * h))
        crop = client[cy0:cy1, cx0:cx1]
        if crop.shape[0] < 6 or crop.shape[1] < 6:
            continue
        img = prep_crop(crop, float(np.clip(t["target_px"] / h, 0.5, 4.0)), t["method"], "best", t["k"], t["blur"])
        name = f"{case_name}_{i:03d}"
        ok, buf = cv2.imencode(".png", img)
        (lines_dir() / f"{name}.png").write_bytes(buf.tobytes())
        (lines_dir() / f"{name}.gt.txt").write_text(text + "\n", encoding="utf-8")
        n += 1
    return n


# ----------------------------------------------------------------------------- entrenamiento
def _tools() -> dict[str, Path] | None:
    tess = find_tesseract(load_config())
    if not tess:
        return None
    folder = Path(tess).parent
    t = {"tesseract": Path(tess), "lstmtraining": folder / "lstmtraining.exe",
         "combine": folder / "combine_tessdata.exe"}
    return t if all(p.exists() for p in t.values()) else None


def _run(cmd, env=None, cwd=None, log=print, check=True):
    log("  $ " + " ".join(str(c) for c in cmd)[:200])
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env, cwd=cwd,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} falló:\n{(r.stderr or r.stdout)[-800:]}")
    return r


def train(iterations: int = 800, learning_rate: float = 0.0001, min_lines: int = MIN_LINES,
          log=print) -> dict:
    """Fine-tuning de `spa`. Deja el modelo en aprendizaje/modelos/spa_fv.traineddata (no lo activa)."""
    n = count_lines()
    if n < min_lines:
        return {"ok": False, "mensaje": f"Hacen falta al menos {min_lines} líneas revisadas (hay {n})."}
    tools = _tools()
    if not tools:
        return {"ok": False, "mensaje": "No se encontraron lstmtraining.exe / combine_tessdata.exe. Reinstala Tesseract "
                "con: winget install UB-Mannheim.TesseractOCR (o usa WSL + tesstrain)."}
    cfg = load_config()
    tessdata = (BASE_DIR / "tools" / "tessdata").resolve()
    base_model = tessdata / "spa.traineddata"
    if not base_model.exists():
        return {"ok": False, "mensaje": "Falta tools/tessdata/spa.traineddata."}

    work = models_dir() / "trabajo"
    if work.exists():
        shutil.rmtree(work)
    (work / "lstmf").mkdir(parents=True)
    (work / "out").mkdir()
    env = {**__import__("os").environ, "TESSDATA_PREFIX": str(tessdata)}
    gen_env = {**env, "TESSDATA_PREFIX": str(tools["tesseract"].parent / "tessdata")}

    log("1/5 Extrayendo el modelo LSTM base…")
    _run([tools["combine"], "-e", base_model, work / "spa.lstm"], env, log=log)

    log("2/5 Generando archivos .lstmf…")
    pngs = sorted(lines_dir().glob("*.png"))
    lstmfs = []
    for png in pngs:
        gt = png.with_suffix("").with_suffix(".gt.txt")
        if not gt.exists():
            continue
        text = gt.read_text(encoding="utf-8").strip()
        h, w = cv2.imdecode(np.frombuffer(png.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE).shape[:2]
        tmp = work / "lstmf" / png.name
        shutil.copy(png, tmp)
        tmp.with_suffix(".box").write_text(f"WordStr 0 0 {w} {h} 0 #{text}\n\t 0 0 {w} {h} 0\n", encoding="utf-8")
        base = tmp.with_suffix("")
        # `lstm.train` es una configuración que viene en el tessdata del propio Tesseract (no en tools/tessdata)
        r = _run([tools["tesseract"], tmp, base, "--psm", "13", "lstm.train"], gen_env, log=lambda *_: None, check=False)
        if base.with_suffix(".lstmf").exists():
            lstmfs.append(base.with_suffix(".lstmf"))
    if len(lstmfs) < min_lines * 0.8:
        return {"ok": False, "mensaje": f"Solo se pudieron preparar {len(lstmfs)} líneas para entrenar."}

    random.Random(7).shuffle(lstmfs)
    cut = max(1, int(len(lstmfs) * 0.9))
    # rutas con «/» y saltos de línea \n (lstmtraining en Windows falla con «\» o \r\n)
    with open(work / "list.train", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(p.as_posix() for p in lstmfs[:cut]) + "\n")
    with open(work / "list.eval", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(p.as_posix() for p in lstmfs[cut:]) + "\n")

    log(f"3/5 Entrenando ({iterations} iteraciones, {cut} líneas de entrenamiento / {len(lstmfs) - cut} de validación)…")
    r = _run([tools["lstmtraining"], "--model_output", work / "out" / "spa_fv", "--continue_from", work / "spa.lstm",
              "--traineddata", base_model.as_posix(), "--train_listfile", (work / "list.train").as_posix(),
              "--eval_listfile", work / "list.eval", "--max_iterations", str(iterations),
              "--learning_rate", str(learning_rate), "--target_error_rate", "0.01"], env, log=log)

    log("4/5 Empaquetando el modelo…")
    ckpt = work / "out" / "spa_fv_checkpoint"
    if not ckpt.exists():
        cands = sorted((work / "out").glob("spa_fv*.checkpoint"))
        ckpt = cands[-1] if cands else ckpt
    model = models_dir() / "spa_fv.traineddata"
    _run([tools["lstmtraining"], "--stop_training", "--continue_from", ckpt, "--traineddata", base_model,
          "--model_output", model], env, log=log)
    info = {"ok": model.exists(), "modelo": str(model), "lineas": len(lstmfs), "iteraciones": iterations,
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "mensaje": "Modelo entrenado. Falta la prueba A/B."}
    store.save_json("modelo_info.json", info)
    return info


def build_runtime() -> Path:
    """Carpeta tessdata con spa/eng/osd + spa_fv (para que Tesseract lo encuentre)."""
    rt = models_dir() / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    for f in (BASE_DIR / "tools" / "tessdata").glob("*.traineddata"):
        shutil.copy(f, rt / f.name)
    shutil.copy(models_dir() / "spa_fv.traineddata", rt / "spa_fv.traineddata")
    return rt


def activate(on: bool) -> None:
    flag = models_dir() / "activo.txt"
    if on:
        build_runtime()
        flag.write_text("spa_fv\n", encoding="utf-8")
    else:
        flag.unlink(missing_ok=True)


def is_active() -> bool:
    return (models_dir() / "activo.txt").exists()


def ab_test(log=print, workers: int = 3) -> dict:
    """Corre el banco de pruebas con el modelo base y con el nuevo; lo activa solo si mejora CER y F1 de texto."""
    from bench import run as bench_run  # el banco vive en el repositorio

    if not (models_dir() / "spa_fv.traineddata").exists():
        return {"ok": False, "mensaje": "Todavía no hay un modelo entrenado."}
    rt = build_runtime()
    results = {}
    for label, over in (("base", []), ("nuevo", ["--set", f"tessdata_dir={json.dumps(str(rt))}",
                                                  "--set", 'ocr_lang="spa_fv+spa+eng"'])):
        log(f"Banco de pruebas con el modelo {label}…")
        out = models_dir() / f"ab_{label}.json"
        bench_run.main(["--workers", str(workers), "--etiqueta", f"A/B modelo {label}", "--salida-json", str(out),
                        *over])
        results[label] = json.loads(out.read_text(encoding="utf-8"))
    b, n = results["base"], results["nuevo"]
    cer_b, cer_n = b["global"]["cer_pct"], n["global"]["cer_pct"]
    f1_b, f1_n = b["totales"]["text"]["f1"], n["totales"]["text"]["f1"]
    better = (cer_b is None or cer_n is None or cer_n < cer_b) and f1_n >= f1_b
    if better:
        activate(True)
    msg = (f"CER {cer_b}% → {cer_n}% · F1 texto {f1_b}% → {f1_n}%. "
           + ("El modelo nuevo se activó." if better else "El modelo nuevo NO mejora: se descartó."))
    store.save_json("ab_resultado.json", {"cer_base": cer_b, "cer_nuevo": cer_n, "f1_base": f1_b, "f1_nuevo": f1_n,
                                          "activado": better, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"ok": True, "activado": better, "mensaje": msg}
