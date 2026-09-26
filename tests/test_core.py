import pytest
from fastapi.testclient import TestClient

from app.core import ghostscript, tools
from app.core.errors import UserError
from app.main import app

needs_gs = pytest.mark.skipif(not ghostscript.available(), reason="Ghostscript no instalado")


def test_status_endpoint_lists_tools_and_modules():
    r = TestClient(app).get("/api/status").json()
    assert set(r["herramientas"]) == {"ghostscript", "tesseract"}
    assert set(r["modulos"]) == set(tools.MODULOS)
    assert r["version"]


@needs_gs
def test_ghostscript_runs_with_safer_and_reports_version():
    assert ghostscript.gs_version().split(".")[0].isdigit()
    p = ghostscript.run_gs(["--version"])
    assert p.returncode == 0 and p.stdout.strip()
    assert "-dSAFER" in ghostscript.BASE_ARGS


@needs_gs
def test_ghostscript_errors_are_translated_to_spanish(tmp_path):
    bad = tmp_path / "malo.pdf"
    bad.write_bytes(b"%PDF-1.4 esto no es un pdf")
    with pytest.raises(UserError) as e:
        ghostscript.run_gs(["-sDEVICE=nullpage", str(bad)])
    assert "Ghostscript" in e.value.message


def test_missing_ghostscript_gives_install_hint(monkeypatch):
    monkeypatch.setattr(ghostscript, "find_gs", lambda: None)
    with pytest.raises(UserError, match="README"):
        ghostscript.run_gs(["--version"])


def test_user_error_becomes_http_400_without_traceback():
    from fastapi import APIRouter
    r = APIRouter()

    @r.get("/api/_prueba_error")
    def boom():
        raise UserError("Algo salió mal, en español.")

    app.include_router(r)
    resp = TestClient(app).get("/api/_prueba_error")
    assert resp.status_code == 400 and resp.json()["error"] == "Algo salió mal, en español."


def test_upload_validation_message_in_spanish():
    resp = TestClient(app).post("/api/compare", files={"client_file": ("a.exe", b"x"), "design_file": ("d.pdf", b"x")})
    assert resp.status_code == 400 and "Formato no admitido" in resp.json()["detail"]


def test_inks_api_import_list_export_delete(tmp_path, monkeypatch):
    from app.core import inks
    monkeypatch.setattr(inks, "DATOS_DIR", tmp_path)
    c = TestClient(app)
    libs = c.get("/api/tintas").json()
    assert libs[0]["solo_lectura"] is True
    r = c.post("/api/tintas-importar", files={"file": ("demo.csv", b"Demo Rojo 1,45,68,50\nDemo Azul,30,10,-55\n")},
               data={"nombre": "Mi taller"})
    assert r.status_code == 200 and len(r.json()["inks"]) == 2 and r.json()["inks"][0]["swatch"].startswith("#")
    assert [x["nombre"] for x in c.get("/api/tintas").json()][-1] == "Mi taller"
    assert "Demo Azul" in c.get("/api/tintas/Mi taller/exportar?formato=csv").text
    bad = c.post("/api/tintas-importar", files={"file": ("x.pdf", b"x")}, data={"nombre": "x"})
    assert bad.status_code == 400 and "no admitido" in bad.json()["error"]
    assert c.delete("/api/tintas/Mi taller").json() == {"ok": True}
    assert c.delete("/api/tintas/ISO 12647-2 PC1 (FOGRA51) + básicas").status_code == 400
