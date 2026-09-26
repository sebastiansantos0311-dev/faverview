"""Render de separaciones (S2 §6.2): Ghostscript `tiffsep` → una placa de 8 bits por tinta + vista compuesta simulada.

Convención interna: cobertura 0–255 con 255 = 100 % de tinta (tiffsep entrega el valor invertido: 255 = sin tinta)."""
import hashlib
import json
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

import cv2
import numpy as np
from PIL import Image

from app.config import RESULTS_DIR, load_config
from app.core import colorscience as cs
from app.core import ghostscript
from app.core import inks as inkmod
from app.core.errors import UserError
from app.core.pdfinfo import read_pdf_info
from app.core.units import IN_PT

CACHE_DIR = RESULTS_DIR / "separar" / "_cache"
PROCESS = ["Cyan", "Magenta", "Yellow", "Black"]


@dataclass
class Plates:
    names: list[str]
    arrays: dict[str, np.ndarray]        # nombre → (H, W) uint8, 255 = 100 % de tinta
    dpi: float
    page: int                            # base 0
    width: int
    height: int
    warnings: list[str] = field(default_factory=list)
    key: str = ""

    def pct(self, name: str) -> float:
        return float(self.arrays[name].mean()) / 255.0 * 100.0

    def empty(self, name: str) -> bool:
        return not self.arrays[name].any()


def _file_key(path: Path, page: int, dpi: float) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"{h.hexdigest()[:20]}_{page}_{int(dpi)}"


def plan_dpi(path, page: int, dpi: float, max_mpx: float | None = None) -> tuple[float, list[str]]:
    """Baja el dpi si el render superaría `max_render_mpx` megapíxeles (y avisa)."""
    info = read_pdf_info(path)
    b = info.boxes[min(page, len(info.boxes) - 1)]
    w_pt, h_pt = b.crop[2] - b.crop[0], b.crop[3] - b.crop[1]
    if b.rotate in (90, 270):
        w_pt, h_pt = h_pt, w_pt
    limit = float(max_mpx or load_config().get("max_render_mpx", 120))
    mpx = (w_pt / IN_PT * dpi) * (h_pt / IN_PT * dpi) / 1e6
    if mpx <= limit:
        return float(dpi), []
    new = dpi * (limit / mpx) ** 0.5
    return float(int(new)), [f"La página a {dpi:g} dpi tendría {mpx:.0f} Mpx (máximo {limit:g}); se usó {int(new)} dpi. "
                             "Sube el límite «max_render_mpx» en config.json si tu equipo lo aguanta."]


def _save_cache(plates: Plates):
    d = CACHE_DIR / plates.key
    d.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(plates.names):
        ok, buf = cv2.imencode(".png", plates.arrays[n], [cv2.IMWRITE_PNG_COMPRESSION, 3])
        (d / f"{i}.png").write_bytes(buf.tobytes())
    (d / "meta.json").write_text(json.dumps({"names": plates.names, "dpi": plates.dpi, "page": plates.page,
                                             "width": plates.width, "height": plates.height,
                                             "warnings": plates.warnings}, ensure_ascii=False), encoding="utf-8")


def _load_cache(key: str) -> Plates | None:
    d = CACHE_DIR / key
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        arrays = {}
        for i, n in enumerate(meta["names"]):
            arrays[n] = cv2.imdecode(np.frombuffer((d / f"{i}.png").read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
        d.touch()
        return Plates(meta["names"], arrays, meta["dpi"], meta["page"], meta["width"], meta["height"], meta["warnings"], key)
    except Exception:
        return None


def prune_cache(max_age_days: int = 30) -> None:
    if not CACHE_DIR.exists():
        return
    limit = time.time() - max_age_days * 86400
    for p in CACHE_DIR.iterdir():
        try:
            if p.is_dir() and p.stat().st_mtime < limit:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def render_plates(pdf_path, page: int = 0, dpi: float = 150, cancel: threading.Event | None = None,
                  use_cache: bool = True) -> Plates:
    """Separa la página `page` (base 0) en placas con Ghostscript tiffsep."""
    pdf_path = Path(pdf_path)
    dpi, warns = plan_dpi(pdf_path, page, dpi)
    key = _file_key(pdf_path, page, dpi)
    if use_cache:
        hit = _load_cache(key)
        if hit is not None:
            return hit
    tmp = Path(tempfile.mkdtemp(prefix="fv_sep_"))
    try:
        ghostscript.run_gs(
            ["-sDEVICE=tiffsep", f"-r{dpi:g}", "-dMaxSpots=60", "-dOverprint=/simulate", "-dUseCropBox",
             f"-dFirstPage={page + 1}", f"-dLastPage={page + 1}", f"-sOutputFile={tmp}/p%03d.tif", str(pdf_path)],
            timeout=300, cancel=cancel)
        arrays: dict[str, np.ndarray] = {}
        for f in sorted(tmp.glob("p*.tif")):
            stem = f.name[:-4]
            if "(" not in stem:
                continue  # el compuesto CMYK (p001.tif) no se usa
            name = unquote(stem[stem.index("(") + 1:stem.rindex(")")])
            with Image.open(f) as im:
                arr = np.array(im.convert("L"))
            arrays[name] = (255 - arr).astype(np.uint8)
        if not arrays:
            raise UserError("Ghostscript no produjo placas para esa página.")
        order = [n for n in PROCESS if n in arrays] + sorted(n for n in arrays if n not in PROCESS)
        h, w = arrays[order[0]].shape
        plates = Plates(order, arrays, dpi, page, w, h, warns, key)
        if use_cache:
            _save_cache(plates)
        return plates
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- vista compuesta simulada
def _ink_def(name: str, meta: dict) -> dict:
    """Lab y opacidad de una tinta para la simulación. `meta`: {nombre: {"lab", "tipo", "orden", "opacity"}}."""
    m = meta.get(name) or {}
    kind = m.get("tipo", "spot")
    lab = m.get("lab")
    if lab is None:
        ref = {i.name: i for i in inkmod.builtin_library().inks}.get(name)
        lab = ref.lab if ref and ref.lab else (50.0, 0.0, 0.0)
    opacity = m.get("opacity", 1.0 if kind == "white" else 0.0)
    return {"lab": tuple(lab), "opacity": opacity, "kind": kind, "order": m.get("orden")}


def compose(plates: Plates, meta: dict | None = None, visible: set | None = None, substrate_lab=inkmod.PAPER_PC1,
            n: float = 1.7, scale: float = 1.0) -> np.ndarray:
    """PNG sRGB simulado de la combinación de placas (modelo de mezcla orientativo). `scale` < 1 reduce antes de mezclar."""
    meta = meta or {}
    names = [x for x in plates.names if (visible is None or x in visible) and not plates.empty(x)]
    defs = {x: _ink_def(x, meta) for x in names}
    # orden de impresión: opacas (blanco) primero, luego proceso C M Y K y por último las directas
    def rank(x):
        d = defs[x]
        if d["order"] is not None:
            return (1, d["order"])
        if d["opacity"] >= 0.5:
            return (0, 0)
        return (1, PROCESS.index(x) if x in PROCESS else 10)
    names.sort(key=rank)
    h, w = plates.height, plates.width
    if scale != 1.0:
        w, h = max(1, int(w * scale)), max(1, int(h * scale))
    if not names:
        return np.full((h, w, 3), np.round(cs.lab_to_srgb(substrate_lab) * 255), np.uint8)
    covs = []
    for x in names:
        a = plates.arrays[x]
        if scale != 1.0:
            a = cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA)
        covs.append(a.astype(np.float32) / 255.0)
    rgb = cs.mix_inks(substrate_lab, [{"lab": defs[x]["lab"], "opacity": defs[x]["opacity"]} for x in names], covs,
                      n=n, output="srgb")
    return np.clip(np.rint(rgb * 255), 0, 255).astype(np.uint8)
