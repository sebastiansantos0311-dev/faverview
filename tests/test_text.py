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


def test_no_font_false_positive_on_sample_errors():
    """Regresión F6.2: cliente_errores.png tiene otros errores pero NINGÚN cambio de fuente."""
    from app.pipeline import run_comparison
    r = run_comparison("t_fontreg", "samples/cliente_errores.png", "samples/diseno.pdf", persist=False,
                       out_dir=__import__("pathlib").Path(__import__("tempfile").mkdtemp()))
    assert not [d for d in r.differences if d.category == "font"]


@needs_ocr
def test_font_size_change_is_detected(tmp_path):
    from app.pipeline import run_comparison
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    t = "Gran Oferta Especial Verano"
    make_pdf(a, title_size=30, title=t)
    make_pdf(b, title_size=36, title=t)
    r = run_comparison("t_font2", b, a, persist=False, out_dir=tmp_path / "o")
    assert [d for d in r.differences if d.category == "font"]


def test_hunspell_tilde_and_valid_forms():
    diffs, _ = check_spelling([_w("informacion"), _w("jardineria"), _w("verrano"), _w("comunícate"), _w("Bogotá"),
                               _w("productos"), _w("aprovecha")])
    by = {d.found: d for d in diffs}
    assert set(by) == {"informacion", "jardineria", "verrano"}
    assert by["informacion"].subtype == "tilde_faltante" and by["informacion"].suggestions == ["información"]
    assert by["verrano"].subtype == "ortografia"


@needs_ocr
def test_guided_ocr_finds_price_and_removed_word():
    from app.align import align_images
    from app.ocr_guided import compare_guided
    d = load_as_image("samples/diseno.pdf", 200)
    c = load_as_image("samples/cliente_errores.png", 200)
    al = align_images(d, c)
    tr = compare_guided(extract_pdf_layout("samples/diseno.pdf", 200), al.aligned_client, load_config(),
                        al.alignment_quality)
    kinds = sorted((x.subtype, x.found or x.expected) for x in tr.differences)
    assert ("cambiada", "10.000") in kinds and ("sobrante", "especiales") in kinds and len(kinds) == 2


@needs_ocr
def test_ocr_accent_loss_is_not_reported_but_missing_tilde_is():
    from app.compare_text import compare_words
    w = lambda t: Word(t, (0, 0, 50, 20), 90.0)
    # el diseño TIENE la tilde y el OCR la perdió: no es error del diseño
    assert not compare_words([w("Visítanos")], [w("Visitanos")]).differences
    # el diseño NO tiene la tilde y el cliente sí: error real
    r = compare_words([w("Reunion")], [w("Reunión")])
    assert [d.subtype for d in r.differences] == ["cambiada"]
