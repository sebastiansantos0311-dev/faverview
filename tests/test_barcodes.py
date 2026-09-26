"""Códigos de barras (S6): generar → verificar, validaciones y avisos."""
import io
import zipfile

import cv2
import numpy as np
import pymupdf
import pytest

from app.core.errors import UserError
from app.modules.barcodes import generate as g
from app.modules.barcodes import gs1, verify as v

CASOS = [("ean13", "590123412345", "5901234123457"), ("ean8", "9638507", "96385074"), ("upca", "03600029145", "0036000291452"),
         ("upce", "0425261", "0042100005264"), ("itf14", "1540014128876", "15400141288763"), ("code128", "Hola123", "Hola123"),
         ("gs1_128", "(01)09501101530003(17)250101(10)AB12", "(01)09501101530003(17)250101(10)AB12"), ("code39", "ABC-123", "ABC-123"),
         ("qr", "https://faverview.local", "https://faverview.local"), ("datamatrix", "Hola", "Hola"),
         ("gs1_datamatrix", "(01)09501101530003(17)250101(10)AB12", "(01)09501101530003(17)250101(10)AB12"),
         ("databar", "09501101530003", "(01)09501101530003")]


@pytest.mark.parametrize("tipo,dato,esperado", CASOS)
def test_generar_y_verificar(tipo, dato, esperado, tmp_path):
    lay = g.layout(tipo, dato)
    (tmp_path / "c.pdf").write_bytes(g.to_pdf(lay))
    r = v.verify(tmp_path / "c.pdf", 600)
    assert r["codigos"], r
    assert r["codigos"][0]["contenido"] == esperado
    assert "no es una verificación certificada" in r["codigos"][0]["grado"]["nota"]


def test_digito_de_control():
    assert gs1.check_digit("590123412345") == 7
    with pytest.raises(UserError):
        g.normalize("ean13", "5901234123458")
    assert g.normalize("ean13", "5901234123457")[0] == "5901234123457"
    with pytest.raises(UserError):
        g.normalize("ean13", "123")


def test_gs1_ai_validacion():
    gs1.parse_ais("(01)09501101530003(17)250101(10)AB12")
    for malo in ("(01)09501101530004", "(17)251301", "(99)123", "sin parentesis", "(01)123"):
        with pytest.raises(UserError):
            gs1.parse_ais(malo)


def test_magnificacion_y_medicion(tmp_path):
    lay = g.layout("ean13", "5901234123457", magnificacion=1.2)
    assert abs(lay.width - 37.29 * 1.2) < 0.2
    (tmp_path / "m.pdf").write_bytes(g.to_pdf(lay))
    r = v.verify(tmp_path / "m.pdf", 600)["codigos"][0]
    assert abs(r["magnificacion_pct"] - 120) < 2


def test_limites_de_magnificacion_y_bwr():
    with pytest.raises(UserError):
        g.layout("ean13", "5901234123457", magnificacion=0.5)
    with pytest.raises(UserError):
        g.layout("ean13", "5901234123457", bwr_mm=0.5)
    assert any("BWR" in w for w in g.layout("ean13", "5901234123457", bwr_mm=0.03).warnings)


def test_zona_de_silencio_corta(tmp_path):
    lay = g.layout("ean13", "5901234123457")
    # se recorta el silencio del PDF dibujando el símbolo casi al borde
    lay.rects = [(x - 8.0, y, w, h) for x, y, w, h in lay.rects]
    lay.texts = []
    lay.width -= 8.0
    (tmp_path / "s.pdf").write_bytes(g.to_pdf(lay))
    r = v.verify(tmp_path / "s.pdf", 600)
    if r["codigos"]:
        assert any("silencio" in a["mensaje"] for a in r["codigos"][0]["avisos"])


def test_rojo_sobre_blanco_es_error(tmp_path):
    lay = g.layout("code128", "Hola123", ink_lab=(50.0, 70.0, 55.0))
    assert any("luz roja" in w for w in lay.warnings)
    (tmp_path / "r.pdf").write_bytes(g.to_pdf(lay, "Rojo", (50.0, 70.0, 55.0)))
    r = v.verify(tmp_path / "r.pdf", 600)
    if r["codigos"]:
        assert any("luz roja" in a["mensaje"] for a in r["codigos"][0]["avisos"])


def test_direccion_de_impresion(tmp_path):
    (tmp_path / "d.pdf").write_bytes(g.to_pdf(g.layout("code128", "Hola123")))
    r = v.verify(tmp_path / "d.pdf", 600, direccion_impresion="vertical")["codigos"][0]
    assert any("paralelas" in a["mensaje"] for a in r["avisos"])
    r2 = v.verify(tmp_path / "d.pdf", 600, direccion_impresion="horizontal")["codigos"][0]
    assert not any("paralelas" in a["mensaje"] for a in r2["avisos"])


def test_tinta_directa_y_svg_vectorial(tmp_path):
    lay = g.layout("ean13", "5901234123457", ink_lab=(20.0, 5.0, -25.0))
    pdf = g.to_pdf(lay, "Azul marino", (20.0, 5.0, -25.0))
    from app.modules.separate.pdf_inks import read_inventory
    (tmp_path / "t.pdf").write_bytes(pdf)
    assert [i.name for i in read_inventory(tmp_path / "t.pdf").inks] == ["Azul_marino"]
    svg = g.to_svg(lay)
    assert svg.startswith("<svg") and "<image" not in svg


def test_verificar_imagen_raster(tmp_path):
    lay = g.layout("qr", "hola mundo")
    with pymupdf.open(stream=g.to_pdf(lay), filetype="pdf") as d:
        pix = d[0].get_pixmap(dpi=300)
    pix.save(str(tmp_path / "q.png"))
    assert v.verify(tmp_path / "q.png")["codigos"][0]["contenido"] == "hola mundo"


def test_sin_codigos(tmp_path):
    cv2.imwrite(str(tmp_path / "b.png"), np.full((100, 100), 255, np.uint8))
    assert v.verify(tmp_path / "b.png")["codigos"] == []


def test_api(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/codigos/generar", json={"tipo": "ean13", "datos": "590123412345"})
    assert r.status_code == 200 and "<svg" in r.json()["svg"]
    assert c.post("/api/codigos/generar", json={"tipo": "ean13", "datos": "5901234123458"}).status_code == 400
    pdf = c.post("/api/codigos/generar", json={"tipo": "qr", "datos": "hola", "formato": "pdf"})
    assert pdf.content.startswith(b"%PDF")
    csv_bytes = b"tipo;datos;nombre\nean13;590123412345;uno\ncode128;Hola;dos\nean13;123;malo\n"
    z = c.post("/api/codigos/lote", files={"file": ("l.csv", csv_bytes, "text/csv")})
    assert z.status_code == 200 and z.headers["X-Errores"] == "1"
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "hoja.pdf" in names and "errores.txt" in names and len([n for n in names if n.endswith(".pdf")]) == 3
    (tmp_path / "e.pdf").write_bytes(g.to_pdf(g.layout("ean13", "5901234123457")))
    with open(tmp_path / "e.pdf", "rb") as f:
        rv = c.post("/api/codigos/verificar", files={"file": ("e.pdf", f, "application/pdf")}, data={"dpi": "600"})
    assert rv.json()["codigos"][0]["contenido"] == "5901234123457"
