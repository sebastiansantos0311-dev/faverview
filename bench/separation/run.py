"""Banco de S3: 25 casos sintéticos (12 de tintas planas, 13 de proceso simulado).

Uso: uv run python -m bench.separation.run [--ci] [--guardar-base]"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from app.core import colorscience as cs
from app.modules.separate import raster

BASE = Path(__file__).with_name("linea_base.json")
INKS6 = [raster.Ink("Blanco", (95, 0, -2), 1.0), raster.Ink("Cyan", (55, -37, -50)), raster.Ink("Magenta", (48, 74, -3)),
         raster.Ink("Yellow", (89, -5, 93)), raster.Ink("Negro", (16, 0, 0)), raster.Ink("Naranja", (62, 55, 70))]


def flat_case(seed: int):
    rng = np.random.default_rng(seed)
    n = 2 + seed % 7
    while True:                                           # colores bien separados
        cols = rng.integers(0, 256, (n, 3))
        labs = np.array([cs.srgb_to_lab(c / 255.0) for c in cols])
        if all(float(cs.delta_e2000(labs[i], labs[j])) > 25 for i in range(n) for j in range(i)):
            break
    h, w = 300, 400
    truth = np.zeros((h, w), np.int32)
    truth[:] = 0
    for k in range(1, n):
        c = (int(rng.integers(40, w - 40)), int(rng.integers(40, h - 40)))
        if k % 2:
            cv2.circle(truth, c, int(rng.integers(20, 60)), k, -1)
        else:
            cv2.rectangle(truth, c, (c[0] + int(rng.integers(30, 90)), c[1] + int(rng.integers(20, 70))), k, -1)
    img = cols[truth].astype(np.uint8)
    # antialias: se suaviza el borde y se comprime en JPEG
    img = cv2.GaussianBlur(img, (3, 3), 0.7)
    _, b = cv2.imencode(".jpg", img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 75])
    img = cv2.imdecode(b, 1)[..., ::-1].copy()
    return img, truth, labs


def eval_flat(seed: int) -> dict:
    img, truth, labs = flat_case(seed)
    res = raster.separate_flat(img, 200, k_max=12)
    pal = np.array([i.lab for i in res.palette])
    idx = np.stack([res.channels[n] for n in res.names]).argmax(0)
    de, ious = [], []
    for k in range(len(labs)):
        m = truth == k
        if not m.any():
            continue
        de.append(min(float(cs.delta_e2000(labs[k], p)) for p in pal))
        best = np.bincount(idx[m]).argmax()
        pr = idx == best
        ious.append((pr & m).sum() / max((pr | m).sum(), 1))
    return {"de_paleta": float(np.mean(de)), "iou": float(np.mean(ious)), "tintas": len(res.names), "verdaderas": len(labs)}


def photo(seed: int):
    rng = np.random.default_rng(100 + seed)
    h, w = 240, 320
    noise = rng.random((h // 8, w // 8, 3)).astype(np.float32)
    img = cv2.resize(noise, (w, h), interpolation=cv2.INTER_CUBIC)
    img = cv2.GaussianBlur(img, (0, 0), 6)
    img = (img - img.min()) / (img.max() - img.min())
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def eval_process(seed: int) -> dict:
    sub = raster.SUBSTRATES["Papel blanco" if seed % 2 else "Prenda negra"]
    res = raster.separate_process(photo(seed), INKS6, sub, white_index=0, choke_px=1)
    return {"de_medio": res.stats["de_medio"], "de_p95": res.stats["de_p95"], "tac_medio": res.stats["cobertura_total_media"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true")
    ap.add_argument("--guardar-base", action="store_true")
    a = ap.parse_args()
    flat = [eval_flat(s) for s in range(12)]
    proc = [eval_process(s) for s in range(13)]
    out = {"planas": {"iou_medio": round(float(np.mean([f["iou"] for f in flat])), 4),
                      "de_paleta_medio": round(float(np.mean([f["de_paleta"] for f in flat])), 3),
                      "tintas_de_mas": int(sum(max(f["tintas"] - f["verdaderas"], 0) for f in flat))},
           "proceso": {"de_medio": round(float(np.mean([p["de_medio"] for p in proc])), 3),
                       "de_p95": round(float(np.mean([p["de_p95"] for p in proc])), 3),
                       "tac_medio": round(float(np.mean([p["tac_medio"] for p in proc])), 1)}}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if a.guardar_base:
        BASE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    ok = out["planas"]["iou_medio"] >= 0.96 and out["planas"]["de_paleta_medio"] <= 3 and out["proceso"]["de_medio"] <= 12
    if BASE.exists():
        b = json.loads(BASE.read_text(encoding="utf-8"))
        ok &= out["planas"]["iou_medio"] >= b["planas"]["iou_medio"] - 0.01 and out["proceso"]["de_medio"] <= b["proceso"]["de_medio"] + 0.5
    if a.ci:
        print("CI OK" if ok else "CI FALLA")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
