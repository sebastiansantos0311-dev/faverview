"""Banco del vectorizador (S4 §8.4): 40 logos sintéticos con vector verdadero contra VTracer y Potrace.

Uso: uv run python -m bench.vector.run [--casos N] [--etiqueta x] [--ci]"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import potrace
import vtracer
from skimage.metrics import structural_similarity

from app.config import DATOS_DIR
from app.modules.vectorize import export, pipeline, quantize
from bench.vector import synth

OUT = DATOS_DIR / "bench_resultados"


def nodes(svg: str) -> int:
    return len(re.findall(r"[MLCQZmlcqz]", " ".join(re.findall(r'\bd="([^"]*)"', svg))))


def ours(img, dpi=None, **kw):
    r = pipeline.vectorize(img, dpi, preset="logo", **kw)
    h, w = img.shape[:2]
    svg = export.to_svg(r)
    # el vector está en px de la imagen de trabajo (escalada): se ajusta el viewBox al tamaño original
    svg = re.sub(r'viewBox="[^"]*"', f'viewBox="0 0 {r.width} {r.height}" width="{w}" height="{h}"', svg, 1)
    return svg


def vt(img):
    ok, b = cv2.imencode(".png", img[..., ::-1])
    svg = vtracer.convert_raw_image_to_svg(b.tobytes(), img_format="png", colormode="color", hierarchical="stacked",
                                           filter_speckle=4, color_precision=6, layer_difference=16, mode="spline",
                                           corner_threshold=60, length_threshold=4.0, splice_threshold=45)
    return svg


def po(img):
    """Potrace es solo B/N: se traza cada color de la paleta como una capa apilada (mayor área primero)."""
    labels, pal = quantize.quantize(img, None, None, 8, 8.0, 4)
    h, w = labels.shape
    order = np.argsort(-np.bincount(labels.ravel()))
    from app.core import colorscience as cs
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">']
    for k in order:
        bm = potrace.Bitmap(labels == k)
        pl = bm.trace(turdsize=2, alphamax=1.0, opticurve=True, opttolerance=0.4)
        d = ""
        for c in pl:
            sp = c.start_point
            d += f"M{sp.x:.1f} {sp.y:.1f}"
            for s in c.segments:
                if s.is_corner:
                    d += f"L{s.c.x:.1f} {s.c.y:.1f}L{s.end_point.x:.1f} {s.end_point.y:.1f}"
                else:
                    d += f"C{s.c1.x:.1f} {s.c1.y:.1f} {s.c2.x:.1f} {s.c2.y:.1f} {s.end_point.x:.1f} {s.end_point.y:.1f}"
            d += "Z"
        parts.append(f'<path fill="{cs.lab_to_hex(pal[k].lab)}" fill-rule="evenodd" d="{d}"/>')
    parts.append("</svg>")
    return "".join(parts)


def measure(svg: str, truth: np.ndarray) -> dict:
    h, w = truth.shape[:2]
    m = re.search(r'viewBox="([\d.\s-]+)"', svg)
    vw, vh = [float(x) for x in m.group(1).split()[2:4]] if m else (w, h)
    sv = re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
    sv = sv.replace("<svg", f'<svg width="{w}" height="{h}"', 1)
    img = synth.render_svg(sv)[..., :3]
    if img.shape[:2] != (h, w):
        img = cv2.resize(img, (w, h))
    ssim = float(structural_similarity(img, truth, channel_axis=2, data_range=255))
    a = synth.render_svg(sv, alpha=True, aa=False)
    gaps = float((a[..., 3] == 0).mean() * 100) if a.shape[-1] == 4 else 0.0
    return {"ssim": ssim, "huecos": gaps, "nodos": nodes(svg)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--casos", type=int, default=40)
    ap.add_argument("--etiqueta", default="")
    ap.add_argument("--ci", action="store_true")
    a = ap.parse_args()
    tools = {"FAVERVIEW": ours, "FAVERVIEW v2": lambda i: ours(i, primitives=True, geometria_limpia=True), "VTracer": vt, "Potrace": po}
    rows = {t: [] for t in tools}
    for s in range(a.casos):
        img, truth, _, n = synth.degrade(s)
        for name, fn in tools.items():
            t = time.time()
            try:
                svg = fn(img)
                r = measure(svg, truth)
            except Exception as e:  # una herramienta que falla cuenta como peor resultado
                r = {"ssim": 0.0, "huecos": 100.0, "nodos": 10 ** 6, "error": str(e)[:80]}
            r["seg"] = time.time() - t
            rows[name].append(r)
        print(f"caso {s + 1}/{a.casos}", {t: (round(rows[t][-1]['ssim'], 3), rows[t][-1]['nodos']) for t in tools}, flush=True)
    summ = {t: {k: round(float(np.mean([r[k] for r in v])), 4) for k in ("ssim", "huecos", "nodos", "seg")} for t, v in rows.items()}
    f, v = rows["FAVERVIEW"], rows["VTracer"]
    win_ssim = float(np.mean([a_["ssim"] >= b["ssim"] - 0.005 for a_, b in zip(f, v)]))
    win_nodes = float(np.mean([a_["nodos"] <= b["nodos"] for a_, b in zip(f, v) if a_["ssim"] >= b["ssim"] - 0.005] or [0]))
    res = {"resumen": summ, "ssim_ge_vtracer": round(win_ssim, 3), "nodos_le_vtracer": round(win_nodes, 3)}
    print(json.dumps(res, indent=2))
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    md = [f"# Banco del vectorizador — {stamp} {a.etiqueta}", "", f"{a.casos} logos sintéticos con vector verdadero.", "",
          "| Herramienta | SSIM | Huecos % | Nodos | s/imagen |", "|---|---|---|---|---|"]
    md += [f"| {t} | {s['ssim']} | {s['huecos']} | {s['nodos']} | {s['seg']} |" for t, s in summ.items()]
    md += ["", f"SSIM ≥ VTracer (±0.005): {win_ssim:.0%} de los casos. Nodos ≤ VTracer a igual SSIM: {win_nodes:.0%}."]
    (OUT / f"{stamp}_vector_{a.etiqueta or 'sin_etiqueta'}.md").write_text("\n".join(md), encoding="utf-8")
    if a.ci:
        ok = summ["FAVERVIEW"]["huecos"] < 0.01 and win_ssim >= 0.5
        print("CI OK" if ok else "CI FALLA")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
