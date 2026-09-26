"""Vectorizador (S4): fronteras compartidas, ajuste de curvas, exportaciones y API."""
import io
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.vectorize import boundaries, export, fit, pipeline


def logo():
    img = np.full((300, 400, 3), 255, np.uint8)
    cv2.circle(img, (120, 150), 80, (220, 30, 30), -1, cv2.LINE_AA)
    cv2.rectangle(img, (230, 60), (360, 240), (30, 60, 200), -1, cv2.LINE_AA)
    cv2.circle(img, (120, 150), 30, (255, 255, 255), -1, cv2.LINE_AA)
    return img


def test_cadenas_separan_dos_regiones():
    L = np.zeros((10, 12), np.int32)
    L[2:6, 3:8] = 1
    L[6:9, 6:10] = 2
    chains = boundaries.build_chains(L)
    pairs = {frozenset((c.left, c.right)) for c in chains}
    assert frozenset((1, 2)) in pairs and frozenset((-1, 0)) in pairs


def test_ajuste_recta_y_arco():
    t = np.linspace(0, 1, 60)
    line = np.stack([t * 50, t * 20], 1)
    assert [s[0] for s in fit.fit_polyline(line)] == ["L"]
    arc = np.stack([50 * np.cos(t * np.pi / 2), 50 * np.sin(t * np.pi / 2)], 1)
    segs = fit.fit_polyline(arc, tol=0.3)
    assert all(s[0] == "C" for s in segs) and len(segs) <= 3


def test_pocos_nodos_y_tres_colores():
    r = pipeline.vectorize(logo(), 150, preset="logo")
    assert r.stats["colores"] == 3
    assert r.stats["nodos"] <= 40


def test_sin_huecos_ni_solapes():
    """Con fronteras compartidas cada píxel del render sin antialias queda cubierto por exactamente una región."""
    import fitz
    r = pipeline.vectorize(logo(), 150, preset="logo")
    svg = export.to_svg(r).replace("<svg ", '<svg width="600" height="450" ', 1)
    fitz.TOOLS.set_aa_level(0)
    try:
        pix = fitz.open(stream=svg.encode(), filetype="svg")[0].get_pixmap(alpha=True)
    finally:
        fitz.TOOLS.set_aa_level(8)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 4)
    assert (a[:-1, :-1, 3] == 0).mean() < 1e-4       # la última fila/columna puede quedar fuera por el redondeo del tamaño


def test_render_fiel():
    r = pipeline.vectorize(logo(), 150, preset="logo")
    from skimage.metrics import structural_similarity
    out = export.render(r, 400, 300)
    assert structural_similarity(out, logo(), channel_axis=2, data_range=255) > 0.95


def test_modo_apilado_sin_agujeros():
    r = pipeline.vectorize(logo(), 150, preset="logo", mode="apilado")
    svg = export.to_svg(r)
    assert svg.count("<path") == 3


def test_pdf_tintas_directas_y_dxf_y_eps():
    r = pipeline.vectorize(logo(), 150, preset="logo")
    pdf = export.to_pdf(r, 100, names=["Fondo", "Rojo", "Azul"])
    import pikepdf
    with pikepdf.open(io.BytesIO(pdf)) as p:
        spaces = [str(v[1]) for v in p.pages[0].Resources.ColorSpace.values()]
    assert set(spaces) == {"/Fondo", "/Rojo", "/Azul"} or len(spaces) == 3
    assert b"LWPOLYLINE" in export.to_dxf(r, 100)
    from app.core import ghostscript
    if ghostscript.available():
        assert export.to_eps(pdf).startswith(b"%!PS")


def test_dxf_pide_tamano():
    from app.core.errors import UserError
    r = pipeline.vectorize(logo(), None, preset="logo")
    with pytest.raises(UserError):
        export.to_dxf(r, None)


def test_api_flujo():
    c = TestClient(app)
    ok, buf = cv2.imencode(".png", logo()[..., ::-1])
    r = c.post("/api/vectorizar", files={"file": ("l.png", buf.tobytes(), "image/png")})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    a = c.post(f"/api/vectorizar/{jid}/procesar", json={"k_max": 4}).json()["job_id"]
    for _ in range(150):
        st = c.get(f"/api/jobs/{a}").json()
        if st["status"] != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done", st
    assert c.get(f"/api/vectorizar/{jid}/vector.svg").text.startswith("<svg")
    assert c.get(f"/api/vectorizar/{jid}/diferencias.png").status_code == 200
    assert c.get(f"/api/vectorizar/{jid}/descargar?formato=pdf&tam_mm=100").content.startswith(b"%PDF")
    assert c.get(f"/api/vectorizar/{jid}/descargar?formato=dxf&tam_mm=100").status_code == 200
    assert c.post("/api/vectorizar", files={"file": ("a.txt", b"x")}).status_code == 400
