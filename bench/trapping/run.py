"""Banco de auto-trap (AUTOTRAP T6): 20 casos sintéticos × 3 perfiles. Meta: 0 filetes tras el movimiento.

Uso: uv run python -m bench.trapping.run [--ci]"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from app.core.press import PressProfile
from app.modules.separate.pdf_render import Plates
from app.modules.tools import registration_check as rc
from app.modules.tools import trapping

DPI = 254.0
W, H = 400, 300
PERFILES = {"serigrafia_0.20": PressProfile(nombre="serigrafia", tolerancia_mm=0.20), "flexo_0.15": PressProfile(nombre="flexo", tolerancia_mm=0.15),
            "offset_0.08": PressProfile(nombre="offset", tolerancia_mm=0.08)}


def _labs(rng, n, similar=False):
    out = []
    while len(out) < n:
        L = float(rng.uniform(35, 90)) if not similar else float(50 + rng.uniform(-3, 3))
        lab = (L, float(rng.uniform(-60, 60)), float(rng.uniform(-60, 60)))
        if all(np.linalg.norm(np.array(lab[1:]) - np.array(o[1:])) > 40 for o in out):
            out.append(lab)
    return out


def _split(rng, box, k, out):
    """División en guillotina de `box` en k celdas (los cortes forman uniones en T entre tres zonas entintadas)."""
    x0, y0, x1, y1 = box
    if k == 1:
        out.append(box)
        return
    left = int(rng.integers(1, k))
    r = float(rng.uniform(0.35, 0.65))
    if (x1 - x0) >= (y1 - y0):
        xm = int(x0 + (x1 - x0) * r)
        _split(rng, (x0, y0, xm, y1), left, out)
        _split(rng, (xm, y0, x1, y1), k - left, out)
    else:
        ym = int(y0 + (y1 - y0) * r)
        _split(rng, (x0, y0, x1, ym), left, out)
        _split(rng, (x0, ym, x1, y1), k - left, out)


def logo_case(seed: int, n: int, similar=False):
    """n colores: celdas contiguas (n − 1 o n − 2) y, si sobra un color, un círculo dentro de la celda más grande."""
    rng = np.random.default_rng(seed)
    lab = np.zeros((H, W), np.int32)
    cells = []
    _split(rng, (40, 40, 360, 260), max(n - 1 if n < 4 else n - 1, 2), cells)
    ncell = len(cells)
    for k, (x0, y0, x1, y1) in enumerate(cells, 1):
        lab[y0:y1, x0:x1] = k
    if n >= 5:                                                           # un círculo de otro color dentro de la celda más grande
        x0, y0, x1, y1 = max(cells, key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
        cv2.circle(lab, ((x0 + x1) // 2, (y0 + y1) // 2), int(min(x1 - x0, y1 - y0) * 0.3), ncell + 1, -1)
        total = ncell + 1
    else:
        total = ncell
    labs = _labs(rng, total + 1, similar)
    names = [f"T{k}" for k in range(1, total + 1)]
    arr = {names[k - 1]: ((lab == k) * 255).astype(np.uint8) for k in range(1, total + 1)}
    meta = {names[k - 1]: {"lab": labs[k], "tipo": "spot"} for k in range(1, total + 1)}
    return Plates(names, arr, DPI, 0, W, H), meta


def text_case(seed: int):
    rng = np.random.default_rng(seed)
    base = np.zeros((H, W), np.uint8)
    base[40:260, 40:360] = 255
    k = np.zeros((H, W), np.uint8)
    cv2.putText(k, "TRAP", (70, 160), cv2.FONT_HERSHEY_SIMPLEX, 2.4, 255, 3, cv2.LINE_AA)
    k = (k > 127).astype(np.uint8) * 255
    color = np.where(k > 0, 0, base).astype(np.uint8)
    return Plates(["Color", "Black"], {"Color": color, "Black": k}, DPI, 0, W, H), {"Color": {"lab": (80, 10, 60), "tipo": "spot"}, "Black": {"lab": (16, 0, 0), "tipo": "process"}}


def rich_black_case(seed: int):
    K = np.zeros((H, W), np.uint8)
    K[60:240, 40:200] = 255
    col = np.zeros((H, W), np.uint8)
    col[60:240, 200:360] = 255
    return (Plates(["Cyan", "Magenta", "Black", "Color"], {"Cyan": K.copy(), "Magenta": K.copy(), "Black": K, "Color": col}, DPI, 0, W, H),
            {"Color": {"lab": (85, -5, 70), "tipo": "spot"}})


def white_case(seed: int):
    wh = np.zeros((H, W), np.uint8)
    wh[40:260, 40:360] = 255
    a = np.zeros((H, W), np.uint8)
    a[80:220, 80:200] = 255
    b = np.zeros((H, W), np.uint8)
    b[80:220, 200:320] = 255
    return (Plates(["Blanco", "A", "B"], {"Blanco": wh, "A": a, "B": b}, DPI, 0, W, H),
            {"Blanco": {"lab": (94, 0, -2), "tipo": "white", "opacity": 1.0}, "A": {"lab": (60, 50, 30), "tipo": "spot"}, "B": {"lab": (35, -30, 30), "tipo": "spot"}})


def cases():
    out = [(f"logo_{n}t_{s}", *logo_case(s, n)) for s, n in enumerate([3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6, 6])]
    out += [(f"similar_{s}", *logo_case(100 + s, 4, similar=True)) for s in range(3)]
    out += [(f"texto_fino_{s}", *text_case(s)) for s in range(2)]
    out += [(f"negro_enriquecido_{s}", *rich_black_case(s)) for s in range(2)]
    out += [("base_blanca", *white_case(0))]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ci", action="store_true")
    a = ap.parse_args()
    thr = json.loads((Path(__file__).with_name("umbral_ci.json")).read_text(encoding="utf-8"))
    rows, worst_fil, worst_t, areas = [], 0, 0.0, []
    for name, plates, meta in cases():
        for pn, pf in PERFILES.items():
            t0 = time.time()
            res = trapping.trap(plates, meta, press=pf, tac_max=None)
            before = rc.check(plates, pf, meta)
            after = rc.check(res.plates, pf, meta, ignore=res.pullback_mask)
            dt = time.time() - t0
            ink = sum(int((plates.arrays[n] > 127).sum()) for n in plates.names) or 1
            changed = sum(int((res.plates.arrays[n] != plates.arrays[n]).sum()) for n in plates.names)
            pct = 100.0 * changed / ink
            rows.append({"caso": name, "perfil": pn, "filetes_antes_px": before.filetes_px, "filetes_despues_px": after.filetes_px, "area_modificada_pct": round(pct, 2), "s": round(dt, 2)})
            worst_fil = max(worst_fil, after.filetes_px)
            worst_t = max(worst_t, dt)
            areas.append(pct)
    resumen = {"casos": len(rows), "filetes_despues_max_px": worst_fil, "area_modificada_media_pct": round(float(np.mean(areas)), 2),
               "area_modificada_max_pct": round(max(areas), 2), "s_max": round(worst_t, 2),
               "con_filetes": [r for r in rows if r["filetes_despues_px"]][:10]}
    print(json.dumps(resumen, indent=1, ensure_ascii=False))
    if a.ci:
        ok = worst_fil <= thr["filetes_despues_max_px"] and max(areas) <= thr["area_modificada_max_pct"] and worst_t <= thr["segundos_max_por_caso"]
        print("CI OK" if ok else "CI FALLA")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
