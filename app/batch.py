"""Fase 8.4 – comparar todas las páginas de dos archivos de varias páginas."""
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from scipy.optimize import linear_sum_assignment

from . import history
from .config import RESULTS_DIR, UPLOADS_DIR, load_config
from .loaders import load_as_image, page_count
from .pipeline import run_comparison
from .scoring import status_for


def _thumb(path, page: int) -> np.ndarray:
    im = load_as_image(path, 30, page)
    g = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    return cv2.resize(g, (48, 64), interpolation=cv2.INTER_AREA).astype(np.float32)


def pair_pages(client_path, design_path) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Empareja páginas: por orden si hay el mismo número; si no, por similitud visual (asignación óptima)."""
    n, m = page_count(client_path), page_count(design_path)
    if n == m:
        return [(i, i) for i in range(n)], [], []
    ct = [_thumb(client_path, i) for i in range(n)]
    dt = [_thumb(design_path, j) for j in range(m)]
    cost = np.array([[np.abs(a - b).mean() for b in dt] for a in ct])
    rows, cols = linear_sum_assignment(cost)
    pairs = sorted((int(i), int(j)) for i, j in zip(rows, cols))
    return pairs, [i for i in range(n) if i not in rows], [j for j in range(m) if j not in cols]


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy(src, dst)


def run_batch(batch_id: str, client_path, design_path, client_name: str, design_name: str, params: dict | None,
              progress=None) -> dict:
    prog = progress or (lambda *a: None)
    pairs, sin_c, sin_d = pair_pages(client_path, design_path)
    cs, ds = Path(client_path).suffix, Path(design_path).suffix
    rows = []
    for k, (ci, di) in enumerate(pairs):
        prog("ocr", k / max(1, len(pairs)), f"Comparando página {k + 1} de {len(pairs)}…")
        jid = uuid.uuid4().hex[:12]
        up = UPLOADS_DIR / jid
        _link(Path(client_path), up / f"client{cs}")
        _link(Path(design_path), up / f"design{ds}")
        (up / "meta.json").write_text(json.dumps({"client_name": client_name, "design_name": design_name}), encoding="utf-8")
        res = run_comparison(jid, client_path, design_path, params, ci, di, client_name, design_name)
        vivos = [d for d in res.differences if not d.ignored_by_zone]
        rows.append({"n": k + 1, "client_page": ci + 1, "design_page": di + 1, "job_id": jid,
                     "total": res.scores["total"], "status": res.status, "errores": len(vivos),
                     "pendientes": sum(d.status == "pendiente" for d in vivos)})
    prom = round(float(np.mean([r["total"] for r in rows])), 1) if rows else 0.0
    summary = {"batch_id": batch_id, "client_name": client_name, "design_name": design_name, "paginas": rows,
               "sin_pareja_cliente": [i + 1 for i in sin_c], "sin_pareja_diseno": [j + 1 for j in sin_d],
               "total_promedio": prom, "estado_global": status_for(min([r["total"] for r in rows] or [0])),
               "created": datetime.now().isoformat(timespec="seconds")}
    out = RESULTS_DIR / batch_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "batch.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    history.add_entry({"job_id": batch_id, "created": summary["created"], "client_name": client_name + f" ({len(rows)} págs.)",
                       "design_name": design_name, "total": prom, "status": summary["estado_global"], "batch": True})
    prog("cierre", 1.0, "Listo")
    return summary


def merge_reports(batch_id: str, out_path: Path) -> Path:
    """Reporte PDF único con todas las páginas del lote (portada del lote + el reporte de cada página)."""
    from .models import Result
    from .report import build_report, STATUS

    summary = json.loads((RESULTS_DIR / batch_id / "batch.json").read_text(encoding="utf-8"))
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 80), "FAVERVIEW - Reporte del lote", fontsize=22, fontname="hebo")
    p.insert_text((50, 110), f"Fecha: {summary['created'].replace('T', ' ')}", fontsize=11)
    p.insert_text((50, 130), f"Arte del cliente: {summary['client_name']}", fontsize=11)
    p.insert_text((50, 146), f"Mi diseño: {summary['design_name']}", fontsize=11)
    p.insert_text((50, 190), f"Similitud promedio: {summary['total_promedio']}%", fontsize=18, fontname="hebo")
    y = 230
    for r in summary["paginas"]:
        label = STATUS[r["status"]][0]
        p.insert_text((50, y), f"Página {r['n']} (cliente {r['client_page']} / diseño {r['design_page']}): "
                      f"{r['total']}% - {label} - {r['errores']} errores, {r['pendientes']} pendientes", fontsize=11)
        y += 18
    for lst, txt in ((summary["sin_pareja_cliente"], "Páginas del cliente sin pareja"),
                     (summary["sin_pareja_diseno"], "Páginas del diseño sin pareja")):
        if lst:
            y += 8
            p.insert_text((50, y), f"{txt}: {', '.join(map(str, lst))}", fontsize=11, color=(0.7, 0.3, 0))
            y += 18
    for r in summary["paginas"]:
        d = RESULTS_DIR / r["job_id"]
        res = Result.model_validate_json((d / "result.json").read_text(encoding="utf-8"))
        tmp = d / "_reporte_lote.pdf"
        build_report(res, d, tmp)
        with pymupdf.open(tmp) as sub:
            doc.insert_pdf(sub)
        tmp.unlink(missing_ok=True)
    doc.save(out_path)
    doc.close()
    return out_path
