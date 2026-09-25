import numpy as np
import pytest
from PIL import Image

from app.loaders import FileError, extract_pdf_layout, load_as_image, page_count, validate_file
from make_samples import make_pdf


def test_png_transparency_is_flattened_on_white(tmp_path):
    p = tmp_path / "t.png"
    Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(p)
    img = load_as_image(p)
    assert img.shape == (20, 20, 3) and img.min() == 255


def test_exif_orientation_is_applied(tmp_path):
    p = tmp_path / "e.jpg"
    im = Image.new("RGB", (40, 20), (200, 10, 10))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotar 90°
    im.save(p, exif=exif)
    assert load_as_image(p).shape[:2] == (40, 20)


def test_pdf_render_and_layout(tmp_path):
    p = tmp_path / "d.pdf"
    make_pdf(p)
    img = load_as_image(p, dpi=100)
    assert img.shape[2] == 3 and abs(img.shape[1] - 595 / 72 * 100) <= 1
    spans = extract_pdf_layout(p, dpi=100)
    words = [w for s in spans for w, _ in s.words]
    assert "Precio" in words and "10.000" in words
    price = next(s for s in spans if "Precio" in s.text)
    assert price.color == "#CC0000" and round(price.size) == 26
    assert page_count(p) == 1


def test_invalid_files(tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("hola")
    with pytest.raises(FileError, match="Formato no admitido"):
        validate_file(bad)
    corrupt = tmp_path / "c.pdf"
    corrupt.write_bytes(b"no soy un pdf")
    with pytest.raises(FileError):
        load_as_image(corrupt)
