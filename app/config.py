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
DATOS_DIR = Path(os.environ.get("FAVERVIEW_DATOS") or BASE_DIR / "datos_locales")  # casos reales y aprendizaje: NUNCA a git

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
    "ocr_mode": "guiado",  # "guiado" (por línea, guiado por el PDF) | "pagina" (página completa)
    "spell_lang": "es_CO",
    "cmyk_profile": "",  # ruta a un perfil ICC CMYK por defecto (vacío: conversión estándar)
    "learning_enabled": True,
    "learning_min_confusion_count": 3,
    "learning_autotune_every": 5,
    "update_check": True,
    "weights": {"visual": 0.30, "text": 0.35, "color": 0.15, "spelling": 0.10, "font": 0.10},
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    # modelo de OCR re-entrenado con los casos revisados (Fase 7, nivel 4), si está activado
    modelos = DATOS_DIR / "aprendizaje" / "modelos"
    if (modelos / "activo.txt").exists() and (modelos / "runtime" / "spa_fv.traineddata").exists() \
            and cfg.get("learning_enabled", True) and "spa_fv" not in cfg["ocr_lang"]:
        cfg["tessdata_dir"] = str(modelos / "runtime")
        cfg["ocr_lang"] = "spa_fv+" + cfg["ocr_lang"]
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


def setup_tesseract(cfg: dict | None = None) -> str | None:
    """Configura pytesseract y TESSDATA_PREFIX. Devuelve la ruta o None."""
    cfg = cfg or load_config()
    tessdata = (BASE_DIR / cfg["tessdata_dir"]).resolve()  # (si es absoluta, `/` la respeta)
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
