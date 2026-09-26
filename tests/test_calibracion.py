"""Calibración del modelo de mezcla (S3 §7.6)."""
import numpy as np
import pymupdf

from app.core import colorscience as cs
from app.modules.separate import calibration as cal
from app.modules.separate.raster import PAPER, Ink

INKS = [Ink("Cyan", (55, -37, -50)), Ink("Magenta", (48, 74, -3))]


def synthetic(n=2.2, gains=(0.12, 0.05)):
    """Lab 'medidos' generados con un modelo conocido (n y ganancia) para comprobar que el ajuste los recupera."""
    m = {}
    for i, g in zip(INKS, gains):
        for s in cal.STEPS:
            t = s / 100
            teff = min(t + g * 4 * t * (1 - t), 1.0)
            m[f"{i.name}|{s}"] = tuple(float(v) for v in cs.mix_inks(PAPER, [{"lab": i.lab, "opacity": 0}], [np.float64(teff)], n=n))
    return m


def test_grafico_y_plantilla(tmp_path):
    pdf = cal.chart_pdf(INKS)
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        assert len(d) == 1
    ids = [p["id"] for p in cal.patches(INKS)]
    assert "Cyan|50" in ids and "Cyan+Magenta|100" in ids and len(ids) == 22 + 1
    assert cal.template_csv(INKS).count("\n") == len(ids) + 1
    from app.modules.separate.pdf_inks import read_inventory
    (tmp_path / "c.pdf").write_bytes(pdf)
    assert {i.name for i in read_inventory(tmp_path / "c.pdf").inks} == {"Cyan", "Magenta"}


def test_ajuste_recupera_n_y_ganancia():
    r = cal.fit(INKS, synthetic())
    assert r["error_medio_de"] < 0.6                       # n y ganancia se compensan: se comprueba la calidad del ajuste, no cada valor
    assert 1.0 <= r["n"] <= 3.0 and r["tintas"]["Cyan"]["g50"] > 0


def test_perfil_guardar_y_aplicar(tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "PROFILES_DIR", tmp_path)
    prof = cal.fit(INKS, synthetic())
    cal.save_profile("Mi imprenta", prof)
    assert cal.list_profiles() == ["Mi imprenta"]
    inks, gains, n = cal.apply_profile(INKS, cal.load_profile("Mi imprenta"))
    assert gains["Cyan"] > 0 and abs(n - prof["n"]) < 1e-9


def test_csv_medidas_y_faltantes():
    import pytest
    from app.core.errors import UserError
    m = cal.parse_measurements("id;L;a;b\nCyan|100;55,1;-37;-50\nCyan|50;;;\n")
    assert m == {"Cyan|100": (55.1, -37.0, -50.0)}
    with pytest.raises(UserError):
        cal.fit(INKS, {})


def test_api_calibracion(tmp_path, monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(cal, "PROFILES_DIR", tmp_path)
    c = TestClient(app)
    t = {"tintas": [{"name": "Cyan", "lab": [55, -37, -50]}, {"name": "Magenta", "lab": [48, 74, -3]}]}
    assert c.post("/api/herramientas/calibracion/grafico", json=t).content.startswith(b"%PDF")
    assert b"Cyan|50" in c.post("/api/herramientas/calibracion/plantilla", json=t).content
    m = synthetic()
    csv_txt = "id;L;a;b\n" + "\n".join(f"{k};{v[0]};{v[1]};{v[2]}" for k, v in m.items())
    r = c.post("/api/herramientas/calibracion/ajustar", params={"tintas": json.dumps(t["tintas"]), "nombre": "Prueba"},
               files={"file": ("m.csv", csv_txt.encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["error_medio_de"] < 0.6
    assert c.get("/api/herramientas/calibracion/perfiles").json() == ["Prueba"]
