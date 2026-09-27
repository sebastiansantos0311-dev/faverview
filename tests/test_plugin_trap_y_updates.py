"""Ruta de trap del plugin (P7), clasificación de tintas y aviso de actualización del plugin (P9)."""
import io
import json
import time

import cv2
import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core import ghostscript, plugin_auth
from app.main import app
from bench.synth_separations import Builder

c = TestClient(app)
gs = pytest.mark.skipif(not ghostscript.available(), reason="Ghostscript no instalado")


def tok():
    return {plugin_auth.HEADER: plugin_auth.get_token()}


def wait(jid, n=400):
    for _ in range(n):
        st = c.get(f"/api/jobs/{jid}", headers=tok()).json()
        if st["status"] != "running":
            return st
        time.sleep(0.25)
    return st


def touching(path):
    b = Builder(283.5, 283.5)
    b.separation("CS0", "Amarillo Demo", (0, 0, 1, 0))
    b.separation("CS1", "Azul Demo", (1, 0.5, 0, 0))
    b.rect(20, 20, 100, 100, "/CS0 cs 1 scn")
    b.rect(120, 20, 100, 100, "/CS1 cs 1 scn")
    return b.build(path)


@gs
def test_trap_analiza_y_crea_pdf_vectorial(tmp_path):
    src = touching(tmp_path / "t.pdf")
    with open(src, "rb") as f:
        r = c.post("/api/plugin/trap", headers=tok(), files={"file": ("t.pdf", f, "application/pdf")},
                   data={"perfil": "serigrafia_textil_automatica", "crear_vectorial": "true", "dpi": "600"})
    st = wait(r.json()["job_id"])
    assert st["status"] == "done", st
    res = st["result"]
    assert res["ok"] is False and res["registro"]["filetes_mm2"] > 5 and res["filetes"]
    x0, y0, x1, y1 = res["filetes"][0]["bbox_pt"]
    assert 100 < x0 < 145 and 10 < y0 < 130 and y1 > y0                       # cerca de la frontera x = 120 pt, en pt PDF (abajo-izquierda)
    assert res["arte_plano"] is True and res["vectorial"]["disponible"]
    pdf = c.get(res["vectorial"]["archivos"][0]["url"], headers=tok())
    assert pdf.content.startswith(b"%PDF")
    with pymupdf.open(stream=pdf.content, filetype="pdf") as d:
        assert abs(d[0].rect.width - 283.5) < 1
    from app.modules.separate.pdf_inks import read_inventory
    (tmp_path / "traps.pdf").write_bytes(pdf.content)
    assert {i.name for i in read_inventory(tmp_path / "traps.pdf").inks} <= {"Amarillo Demo", "Azul Demo"}      # mismas tintas, mismos nombres
    # combinado con el arte, la prueba de movimiento pasa
    from app.core.press import PressProfile
    from app.modules.separate.pdf_render import render_plates
    from app.modules.tools import registration_check as rc
    doc = pymupdf.open(str(src))
    with pymupdf.open(stream=pdf.content, filetype="pdf") as tr:
        doc[0].show_pdf_page(doc[0].rect, tr, 0)
    doc.save(str(tmp_path / "comb.pdf"))
    inv = read_inventory(tmp_path / "comb.pdf")
    pl = render_plates(tmp_path / "comb.pdf", 0, 600, use_cache=False)
    out = rc.check(pl, PressProfile(tolerancia_mm=0.2), {i.name: {"tipo": i.kind, "lab": i.lab} for i in inv.inks})
    assert out.filetes_mm2 < 0.1


@gs
def test_trap_arte_con_imagen_no_es_plano(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=283.5, height=283.5)
    ok, buf = cv2.imencode(".png", np.full((20, 20, 3), 128, np.uint8))
    pg.insert_image(pymupdf.Rect(20, 20, 120, 120), stream=buf.tobytes())
    doc.save(str(tmp_path / "i.pdf"))
    with open(tmp_path / "i.pdf", "rb") as f:
        r = c.post("/api/plugin/trap", headers=tok(), files={"file": ("i.pdf", f, "application/pdf")}, data={"crear_vectorial": "true"})
    st = wait(r.json()["job_id"])
    assert st["status"] == "done", st
    assert st["result"]["arte_plano"] is False and "imágenes" in st["result"]["vectorial"]["mensaje"]


def test_clasificar_tintas():
    r = c.post("/api/plugin/tintas/clasificar", headers=tok(), json={"nombres": ["Troquel", "Pantone 485C", "PANTONE 485 C", "Blanco"]}).json()
    assert r["Troquel"]["tipo"] == "technical" and r["Pantone 485C"]["norm"] == r["PANTONE 485 C"]["norm"] and r["Blanco"]["tipo"] == "white"


def test_actualizacion_del_plugin(monkeypatch):
    from app import updates
    body = json.dumps([{"html_url": "https://github.com/x/y/releases/tag/p3", "assets": [{"name": "FAVERVIEW-Illustrator-3.2.0.zxp"}]},
                       {"html_url": "https://github.com/x/y/releases/tag/p1", "assets": [{"name": "FAVERVIEW-Illustrator-3.1.0.zxp"}, {"name": "otro.zip"}]}]).encode()

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: R(body))
    assert updates.plugin_release() == ("3.2.0", "https://github.com/x/y/releases/tag/p3")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("sin internet")))
    assert updates.plugin_release() == (None, None)
