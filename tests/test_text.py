import pytest

from app.compare_text import compare_text, compare_words, Word
from app.config import load_config, setup_tesseract
from app.loaders import extract_pdf_layout, load_as_image
from app.compare_text import layout_words
from app.spelling import check_spelling
from make_samples import make_pdf

needs_ocr = pytest.mark.skipif(setup_tesseract() is None, reason="Tesseract no instalado")


def _w(t, x=0, y=0):
    return Word(t, (x, y, x + 50, y + 20))


def test_word_changed_missing_and_extra():
    client = [_w("Precio", 0), _w("12.000", 60), _w("gratis", 120)]
    design = [_w("Precio", 0), _w("10.000", 60)]
    r = compare_words(design, client)
    subs = sorted(d.subtype for d in r.differences)
    assert subs == ["cambiada", "faltante"]
    r2 = compare_words([_w("Hola"), _w("mundo")], [_w("hola"), _w("mundo")])
    assert [d.subtype for d in r2.differences] == ["mayusculas"]


def test_spelling_flags_typos_but_not_valid_words():
    words = [_w("verrano"), _w("especiales"), _w("productos"), _w("USA"), _w("a@b.com")]
    diffs, checked = check_spelling(words)
    assert [d.found for d in diffs] == ["verrano"]
    assert checked >= 3
    # una palabra idéntica en el arte del cliente se considera válida
    assert not check_spelling([_w("verrano")], {"verrano"})[0]


@needs_ocr
def test_price_changed_detected_via_ocr(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    make_pdf(a, price="Precio 10.000")
    make_pdf(b, price="Precio 12.000")
    design_words = layout_words(extract_pdf_layout(a, 200))
    client_img = load_as_image(b, 200)
    r = compare_text(design_words, client_img, load_config())
    changed = [d for d in r.differences if d.subtype == "cambiada"]
    assert len(changed) == 1
    assert changed[0].expected == "12.000" and changed[0].found == "10.000"
