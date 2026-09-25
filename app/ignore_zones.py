"""Zonas a ignorar y plantillas por cliente (datos_locales/plantillas/<nombre>.json).

Las zonas se guardan en coordenadas RELATIVAS (0–1) al diseño, así valen aunque cambie la resolución.
Cada zona tiene un modo: "todo" (ignora cualquier diferencia), "color" (solo color) o "texto" (texto, ortografía y fuente)."""
import json
import re
from pathlib import Path

import numpy as np

from .config import DATOS_DIR
from .models import Difference

MODES = ("todo", "color", "texto")
_NAME_OK = re.compile(r"[^\w\-–— .()]", re.UNICODE)


def templates_dir() -> Path:
    d = DATOS_DIR / "plantillas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(name: str) -> str:
    n = _NAME_OK.sub("", name).strip().strip(".")
    if not n:
        raise ValueError("Ponle un nombre a la plantilla.")
    return n[:80]


def normalize_zone(z: dict) -> dict:
    x, y, w, h = (float(z[k]) for k in ("x", "y", "w", "h"))
    x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
    w, h = min(max(w, 0.0), 1.0 - x), min(max(h, 0.0), 1.0 - y)
    modo = z.get("modo", "todo")
    return {"x": x, "y": y, "w": w, "h": h, "modo": modo if modo in MODES else "todo"}


def list_templates() -> list[dict]:
    out = []
    for p in sorted(templates_dir().glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"nombre": d["nombre"], "zonas": len(d.get("zonas", [])), "ancho": d.get("ancho"),
                        "alto": d.get("alto")})
        except Exception:
            continue
    return out


def load_template(name: str) -> dict | None:
    p = templates_dir() / f"{safe_name(name)}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_template(name: str, zones: list[dict], width: int | None = None, height: int | None = None) -> dict:
    name = safe_name(name)
    data = {"nombre": name, "zonas": [normalize_zone(z) for z in zones], "ancho": width, "alto": height}
    (templates_dir() / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def delete_template(name: str) -> None:
    (templates_dir() / f"{safe_name(name)}.json").unlink(missing_ok=True)


def suggest(filename: str, width: int | None, height: int | None) -> list[str]:
    """Plantillas cuyo nombre aparece en el nombre del archivo o cuyo tamaño coincide (±3%)."""
    fn = filename.lower()
    res = []
    for t in list_templates():
        hit = t["nombre"].lower() in fn
        if not hit and width and height and t.get("ancho") and t.get("alto"):
            hit = abs(t["ancho"] - width) / width < 0.03 and abs(t["alto"] - height) / height < 0.03
        if hit:
            res.append(t["nombre"])
    return res


def zone_mask(zones: list[dict], W: int, H: int, modes=("todo",)) -> np.ndarray:
    """Máscara booleana (H×W) de las zonas con alguno de los modos indicados."""
    m = np.zeros((H, W), bool)
    for z in zones:
        if z["modo"] in modes:
            x0, y0 = int(z["x"] * W), int(z["y"] * H)
            m[y0:int((z["y"] + z["h"]) * H) + 1, x0:int((z["x"] + z["w"]) * W) + 1] = True
    return m


def _in_zone(d: Difference, z: dict, W: int, H: int) -> bool:
    x, y, w, h = d.bbox
    cx, cy = (x + w / 2) / W, (y + h / 2) / H
    inside_center = z["x"] <= cx <= z["x"] + z["w"] and z["y"] <= cy <= z["y"] + z["h"]
    iw = min(x + w, (z["x"] + z["w"]) * W) - max(x, z["x"] * W)
    ih = min(y + h, (z["y"] + z["h"]) * H) - max(y, z["y"] * H)
    overlap = (iw * ih) / max(1.0, w * h) if iw > 0 and ih > 0 else 0.0
    return inside_center or overlap >= 0.5


def affected(d: Difference, zones: list[dict], W: int, H: int) -> bool:
    """¿Alguna zona ignora esta diferencia (según su modo)?"""
    for z in zones:
        if not _in_zone(d, z, W, H):
            continue
        if z["modo"] == "todo":
            return True
        if z["modo"] == "color" and (d.category == "color" or d.subtype in ("color_distinto", "zona")):
            return True
        if z["modo"] == "texto" and d.category in ("text", "spelling", "font"):
            return True
    return False
