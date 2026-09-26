"""Gestión de color: CMYK y perfiles ICC → sRGB, y descripción del espacio de color de cada archivo."""
import io
import re
from pathlib import Path

import pymupdf
from PIL import Image, ImageCms

_SRGB = None


def enable_pdf_icc() -> None:
    """Activa la gestión de color de MuPDF: los PDF en CMYK se convierten a sRGB con el perfil del propio PDF."""
    try:
        pymupdf.TOOLS.set_icc(True)
    except Exception:
        pass


def _srgb_profile():
    global _SRGB
    if _SRGB is None:
        _SRGB = ImageCms.createProfile("sRGB")
    return _SRGB


def _profile_name(profile) -> str:
    try:
        return ImageCms.getProfileDescription(profile).strip().replace("\x00", "") or "perfil ICC"
    except Exception:
        return "perfil ICC"


def image_to_srgb(im: Image.Image, cmyk_profile_path: str = "") -> tuple[Image.Image, str]:
    """Convierte una imagen PIL a RGB en sRGB. Devuelve (imagen, descripción del espacio de color original)."""
    icc = im.info.get("icc_profile")
    if im.mode == "CMYK":
        profile, name = None, None
        if icc:
            try:
                profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                name = f"CMYK ({_profile_name(profile)})"
            except Exception:
                profile = None
        if profile is None and cmyk_profile_path and Path(cmyk_profile_path).exists():
            try:
                profile = ImageCms.getOpenProfile(cmyk_profile_path)
                name = f"CMYK ({_profile_name(profile)}, perfil por defecto)"
            except Exception:
                profile = None
        if profile is not None:
            try:
                out = ImageCms.profileToProfile(im, profile, _srgb_profile(), outputMode="RGB",
                                                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
                return out, name
            except Exception:
                pass
        return im.convert("RGB"), "CMYK (sin perfil; conversión estándar, los colores pueden variar)"
    if icc:
        try:
            profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            name = _profile_name(profile)
            if "srgb" in name.lower():
                return im.convert("RGB"), "sRGB"
            src_mode = "RGB" if im.mode not in ("L", "LA") else "L"
            base = im.convert(src_mode)
            out = ImageCms.profileToProfile(base, profile, _srgb_profile(), outputMode="RGB")
            return out, f"{name} → sRGB"
        except Exception:
            pass
    return im.convert("RGB"), "sRGB"


def pdf_color_space(path, page: int = 0) -> str:
    """Espacio de color de un PDF: CMYK (con el nombre del perfil de salida si lo tiene) o sRGB."""
    try:
        with pymupdf.open(path) as doc:
            pg = doc[min(page, doc.page_count - 1)]
            cmyk = False
            for img in doc.get_page_images(pg.number, full=True):
                cs = (img[5] or "") + " " + (img[6] or "")
                if "CMYK" in cs.upper():
                    cmyk = True
            content = pg.read_contents()
            if re.search(rb"\s[kK]\s", content):
                cmyk = True
            if not cmyk:
                return "sRGB"
            name = ""
            try:
                cat = doc.pdf_catalog()
                oi = doc.xref_get_key(cat, "OutputIntents")
                m = re.search(r"(\d+) 0 R", oi[1]) if oi[0] != "null" else None
                if m:
                    ref = int(m.group(1))
                    inner = doc.xref_object(ref)
                    mm = re.search(r"/OutputConditionIdentifier\s*\((.*?)\)", inner)
                    if mm:
                        name = mm.group(1)
            except Exception:
                pass
            return f"CMYK ({name})" if name else "CMYK"
    except Exception:
        return "desconocido"
