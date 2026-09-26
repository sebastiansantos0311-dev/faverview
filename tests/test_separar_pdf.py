"""Separar colores → PDF (S2): inventario, placas, análisis, edición, exportación y API."""
import io
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.separate import analysis, pdf_edit
from app.modules.separate.pdf_inks import read_inventory
from app.modules.separate.pdf_render import render_plates

SEP = Path(__file__).parent / "sinteticos_sep"
pytestmark = pytest.mark.skipif(not (SEP / "completo.pdf").exists(), reason="faltan los PDF sintéticos")


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _need_gs():
    from app.core import ghostscript
    if not ghostscript.available():
        pytest.skip("Ghostscript no instalado")


def test_inventario_exacto():
    inv = read_inventory(SEP / "completo.pdf").to_dict()
    nombres = {i["nombre"] for i in inv["tintas"]}
    assert {"Demo Rojo 1", "Demo Azul", "Demo Verde", "Blanco"} <= nombres
    assert inv["duplicadas"]
    assert "Demo Sin Usar" in inv["no_usadas"]


def test_limpio_sin_hallazgos():
    _need_gs()
    pdf = SEP / "limpio.pdf"
    plates = render_plates(pdf, 0, 100, use_cache=False)
    inv = read_inventory(pdf)
    assert analysis.run_checks(plates, pdf, 0, inv) == []


def test_completo_dispara_cada_chequeo():
    _need_gs()
    pdf = SEP / "completo.pdf"
    plates = render_plates(pdf, 0, 150, use_cache=False)
    ids = {f.id for f in analysis.run_checks(plates, pdf, 0, read_inventory(pdf))}
    assert {"tac", "negro_enriquecido", "texto_pequeno_multitinta"} <= ids


def test_parches_cobertura():
    _need_gs()
    p = render_plates(SEP / "parches.pdf", 0, 150, use_cache=False)
    assert "Cyan" in p.names and "Demo Rojo 1" in p.names
    vals = sorted({round(v / 255 * 100) for v in np.unique(p.arrays["Cyan"])})
    assert {25, 50, 75, 100} <= {min(vals, key=lambda x: abs(x - t)) for t in (25, 50, 75, 100)}
    assert abs(p.pct("Cyan") - p.pct("Demo Rojo 1")) < 1.0


def test_sonda_y_tac():
    _need_gs()
    pdf = SEP / "completo.pdf"
    p = render_plates(pdf, 0, 100, use_cache=False)
    tac = analysis.tac_map(p)
    assert tac.max() >= 390
    x, y, w, h = max((r["bbox"] for r in analysis.tac_regions(tac, 330, p.dpi)), key=lambda b: b[2] * b[3])
    assert analysis.probe(p, x + w // 2, y + h // 2)["tac"] >= 330


def test_edicion_renombra_y_no_toca_original(tmp_path):
    _need_gs()
    src = SEP / "completo.pdf"
    before = src.read_bytes()
    dst = tmp_path / "ed.pdf"
    r = pdf_edit.apply_edits(src, dst, rename={"Demo 485C": "DEMO 485 C"}, delete_unused=True)
    assert r["renombradas"] == 1 and r["eliminadas"] == 1
    assert not read_inventory(dst).to_dict()["duplicadas"]
    assert src.read_bytes() == before
    v = pdf_edit.verify_untouched(src, dst, {"Demo 485C"})
    assert v["maximo"] < 0.01


def test_convertir_a_proceso(tmp_path):
    _need_gs()
    dst = tmp_path / "c.pdf"
    r = pdf_edit.apply_edits(SEP / "completo.pdf", dst, convert=["Demo Rojo 1"])
    assert r["convertidas"] == 1
    assert "Demo Rojo 1" not in render_plates(dst, 0, 100, use_cache=False).names


def test_no_sobrescribe_original():
    from app.core.errors import UserError
    with pytest.raises(UserError):
        pdf_edit.apply_edits(SEP / "completo.pdf", SEP / "completo.pdf")


def test_api_flujo(client):
    _need_gs()
    with open(SEP / "completo.pdf", "rb") as f:
        r = client.post("/api/separar/pdf", files={"file": ("completo.pdf", f, "application/pdf")})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    a = client.post(f"/api/separar/pdf/{jid}/analizar?dpi=100").json()["job_id"]
    for _ in range(100):
        st = client.get(f"/api/jobs/{a}").json()
        if st["status"] != "running":
            break
        time.sleep(0.3)
    assert st["status"] == "done", st
    res = st["result"]
    assert any(h["id"] == "tac" for h in res["hallazgos"])
    tipos = {p["nombre"]: p["tipo"] for p in res["placas"]}
    assert {tipos[n] for n in ("Cyan", "Magenta", "Yellow", "Black")} == {"process"}
    assert client.get(f"/api/separar/pdf/{jid}/composicion.png?dpi=100").headers["content-type"] == "image/png"
    assert client.get(f"/api/separar/pdf/{jid}/placa.png?nombre=Cyan&dpi=100").status_code == 200
    assert client.get(f"/api/separar/pdf/{jid}/sonda?x=10&y=10&dpi=100").json()["fuera"] is False
    z = client.post(f"/api/separar/pdf/{jid}/exportar", json={"formato": "tiff1", "dpi": 100})
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "Cyan.tif" in names and "informe_separaciones.csv" in names
    e = client.post(f"/api/separar/pdf/{jid}/editar", json={"eliminar_no_usadas": True})
    assert e.status_code == 200 and client.get(f"/api/separar/pdf/{jid}/descargar").status_code == 200
    assert client.post("/api/separar/pdf", files={"file": ("a.txt", b"x")}).status_code == 400


def test_rendimiento_a4_150dpi():
    _need_gs()
    t = time.time()
    render_plates(SEP / "completo.pdf", 0, 150, use_cache=False)
    assert time.time() - t < 5
