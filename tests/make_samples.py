"""Genera datos sintéticos en samples/: diseno.pdf, cliente_ok.png y cliente_errores.png."""
import io
import sys
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def make_pdf(path: Path, price="Precio 10.000", paragraph_drop=None, rect=(0.10, 0.45, 0.80),
             logo=True, title_size=34, title="Oferta de Verano") -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text((50, 90), title, fontsize=title_size, fontname="hebo", color=(0.1, 0.1, 0.1))
    page.insert_text((50, 160), price, fontsize=26, fontname="helv", color=(0.8, 0.0, 0.0))
    para = ["Aprovecha nuestras ofertas especiales de temporada",
            "en todos los productos de la tienda hasta agotar stock."]
    if paragraph_drop:
        para = [ln.replace(paragraph_drop + " ", "") for ln in para]
    for i, line in enumerate(para):
        page.insert_text((50, 210 + i * 20), line, fontsize=13, fontname="helv", color=(0, 0, 0))
    page.draw_rect(pymupdf.Rect(50, 300, 300, 420), color=None, fill=rect)
    page.insert_text((70, 370), "Descuento hasta 40%", fontsize=18, fontname="hebo", color=(1, 1, 1))
    if logo:
        page.draw_circle((480, 120), 45, color=None, fill=(0.0, 0.4, 0.8))
        page.draw_circle((480, 120), 18, color=None, fill=(1, 1, 1))
    page.insert_text((50, 780), "www.tiendaejemplo.com  |  Ventas: 555-1234", fontsize=11,
                     fontname="helv", color=(0.3, 0.3, 0.3))
    doc.save(path)
    doc.close()


def render(path: Path, dpi=200) -> np.ndarray:
    with pymupdf.open(path) as doc:
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
        return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()


def jpeg_roundtrip(img: np.ndarray, quality=85) -> np.ndarray:
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "JPEG", quality=quality)
    return np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))


def rotate(img: np.ndarray, deg: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def main(out: Path = SAMPLES) -> None:
    out.mkdir(parents=True, exist_ok=True)
    design = out / "diseno.pdf"
    make_pdf(design)
    Image.fromarray(jpeg_roundtrip(render(design))).save(out / "cliente_ok.png")

    tmp = out / "_errores.pdf"
    make_pdf(tmp, price="Precio 12.000", paragraph_drop="especiales", rect=(0.85, 0.45, 0.10),
             logo=False, title_size=42)
    Image.fromarray(jpeg_roundtrip(rotate(render(tmp), 2.0))).save(out / "cliente_errores.png")
    tmp.unlink(missing_ok=True)
    print("Muestras generadas en", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLES)
