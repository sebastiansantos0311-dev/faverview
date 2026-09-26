"""Detección de herramientas externas (Ghostscript, Tesseract) para /api/status y los avisos de la interfaz."""
import subprocess

from app.config import find_tesseract, load_config
from app.core import ghostscript


def _tesseract_version(path: str | None) -> str | None:
    if not path:
        return None
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
        return (r.stdout or r.stderr).splitlines()[0].strip()
    except Exception:
        return None


def status() -> dict:
    gs = ghostscript.find_gs()
    tess = find_tesseract(load_config())
    return {
        "ghostscript": {"ok": gs is not None, "ruta": gs, "version": ghostscript.gs_version(gs) if gs else None,
                        "ayuda": None if gs else ghostscript.INSTALL_HINT},
        "tesseract": {"ok": tess is not None, "ruta": tess, "version": _tesseract_version(tess),
                      "ayuda": None if tess else "Instálalo con: winget install UB-Mannheim.TesseractOCR"},
    }


# módulos de la suite y qué herramienta necesitan (para desactivarlos con un aviso en la interfaz)
MODULOS = {
    "comparar": {"nombre": "Comparar", "requiere": ["tesseract"]},
    "separar": {"nombre": "Separar colores", "requiere": ["ghostscript"]},
    "vectorizar": {"nombre": "Vectorizar", "requiere": []},
    "preflight": {"nombre": "Preflight", "requiere": []},
    "codigos": {"nombre": "Códigos de barras", "requiere": ["ghostscript"]},
    "herramientas": {"nombre": "Herramientas", "requiere": []},
    "automatizar": {"nombre": "Automatizar", "requiere": []},
}
