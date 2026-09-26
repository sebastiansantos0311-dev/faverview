import struct

import pikepdf
import pymupdf
import pytest

from app.core import inks, pdfinfo
from app.core.errors import UserError


@pytest.fixture()
def tintas(tmp_path, monkeypatch):
    monkeypatch.setattr(inks, "DATOS_DIR", tmp_path)
    return tmp_path


def test_name_normalization_unifies_variants():
    assert inks.normalize_name("Pantone 485C") == inks.normalize_name("PANTONE 485 C") == "PANTONE 485 C"
    assert inks.normalize_name("PMS 485 c") == "PANTONE 485 C"
    assert inks.normalize_name("P 485U") == "PANTONE 485 U"
    assert inks.normalize_name("Demo 485C") == inks.normalize_name("DEMO  485 C") == "DEMO 485 C"
    assert inks.normalize_name("  Demo   Rojo 1 ") == "DEMO ROJO 1"


def test_classify_ink_by_keywords():
    assert inks.classify_ink("Cyan") == "process" and inks.classify_ink("Negro") == "process"
    assert inks.classify_ink("Blanco opaco") == "white" and inks.classify_ink("White") == "white"
    assert inks.classify_ink("Barniz UV") == "varnish"
    assert inks.classify_ink("Troquel") == "technical" and inks.classify_ink("Dieline") == "technical"
    assert inks.classify_ink("Demo Rojo 1") == "spot"


def test_builtin_library_has_fogra_process_inks():
    lib = inks.builtin_library()
    names = [i.name for i in lib.inks]
    assert names[:4] == ["Cyan", "Magenta", "Yellow", "Black"] and lib.readonly
    assert next(i for i in lib.inks if i.name == "Cyan").lab == (55.0, -37.0, -50.0)
    assert next(i for i in lib.inks if i.kind == "white").opacity == 1.0
    assert all(i.swatch_hex().startswith("#") for i in lib.inks if i.lab)


def test_csv_import_with_decimals_and_errors():
    csv_text = "nombre,L,a,b,tipo,opacidad\nDemo Rojo 1,45.5,68.2,50.1\nDemo Blanco,95,0,-2,white,1\n"
    got = inks.import_csv(csv_text)
    assert [i.name for i in got] == ["Demo Rojo 1", "Demo Blanco"] and got[0].lab == (45.5, 68.2, 50.1)
    assert got[1].kind == "white" and got[1].opacity == 1.0
    got = inks.import_csv("Demo Azul;30,5;10,2;-55,0\n")
    assert got[0].lab == (30.5, 10.2, -55.0)
    with pytest.raises(UserError, match="ninguna tinta"):
        inks.import_csv("solo,texto\n")
    with pytest.raises(UserError):
        inks.import_csv("Malo,200,0,0\n")  # L fuera de rango


def _cxf(name="Demo Verde 2", lab=(60.0, -50.0, 30.0)):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cc:CxF xmlns:cc="http://colorexchangeformat.com/CxF3-core"><cc:Resources><cc:ObjectCollection>
<cc:Object Name="{name}" Id="1" ObjectType="Color"><cc:ColorValues><cc:ColorCIELab>
<cc:L>{lab[0]}</cc:L><cc:A>{lab[1]}</cc:A><cc:B>{lab[2]}</cc:B></cc:ColorCIELab></cc:ColorValues></cc:Object>
</cc:ObjectCollection></cc:Resources></cc:CxF>""".encode()


def test_cxf_import_and_bad_xml():
    got = inks.import_cxf(_cxf())
    assert got[0].name == "Demo Verde 2" and got[0].lab == (60.0, -50.0, 30.0) and got[0].kind == "spot"
    with pytest.raises(UserError, match="CxF"):
        inks.import_cxf(b"<no es xml")
    with pytest.raises(UserError):
        inks.import_cxf(b"<a/>")


def _ase(entries):
    body = b""
    for name, model, vals, ctype in entries:
        nm = (name + "\x00").encode("utf-16-be")
        blk = struct.pack(">H", len(name) + 1) + nm + model.encode() + struct.pack(f">{len(vals)}f", *vals) + struct.pack(">H", ctype)
        body += struct.pack(">HI", 0x0001, len(blk)) + blk
    return b"ASEF" + struct.pack(">HHI", 1, 0, len(entries)) + body


def test_ase_import_lab_cmyk_rgb():
    data = _ase([("Demo Naranja", "LAB ", (0.65, 40.0, 60.0), 1), ("Demo Cian", "CMYK", (1.0, 0.0, 0.0, 0.0), 2),
                 ("Demo Gris", "RGB ", (0.5, 0.5, 0.5), 2)])
    got = inks.import_ase(data)
    assert [i.name for i in got] == ["Demo Naranja", "Demo Cian", "Demo Gris"]
    assert got[0].lab == pytest.approx((65.0, 40.0, 60.0), abs=0.01)
    assert got[1].alt_cmyk == (1.0, 0.0, 0.0, 0.0) and got[1].lab[0] == pytest.approx(55.0, abs=1.0)
    assert got[2].lab[0] == pytest.approx(53.4, abs=1.0)
    with pytest.raises(UserError, match="ASE"):
        inks.import_ase(b"nada")
    with pytest.raises(UserError, match="dañado"):
        inks.import_ase(data[:30])


def test_import_any_dispatch_and_unknown_format():
    assert inks.import_any("a.csv", b"X,50,10,10\n")[0].source == "biblioteca:a.csv"
    with pytest.raises(UserError, match="no admitido"):
        inks.import_any("a.pdf", b"")


def test_library_save_load_delete_export(tintas):
    lib = inks.InkLibrary(name="Prendas taller", inks=[inks.Ink(name="Demo Rojo 1", lab=(45, 68, 50), source="usuario")])
    inks.save_library(lib)
    assert [x["nombre"] for x in inks.list_libraries()][1:] == ["Prendas taller"]
    assert inks.load_library("Prendas taller").inks[0].name == "Demo Rojo 1"
    assert '"Demo Rojo 1"' in inks.to_json(lib) and inks.to_csv(lib).splitlines()[1].startswith("Demo Rojo 1,45")
    with pytest.raises(UserError, match="solo lectura"):
        inks.save_library(inks.builtin_library())
    inks.delete_library("Prendas taller")
    with pytest.raises(UserError):
        inks.load_library("Prendas taller")


def test_dedupe_and_lookup():
    a = inks.Ink(name="Demo 485C", lab=None); b = inks.Ink(name="DEMO 485 C", lab=(50, 60, 40))
    out = inks.dedupe([a, b, inks.Ink(name="Otra", lab=(1, 2, 3))])
    assert len(out) == 2 and out[0].lab == (50, 60, 40)
    lib = inks.InkLibrary(name="x", inks=[b])
    assert inks.lookup("demo 485c", [lib]) is b and inks.lookup("nada", [lib]) is None


# ------------------------------------------------------------------------------------- pdfinfo
def _pdf(tmp_path, with_trim=True, transparent=False, layers=False, pdfx=False):
    doc = pymupdf.open()
    p = doc.new_page(width=300, height=200)
    p.insert_text((20, 40), "Hola")
    if with_trim:
        p.set_trimbox(pymupdf.Rect(10, 10, 290, 190))
        p.set_bleedbox(pymupdf.Rect(2, 2, 298, 198))
    path = tmp_path / "t.pdf"
    doc.save(path)
    doc.close()
    pdf = pikepdf.open(path, allow_overwriting_input=True)
    if transparent:
        pdf.pages[0].obj["/Group"] = pikepdf.Dictionary(S=pikepdf.Name("/Transparency"), CS=pikepdf.Name("/DeviceCMYK"))
    if pdfx:
        pdf.docinfo["/GTS_PDFXVersion"] = pikepdf.String("PDF/X-4")
        pdf.Root["/OutputIntents"] = pikepdf.Array([pikepdf.Dictionary(
            S=pikepdf.Name("/GTS_PDFX"), OutputConditionIdentifier=pikepdf.String("FOGRA51"),
            OutputCondition=pikepdf.String("PSO Coated v3"), RegistryName=pikepdf.String("http://www.color.org"))])
    if layers:
        g1 = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name("/OCG"), Name=pikepdf.String("Troquel")))
        g2 = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name("/OCG"), Name=pikepdf.String("Arte")))
        pdf.Root["/OCProperties"] = pikepdf.Dictionary(OCGs=pikepdf.Array([g1, g2]), D=pikepdf.Dictionary(OFF=pikepdf.Array([g1])))
    pdf.save(path)
    pdf.close()
    return path


def test_pdfinfo_boxes_in_mm_and_bleed(tmp_path):
    info = pdfinfo.read_pdf_info(_pdf(tmp_path))
    b = info.boxes[0]
    assert info.pages == 1 and b.has_trim and b.has_bleed
    d = b.to_dict()
    assert d["media_mm"] == (105.83, 70.56) and d["trim_mm"] == (98.78, 63.5)
    assert d["sangrado_mm"]["izq"] == pytest.approx(2.82, abs=0.01)     # 8 pt entre trim y bleed
    assert pdfinfo.page_size_mm(_pdf(tmp_path, with_trim=False)) == (105.83, 70.56)


def test_pdfinfo_intents_pdfx_transparency_layers(tmp_path):
    info = pdfinfo.read_pdf_info(_pdf(tmp_path, transparent=True, layers=True, pdfx=True))
    assert info.has_transparency and info.transparency_pages == [1]
    assert info.pdfx_version == "PDF/X-4"
    assert info.output_intents[0]["condicion"] == "FOGRA51" and info.output_intents[0]["tipo"] == "GTS_PDFX"
    assert {l["nombre"]: l["visible"] for l in info.layers} == {"Troquel": False, "Arte": True}
    clean = pdfinfo.read_pdf_info(_pdf(tmp_path))
    assert not clean.has_transparency and clean.pdfx_version is None and clean.layers == [] and clean.output_intents == []


def test_pdfinfo_errors_are_spanish(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_bytes(b"no pdf")
    with pytest.raises(UserError, match="dañado"):
        pdfinfo.read_pdf_info(bad)
