"""Servidor listo para el plugin (PLUGIN P0): token, CORS, Host, handshake y rutas del plugin."""
import json
import time

import cv2
import numpy as np
import pymupdf
from fastapi.testclient import TestClient

from app.core import plugin_auth
from app.main import app
from bench.synth_separations import Builder

c = TestClient(app)


def tok():
    return {plugin_auth.HEADER: plugin_auth.get_token()}


def wait(jid, headers, n=200):
    for _ in range(n):
        st = c.get(f"/api/jobs/{jid}", headers=headers).json()
        if st["status"] != "running":
            return st
        time.sleep(0.2)
    return st


def test_archivo_de_conexion_y_token_estable(monkeypatch):
    f = plugin_auth.write_connection_file(8123)
    d = json.loads(f.read_text(encoding="utf-8"))
    assert d["puerto"] == 8123 and len(d["token"]) >= 32 and d["pid"] > 0 and d["version"]
    monkeypatch.setattr(plugin_auth, "_TOKEN", None)
    assert plugin_auth.get_token() == d["token"]                       # se conserva entre arranques
    plugin_auth.write_connection_file(8200)
    assert json.loads(f.read_text(encoding="utf-8"))["puerto"] == 8200


def test_sin_token_o_token_malo_401():
    assert c.get("/api/plugin/handshake").status_code == 401
    assert c.get("/api/plugin/handshake", headers={plugin_auth.HEADER: "x" * 43}).status_code == 401
    assert c.get("/api/plugin/handshake", headers=tok()).status_code == 200


def test_handshake():
    d = c.get("/api/plugin/handshake", headers=tok()).json()
    assert d["api_version"] == 1 and d["version"] and "vectorizar" in d["modulos"] and "ghostscript" in d["herramientas"]


def test_origen_externo_sin_token_rechazado_y_frontend_propio_libre():
    assert c.get("/api/status", headers={"Origin": "https://sitio-malo.example"}).status_code == 401
    assert c.get("/api/status", headers={"Origin": "null"}).status_code == 401                   # CEP sin token
    assert c.get("/api/status", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 401
    assert c.get("/api/status", headers={"Origin": "http://testserver", "Host": "testserver"}).status_code == 200
    assert c.get("/api/status").status_code == 200                                               # sin Origin (mismo origen / curl local)


def test_origen_desconocido_con_token_rechazado():
    r = c.get("/api/status", headers={"Origin": "https://sitio-malo.example", **tok()})
    assert r.status_code == 403


def test_cep_con_token_recibe_cors_y_sin_wildcard():
    for origin in ("null", "file://"):
        r = c.get("/api/plugin/handshake", headers={"Origin": origin, **tok()})
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
    assert c.get("/api/plugin/handshake", headers=tok()).headers.get("access-control-allow-origin") is None


def test_preflight_options():
    r = c.options("/api/plugin/handshake", headers={"Origin": "null", "Access-Control-Request-Method": "POST",
                                                     "Access-Control-Request-Headers": "x-faverview-token, content-type",
                                                     "Access-Control-Request-Private-Network": "true"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == "null"
    assert "x-faverview-token" in r.headers["access-control-allow-headers"].lower()
    assert r.headers["access-control-allow-private-network"] == "true"
    assert c.options("/api/plugin/handshake", headers={"Origin": "https://malo.example", "Access-Control-Request-Method": "POST"}).status_code == 403


def test_host_distinto_rechazado_dns_rebinding():
    assert c.get("/api/status", headers={"Host": "evil.example.com"}).status_code == 400
    assert c.get("/api/status", headers={"Host": "127.0.0.1:8000"}).status_code == 200


# ---------------------------------------------------------------- rutas
def _pdf_con_objetos(path):
    b = Builder(283.5, 283.5)            # 100 x 100 mm
    b.separation("CS0", "Tinta Demo", (0, 0.9, 0.8, 0))
    b.rect(20, 40, 80, 60, "/CS0 cs 1 scn")
    return b.build(path)


def test_vectorizar_devuelve_pdf():
    img = np.full((200, 300, 3), 255, np.uint8)
    cv2.circle(img, (100, 100), 60, (30, 30, 220), -1)
    ok, buf = cv2.imencode(".png", img)
    r = c.post("/api/plugin/vectorizar", headers=tok(), files={"file": ("l.png", buf.tobytes(), "image/png")},
               data={"parametros": json.dumps({"preset": "logo", "dpi": 254}), "tamano_mm": "50"})
    assert r.status_code == 200
    st = wait(r.json()["job_id"], tok())
    assert st["status"] == "done", st
    res = st["result"]
    assert res["estadisticas"]["colores"] >= 2
    url = next(a["url"] for a in res["archivos"] if a["nombre"] == "vector.pdf")
    pdf = c.get(url, headers=tok())
    assert pdf.content.startswith(b"%PDF")
    with pymupdf.open(stream=pdf.content, filetype="pdf") as d:
        assert abs(d[0].rect.width - 50 / 25.4 * 72) < 0.6                       # el tamaño final pedido
    assert c.get(url).status_code == 401


def test_preflight_bbox_en_puntos_pdf(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=283.5, height=283.5)
    pg.add_text_annot((50, 50), "nota")                                           # anotación en (50, 50) desde arriba
    doc.save(str(tmp_path / "a.pdf"))
    with open(tmp_path / "a.pdf", "rb") as f:
        r = c.post("/api/plugin/preflight", headers=tok(), files={"file": ("a.pdf", f, "application/pdf")}, data={"perfil": "basico"})
    st = wait(r.json()["job_id"], tok())
    assert st["status"] == "done", st
    an = [h for h in st["result"]["hallazgos"] if h["regla"] == "anotaciones"]
    assert an and st["result"]["page_size_pt"] == [283.5, 283.5]
    x0, y0, x1, y1 = an[0]["bbox_pt"]
    assert 40 < x0 < 60 and 283.5 - 70 < y0 < 283.5 - 30 and y1 > y0 and x1 > x0     # abajo-izquierda: y = alto - (50 + ...)


def test_codigo_y_braille_pdf():
    r = c.post("/api/plugin/codigo", headers=tok(), json={"tipo": "ean13", "datos": "590123412345"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and float(r.headers["x-ancho-mm"]) > 30
    v = c.post("/api/plugin/codigo", headers=tok(), json={"tipo": "ean13", "datos": "590123412345", "vista": True}).json()
    assert "<svg" in v["svg"]
    assert c.post("/api/plugin/codigo", headers=tok(), json={"tipo": "ean13", "datos": "1"}).status_code == 400
    b = c.post("/api/plugin/braille", headers=tok(), json={"texto": "hola", "ancho_mm": 80})
    assert b.content.startswith(b"%PDF")


def test_verificar_codigos_bbox_pt(tmp_path):
    from app.modules.barcodes import generate as g
    lay = g.layout("ean13", "5901234123457")
    doc = pymupdf.open()
    pg = doc.new_page(width=283.5, height=283.5)
    with pymupdf.open(stream=g.to_pdf(lay), filetype="pdf") as src:
        pg.show_pdf_page(pymupdf.Rect(50, 50, 50 + lay.width * 72 / 25.4, 50 + lay.height * 72 / 25.4), src, 0)
    doc.save(str(tmp_path / "c.pdf"))
    with open(tmp_path / "c.pdf", "rb") as f:
        r = c.post("/api/plugin/codigos/verificar", headers=tok(), files={"file": ("c.pdf", f, "application/pdf")}, data={"dpi": "600"}).json()
    x0, y0, x1, y1 = r["codigos"][0]["bbox_pt"]
    assert r["codigos"][0]["contenido"] == "5901234123457" and 45 < x0 < 70 and y0 < 283.5 - 50 and (x1 - x0) > 60


def test_comparar_y_separar(tmp_path):
    from app.core import ghostscript
    src = _pdf_con_objetos(tmp_path / "p.pdf")
    with pymupdf.open(str(src)) as d:
        d[0].get_pixmap(dpi=100).save(str(tmp_path / "arte.png"))
    with open(tmp_path / "arte.png", "rb") as f1, open(src, "rb") as f2:
        r = c.post("/api/plugin/comparar", headers=tok(), files={"arte": ("arte.png", f1, "image/png"), "mesa": ("p.pdf", f2, "application/pdf")})
    st = wait(r.json()["job_id"], tok())
    assert st["status"] == "done", st
    assert st["result"]["page_size_pt"] == [283.5, 283.5] and "diferencias" in st["result"]
    if ghostscript.available():
        with open(src, "rb") as f:
            s = c.post("/api/plugin/separar", headers=tok(), files={"file": ("p.pdf", f, "application/pdf")}, data={"dpi": "100"}).json()
        st = wait(s["analisis_id"], tok())
        assert st["status"] == "done" and any(p["nombre"] == "Tinta Demo" for p in st["result"]["placas"])
        assert c.get(s["urls"]["composicion"], headers=tok()).status_code == 200
        out = c.post("/api/plugin/separar/hallazgos_pt?alto_pt=283.5&dpi=72", headers=tok(), json=[{"bbox": [10, 10, 20, 20], "mensaje": "x"}]).json()
        assert out[0]["bbox_pt"] == [10.0, 283.5 - 30.0, 30.0, 283.5 - 10.0]


def test_rutas_existentes_intactas_para_el_frontend():
    assert c.get("/api/version").status_code == 200 and c.get("/").status_code == 200
