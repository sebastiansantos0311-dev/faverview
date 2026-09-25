"""Carga de PDF/imágenes a arrays RGB y extracción del texto vectorial del PDF."""
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageOps

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}
MAX_SIDE_PX = 6000
Image.MAX_IMAGE_PIXELS = 300_000_000


class FileError(ValueError):
    """Error de archivo con mensaje en español para el usuario."""


@dataclass
class TextSpan:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 en píxeles
    font: str
    size: float  # puntos
    color: str  # #RRGGBB
    flags: int
    words: list[tuple[str, tuple[float, float, float, float]]] = field(default_factory=list)

    @property
    def bold(self) -> bool:
        return bool(self.flags & 16) or "bold" in self.font.lower()

    @property
    def italic(self) -> bool:
        f = self.font.lower()
        return bool(self.flags & 2) or "italic" in f or "oblique" in f


def is_pdf(path) -> bool:
    return Path(path).suffix.lower() == ".pdf"


def validate_file(path, max_mb: float = 50) -> None:
    p = Path(path)
    if not p.exists():
        raise FileError("No se encontró el archivo.")
    if p.suffix.lower() not in ALLOWED_EXT:
        raise FileError(
            f"Formato no admitido ({p.suffix or 'sin extensión'}). Usa JPG, PNG, WEBP, BMP, TIFF o PDF."
        )
    if p.stat().st_size > max_mb * 1024 * 1024:
        raise FileError(f"El archivo supera el máximo de {max_mb} MB.")
    if p.stat().st_size == 0:
        raise FileError("El archivo está vacío.")


def page_count(path) -> int:
    p = Path(path)
    try:
        if is_pdf(p):
            with pymupdf.open(p) as doc:
                return max(1, doc.page_count)
        if p.suffix.lower() in (".tif", ".tiff"):
            with Image.open(p) as im:
                return max(1, getattr(im, "n_frames", 1))
    except Exception as e:
        raise FileError(f"No se pudo leer el archivo: {e}")
    return 1


def _effective_dpi(page, dpi: float) -> float:
    longest = max(page.rect.width, page.rect.height) / 72.0 * dpi
    if longest > MAX_SIDE_PX:
        return dpi * MAX_SIDE_PX / longest
    return dpi


def _open_pdf_page(path, page_index: int):
    try:
        doc = pymupdf.open(path)
    except Exception:
        raise FileError("El PDF está dañado o no se puede abrir.")
    if doc.needs_pass:
        doc.close()
        raise FileError("El PDF está protegido con contraseña.")
    if doc.page_count == 0:
        doc.close()
        raise FileError("El PDF no tiene páginas.")
    if not 0 <= page_index < doc.page_count:
        doc.close()
        raise FileError(f"La página {page_index + 1} no existe en el PDF.")
    return doc, doc[page_index]


def load_as_image(path, dpi: float = 200, page: int = 0) -> np.ndarray:
    """Devuelve la imagen RGB (uint8) del archivo (página `page`, base 0)."""
    p = Path(path)
    if is_pdf(p):
        doc, pg = _open_pdf_page(p, page)
        try:
            s = _effective_dpi(pg, dpi) / 72.0
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            return arr[:, :, :3].copy()
        finally:
            doc.close()
    try:
        with Image.open(p) as im:
            if getattr(im, "n_frames", 1) > 1:
                im.seek(min(page, im.n_frames - 1))
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                im = Image.alpha_composite(bg, rgba).convert("RGB")
            elif im.mode in ("I;16", "I"):
                a = np.array(im, dtype=np.float32)
                a = (a / max(a.max(), 1) * 255).astype(np.uint8)
                im = Image.fromarray(a).convert("RGB")
            else:
                im = im.convert("RGB")
            return np.array(im)
    except FileError:
        raise
    except Exception:
        raise FileError("La imagen está dañada o no se puede leer.")


def _color_hex(c: int) -> str:
    return "#{:02X}{:02X}{:02X}".format((c >> 16) & 255, (c >> 8) & 255, c & 255)


def extract_pdf_layout(path, dpi: float = 200, page: int = 0) -> list[TextSpan]:
    """Spans de texto del PDF con bbox en píxeles, fuente, tamaño y color."""
    if not is_pdf(path):
        return []
    doc, pg = _open_pdf_page(path, page)
    try:
        s = _effective_dpi(pg, dpi) / 72.0
        d = pg.get_text("rawdict")
        spans: list[TextSpan] = []
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for sp in line.get("spans", []):
                    chars = sp.get("chars", [])
                    text = "".join(c["c"] for c in chars)
                    if not text.strip():
                        continue
                    words, cur, cur_box = [], "", None
                    for ch in chars:
                        if ch["c"].isspace():
                            if cur:
                                words.append((cur, tuple(v * s for v in cur_box)))
                            cur, cur_box = "", None
                            continue
                        b = ch["bbox"]
                        cur += ch["c"]
                        cur_box = list(b) if cur_box is None else [
                            min(cur_box[0], b[0]), min(cur_box[1], b[1]),
                            max(cur_box[2], b[2]), max(cur_box[3], b[3])]
                    if cur:
                        words.append((cur, tuple(v * s for v in cur_box)))
                    x0, y0, x1, y1 = (v * s for v in sp["bbox"])
                    spans.append(TextSpan(
                        text=text.strip(), bbox=(x0, y0, x1, y1), font=sp.get("font", ""),
                        size=float(sp.get("size", 0)), color=_color_hex(sp.get("color", 0)),
                        flags=int(sp.get("flags", 0)), words=words))
        return spans
    finally:
        doc.close()
