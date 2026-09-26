"""Preflight (S6): reglas por perfil, correcciones seguras, reporte y API."""
import io
import time
import unicodedata
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core import ghostscript
from app.main import app
from app.modules.preflight import engine, fixes, report
from bench.synth_separations import Builder


def problem_pdf(path: Path) -> Path:
    """PDF con: fuente no incrustada, imagen de baja resolución, JPEG muy comprimido, anotación, sin TrimBox/BleedBox."""
    doc = pymupdf.open()
    page = doc.new_page(width=283, height=283)                 # 100 × 100 mm
    page.insert_text((20, 40), "Texto de prueba", fontname="helv", fontsize=14)
    small = Image.new("RGB", (20, 20), (200, 30, 30))
    buf = io.BytesIO()
    small.save(buf, "PNG")
    page.insert_image(pymupdf.Rect(20, 60, 120, 160), stream=buf.getvalue())         # 20 px en 100 pt → ≈ 14 ppi
    noisy = Image.effect_noise((400, 400), 80).convert("RGB")
    jb = io.BytesIO()
    noisy.save(jb, "JPEG", quality=15)
    page.insert_image(pymupdf.Rect(140, 60, 240, 160), stream=jb.getvalue())
    page.add_text_annot((10, 10), "nota")
    doc.save(str(path))
    return path


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    return problem_pdf(tmp_path_factory.mktemp("pf") / "problemas.pdf")


def ids(res):
    return {f["regla"] for f in res["hallazgos"]}


def test_perfiles_disponibles():
    names = {p["id"] for p in engine.list_profiles()}
    assert {"offset_hoja", "flexo_empaque", "etiquetas_digital", "serigrafia", "basico"} <= names
    assert "GWG" not in "".join(p["nombre"] for p in engine.list_profiles() if "inspirado" not in p["nombre"])


def test_detecta_problemas_basicos(pdf):
    prof = engine.load_profile("basico")
    prof["reglas"]["jpeg_calidad"] = {"activa": True, "severidad": "advertencia", "min": 60}
    res = engine.run_preflight(pdf, prof)
    assert {"fuentes_no_incrustadas", "resolucion", "jpeg_calidad", "anotaciones", "sangrado"} <= ids(res)
    assert res["resumen"]["error"] >= 1
    assert all(f["mensaje"] for f in res["hallazgos"])


def test_perfil_desactiva_reglas(pdf):
    res = engine.run_preflight(pdf, {"nombre": "x", "reglas": {"anotaciones": {"activa": True, "severidad": "info"}}})
    assert ids(res) == {"anotaciones"}


def test_limpio_sin_errores_de_placas():
    if not ghostscript.available():
        pytest.skip("Ghostscript no instalado")
    src = Path(__file__).parent / "sinteticos_sep" / "limpio.pdf"
    res = engine.run_preflight(src, "offset_hoja")
    assert not ({"tac", "texto_pequeno", "negro_enriquecido_texto", "sobreimpresion", "linea_fina"} & ids(res))


def test_completo_dispara_reglas_de_placas():
    if not ghostscript.available():
        pytest.skip("Ghostscript no instalado")
    src = Path(__file__).parent / "sinteticos_sep" / "completo.pdf"
    res = engine.run_preflight(src, "offset_hoja")
    assert {"tac", "negro_enriquecido_texto", "tintas_duplicadas", "tintas_directas_max"} <= ids(res)


def test_correcciones_sobre_copia(pdf, tmp_path):
    before = pdf.read_bytes()
    dst = tmp_path / "ok.pdf"
    r = fixes.apply_fixes(pdf, dst, {"eliminar_anotaciones": True, "cajas": 3}, "basico")
    assert pdf.read_bytes() == before
    assert r["hecho"]["anotaciones_eliminadas"] >= 1
    assert r["despues"]["advertencia"] < r["antes"]["advertencia"]
    assert r["similitud_visual"] > 0.98
    assert "anotaciones" not in {f["regla"] for f in r["hallazgos_despues"]}


def test_sobreimpresion_tecnica(tmp_path):
    b = Builder()
    b.separation("CS0", "Troquel", (0, 0, 0, 1))
    b.rect(10, 10, 100, 100, "0.3 0.3 0 0 k")
    b.rect(30, 30, 40, 40, "/CS0 cs 1 scn")
    src = b.build(tmp_path / "t.pdf")
    if not ghostscript.available():
        pytest.skip("Ghostscript no instalado")
    before = engine.run_preflight(src, "offset_hoja")
    assert "sobreimpresion" in ids(before)
    r = fixes.apply_fixes(src, tmp_path / "t2.pdf", {"sobreimpresion_tecnicas": True}, "offset_hoja")
    assert r["hecho"]["objetos_sobreimpresion"] >= 1
    assert "sobreimpresion" not in {f["regla"] for f in r["hallazgos_despues"]}


def test_no_sobrescribe_y_correccion_desconocida(pdf):
    from app.core.errors import UserError
    with pytest.raises(UserError):
        fixes.apply_fixes(pdf, pdf, {})
    with pytest.raises(UserError):
        fixes.apply_fixes(pdf, pdf.with_name("otro.pdf"), {"inventada": True})


def test_reporte_pdf(pdf):
    res = engine.run_preflight(pdf, "basico")
    data = report.build_report(pdf, res, "problemas.pdf")
    with pymupdf.open(stream=data, filetype="pdf") as d:
        text = unicodedata.normalize("NFKC", "".join(p.get_text() for p in d))
    assert "Informe de preflight" in text and "no es una certificación" in text


def test_api_flujo(pdf):
    c = TestClient(app)
    with open(pdf, "rb") as f:
        r = c.post("/api/preflight", files={"file": ("problemas.pdf", f, "application/pdf")})
    jid = r.json()["job_id"]
    a = c.post(f"/api/preflight/{jid}/revisar?perfil=basico").json()["job_id"]
    for _ in range(100):
        st = c.get(f"/api/jobs/{a}").json()
        if st["status"] != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done", st
    assert c.get(f"/api/preflight/{jid}/pagina.png").headers["content-type"] == "image/png"
    fx = c.post(f"/api/preflight/{jid}/corregir", json={"correcciones": {"eliminar_anotaciones": True}, "perfil": "basico"})
    assert fx.status_code == 200, fx.text
    assert c.get(f"/api/preflight/{jid}/reporte").content.startswith(b"%PDF")
    assert c.get(f"/api/preflight/{jid}/descargar").status_code == 200
    assert c.post("/api/preflight", files={"file": ("a.txt", b"x")}).status_code == 400
