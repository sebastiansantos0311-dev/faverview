import json
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):  # versión portable (PyInstaller): archivos junto al .exe
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
RESULTS_DIR = DATA_DIR / "results"
WEB_DIR = BASE_DIR / "web"
DATOS_DIR = BASE_DIR / "datos_locales"  # casos reales y aprendizaje: NUNCA va a git

_TESS_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]

DEFAULTS = {
    "tesseract_cmd": "",
    "tessdata_dir": "tools/tessdata",
    "ocr_lang": "spa+eng",
    "render_dpi": 200,
    "ssim_threshold": 0.85,
    "pixel_diff_threshold": 40,
    "min_region_area": 150,
    "delta_e_tolerance": 10,
    "text_similarity_min": 0.85,
    "font_size_tolerance_pct": 12,
    "max_upload_mb": 50,
    "weights": {"visual": 0.30, "text": 0.35, "color": 0.15, "spelling": 0.10, "font": 0.10},
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    return cfg


def find_tesseract(cfg: dict) -> str | None:
    bundled = BASE_DIR / "tools" / "tesseract" / "tesseract.exe"
    if bundled.exists():
        return str(bundled)
    if cfg.get("tesseract_cmd") and Path(cfg["tesseract_cmd"]).exists():
        return cfg["tesseract_cmd"]
    import shutil
    found = shutil.which("tesseract")
    if found:
        return found
    for p in _TESS_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def setup_tesseract() -> str | None:
    """Configura pytesseract y TESSDATA_PREFIX. Devuelve la ruta o None."""
    cfg = load_config()
    tessdata = (BASE_DIR / cfg["tessdata_dir"]).resolve()
    if tessdata.exists():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)
    cmd = find_tesseract(cfg)
    if cmd:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
    return cmd


CFG = load_config()
for d in (UPLOADS_DIR, RESULTS_DIR):
    d.mkdir(parents=True, exist_ok=True)
