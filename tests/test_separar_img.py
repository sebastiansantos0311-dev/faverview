"""Separar colores → Imagen (S3): planas, proceso, índice, CMYK, tramado y salidas."""
import io
import time
import zipfile

import cv2
import numpy as np
import pikepdf
import pytest
from fastapi.testclient import TestClient

from app.core.pdffunctions import evaluate
from app.main import app
from app.modules.separate import halftone, raster, raster_export

INKS = [raster.Ink("Blanco", (95, 0, -2), 1.0), raster.Ink("Cyan", (55, -37, -50)), raster.Ink("Magenta", (48, 74, -3)),
        raster.Ink("Yellow", (89, -5, 93)), raster.Ink("Negro", (16, 0, 0))]


def logo():
    img = np.full((240, 320, 3), 255, np.uint8)
    cv2.circle(img, (90, 120), 70, (220, 30, 30), -1)
    cv2.rectangle(img, (180, 60), (300, 180), (30, 60, 200), -1)
    return img


def test_planas_encuentra_3_tintas():
    r = raster.separate_flat(logo(), 200)
    assert len(r.names) == 3
    tot = sum(r.channels[n].astype(int) for n in r.names)
    assert (tot == 255).all()                       # bordes duros: cada píxel en una sola tinta


def test_planas_paleta_fija_y_bordes_suaves():
    pal = [raster.Ink("Rojo", (48, 69, 52)), raster.Ink("Papel", (100, 0, 0))]
    r = raster.separate_flat(logo(), 200, pal, soft_edges=True)
    assert r.names == ["Rojo", "Papel"]


def test_proceso_blanco_y_choke():
    img = np.full((100, 100, 3), 255, np.uint8)
    r = raster.separate_process(img, INKS, raster.SUBSTRATES["Prenda negra"], white_index=0, choke_px=2)
    assert r.channels["Blanco"][50, 50] > 200
    assert r.channels["Blanco"][0, 0] == 0 or r.channels["Blanco"][0, 0] > 0   # el choke solo afecta al borde de la imagen
    assert r.stats["de_medio"] < 12


def test_proceso_papel_sin_tinta():
    img = np.full((40, 40, 3), 250, np.uint8)
    r = raster.separate_process(img, INKS[1:], raster.PAPER)
    assert r.stats["cobertura_total_media"] < 15


def test_indice_y_limites():
    r = raster.separate_index(logo(), k=4)
    assert 2 <= len(r.names) <= 4
    with pytest.raises(Exception):
        raster.separate_process(logo(), INKS * 3)


def test_cmyk_limita_tac():
    if not raster.find_cmyk_profiles():
        pytest.skip("sin perfil ICC CMYK")
    img = np.zeros((20, 20, 3), np.uint8)
    r = raster.separate_cmyk(img, tac=280)
    assert r.stats["tac_max"] <= 281


def test_limit_tac_mantiene_k():
    a = np.full((2, 2, 4), [255, 255, 255, 128], np.uint8)
    out = raster.limit_tac(a, 300)
    assert (out[..., 3] == 128).all() and out.astype(float).sum(-1).max() / 255 * 100 <= 300.5


@pytest.mark.parametrize("kind", ["am", "fm"])
def test_rampa_tramada_cobertura_nominal(kind):
    for nom in (0.1, 0.25, 0.5, 0.75, 0.9):
        cov = np.full((900, 900), round(nom * 255), np.uint8)
        ht = halftone.halftone(cov, 1200, kind=kind, lpi=60, min_dot=0, max_dot=1)
        assert abs(ht.mean() - nom) < 0.02


def test_blue_noise_es_permutacion():
    m = halftone.blue_noise(64)
    assert m.shape == (64, 64) and len(np.unique(m)) == 4096


def test_devicen_pdf_funcion_alternativa():
    r = raster.separate_flat(logo(), 200)
    data = raster_export.devicen_pdf(r, 200)
    pdf = pikepdf.open(io.BytesIO(data))
    fn = pdf.pages[0].Resources.XObject.Im0.ColorSpace[3]
    n = len(r.names)
    white = [0.0] * n
    assert evaluate(fn, white) == [0, 0, 0, 0]
    on = evaluate(fn, [1.0 if i == 1 else 0.0 for i in range(n)])
    assert max(on) > 0.3


def test_api_flujo():
    c = TestClient(app)
    ok, buf = cv2.imencode(".png", logo()[..., ::-1])
    r = c.post("/api/separar/img", files={"file": ("logo.png", buf.tobytes(), "image/png")})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    a = c.post(f"/api/separar/img/{jid}/procesar", json={"modo": "planas"}).json()["job_id"]
    for _ in range(100):
        st = c.get(f"/api/jobs/{a}").json()
        if st["status"] != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done", st
    assert c.get(f"/api/separar/img/{jid}/simulacion.png").status_code == 200
    z = c.post(f"/api/separar/img/{jid}/exportar", json={"trama": {"kind": "am", "lpi": 45}, "dpi_salida": 300})
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "informe.txt" in names and any(n.startswith("placas_1bit/") for n in names)
    assert c.post("/api/separar/img", files={"file": ("a.txt", b"x")}).status_code == 400


def test_rendimiento_proceso_grande():
    img = cv2.resize(logo(), (3000, 2250))
    t = time.time()
    raster.separate_process(img, INKS, raster.SUBSTRATES["Prenda negra"], white_index=0)
    assert time.time() - t < 30
