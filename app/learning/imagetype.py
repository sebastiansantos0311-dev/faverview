"""Clasifica el arte del cliente con reglas simples (sin IA): exportado, whatsapp, foto, escaneo o captura."""
from pathlib import Path

from PIL import Image

WHATSAPP_MAX_SIDES = {1600, 1280, 1024, 960, 800, 640}
SCREEN_SIZES = {(1920, 1080), (1366, 768), (2560, 1440), (1536, 864), (1440, 900), (1280, 720), (3840, 2160),
                (1080, 1920), (1170, 2532), (1284, 2778), (1080, 2340), (1080, 2400), (750, 1334), (828, 1792),
                (1125, 2436), (1242, 2688), (1179, 2556), (1290, 2796)}
EXIF_MAKE, EXIF_MODEL, EXIF_SOFTWARE = 0x010F, 0x0110, 0x0131


def _jpeg_quality(im: Image.Image) -> float | None:
    """Calidad JPEG aproximada a partir de la tabla de cuantización de luminancia."""
    q = getattr(im, "quantization", None)
    if not q:
        return None
    table = q.get(0)
    if not table:
        return None
    avg = sum(table) / len(table)
    scale = avg / 57.6 * 100  # la tabla estándar (calidad 50) promedia 57,6
    q_est = (200 - scale) / 2 if scale <= 100 else 5000 / scale
    return max(1.0, min(100.0, q_est))


def classify(client_path, framed: bool = False, illumination_fixed: bool = False, perspective: bool = False) -> str:
    """Devuelve 'exportado' | 'whatsapp' | 'foto' | 'escaneo' | 'captura'."""
    p = Path(client_path)
    ext = p.suffix.lower()
    try:
        with Image.open(p) as im:
            w, h = im.size
            exif = im.getexif() if hasattr(im, "getexif") else {}
            camera = bool(exif.get(EXIF_MAKE) or exif.get(EXIF_MODEL))
            software = str(exif.get(EXIF_SOFTWARE, "")).lower()
            dpi = im.info.get("dpi", (0, 0))[0] or 0
            fmt = (im.format or "").upper()
            q = _jpeg_quality(im) if fmt == "JPEG" else None
    except Exception:
        return "exportado"

    if framed or (w, h) in SCREEN_SIZES or (h, w) in SCREEN_SIZES:
        return "captura"
    if camera or perspective or illumination_fixed:
        return "foto"
    if "scan" in software or ext in (".tif", ".tiff") or (dpi and 150 <= dpi <= 600 and dpi not in (72, 96)
                                                           and fmt in ("JPEG", "TIFF", "PNG")):
        return "escaneo"
    if fmt == "JPEG" and max(w, h) in WHATSAPP_MAX_SIDES and (q is None or q <= 85):
        return "whatsapp"
    return "exportado"
