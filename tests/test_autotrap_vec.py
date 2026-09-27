"""Auto-trap vectorial (T4), pasos de receta y preflight (T5)."""
import io
from pathlib import Path

import cv2
import numpy as np
import pikepdf
import pytest

from app.core import ghostscript
from app.core.errors import UserError
from app.core.press import PressProfile
from app.modules.automation import engine
from app.modules.preflight import engine as pf_engine
from app.modules.separate.pdf_inks import read_inventory
from app.modules.separate.pdf_render import render_plates
from app.modules.tools import registration_check as rc
from app.modules.vectorize import export, pipeline, traps
from bench.synth_separations import Builder

PRESS = PressProfile(tolerancia_mm=0.2)
gs = pytest.mark.skipif(not ghostscript.available(), reason="Ghostscript no instalado")


def logo():
    img = np.full((300, 420, 3), 255, np.uint8)
    cv2.rectangle(img, (40, 40), (380, 260), (30, 60, 200), -1, cv2.LINE_AA)
    cv2.circle(img, (150, 150), 70, (230, 200, 20), -1, cv2.LINE_AA)
    cv2.circle(img, (300, 150), 50, (20, 150, 60), -1, cv2.LINE_AA)
    return img


def vec():
    return pipeline.vectorize(logo(), 254, preset="logo")


def plates_of(pdf_bytes, tmp_path, dpi=600, name="v.pdf"):
    f = tmp_path / name
    f.write_bytes(pdf_bytes)
    inv = read_inventory(f)
    return render_plates(f, 0, dpi, use_cache=False), {i.name: {"tipo": i.kind, "lab": i.lab} for i in inv.inks}


def test_estructura_del_pdf_con_traps(tmp_path):
    r = vec()
    pdf = export.to_pdf(r, None, trap=PRESS, names=[i.name for i in r.palette])
    with pikepdf.open(io.BytesIO(pdf)) as p:
        ocgs = [str(o.Name) for o in p.Root.OCProperties.OCGs]
        assert ocgs == ["Traps FAVERVIEW"]
        assert p.pages[0].Resources.ExtGState.GSop.OP is True and p.pages[0].Resources.ExtGState.GSop.OPM == 1
        content = p.pages[0].Contents.read_bytes()
    assert b"/OC /FVTraps BDC" in content and b"W n" in content and b"EMC" in content
    sin = export.to_pdf(r, None, names=[i.name for i in r.palette])
    with pikepdf.open(io.BytesIO(sin)) as p:
        assert "/OCProperties" not in p.Root


@gs
def test_pdf_vectorial_con_traps_pasa_la_prueba_de_movimiento(tmp_path):
    r = vec()
    names = [i.name for i in r.palette]
    con, meta = plates_of(export.to_pdf(r, None, trap=PRESS, names=names), tmp_path, name="con_trap.pdf")
    sin, meta0 = plates_of(export.to_pdf(r, None, names=names, sin_fondo=True), tmp_path, name="sin_trap.pdf")
    assert rc.check(sin, PRESS, meta0).filetes_px > 0
    assert rc.check(con, PRESS, meta).filetes_px == 0
    assert rc.check(con, PRESS, meta, factor=2).filetes_px > 0                      # la prueba mide algo
    # las regiones fuera de A ∪ B no cambian: la unión de tintas es la misma con y sin trap
    u = lambda pl: np.max([pl.arrays[n] for n in pl.names if n in meta and not pl.empty(n)], axis=0) > 127
    u_con, u_sin = u(con), u(sin)
    assert (u_con ^ u_sin).sum() <= 0.003 * u_sin.sum()


def test_trap_centrado_dos_trazos_y_resumen():
    r = vec()
    # dos colores de luminosidad parecida → R5
    r.palette[2].lab = (54.0, 60.0, 40.0)
    r.palette[3].lab = (52.0, -60.0, 40.0)
    for reg in r.regions:
        pass
    g = traps.build(r, PRESS, 25.4 / r.dpi)
    assert g and all(t["regla"] in ("R3", "R4", "R5") for x in g for t in x["trazos"])
    s = traps.summary(g, 25.4 / r.dpi)
    assert all(x["ancho_trazo_mm"] > 0.2 for x in s)


def test_svg_con_traps_simulados_y_errores():
    r = vec()
    svg = export.to_svg(r, None, PRESS)
    assert 'id="traps-faverview"' in svg and "multiply" in svg
    assert 'id="traps-faverview"' not in export.to_svg(r)
    apilado = pipeline.vectorize(logo(), 254, preset="logo", mode="apilado")
    with pytest.raises(UserError):
        export.to_pdf(apilado, None, trap=PRESS)
    sin_tam = pipeline.vectorize(logo(), None, preset="logo")
    with pytest.raises(UserError):
        traps.build(sin_tam, PRESS, None)
    assert traps.build(r, PressProfile(tolerancia_mm=0.0), 25.4 / r.dpi) == []


def test_api_vectorizar_con_trap():
    import time
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    ok, buf = cv2.imencode(".png", logo()[..., ::-1])
    jid = c.post("/api/vectorizar", files={"file": ("l.png", buf.tobytes(), "image/png")}).json()["job_id"]
    a = c.post(f"/api/vectorizar/{jid}/procesar", json={"preset": None, "k_max": 6, "dpi": 254}).json()["job_id"]
    for _ in range(150):
        st = c.get(f"/api/jobs/{a}").json()
        if st["status"] != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done", st
    info = c.get(f"/api/vectorizar/{jid}/traps?tam_mm=100&trap_prensa=offset_pliego").json()
    assert info["traps"] and "Estimación" in info["avisos"][-1]
    pdf = c.get(f"/api/vectorizar/{jid}/descargar?formato=pdf&tam_mm=100&trap_prensa=serigrafia_textil_automatica")
    assert pdf.content.startswith(b"%PDF") and b"Traps FAVERVIEW" in pdf.content
    assert 'traps-faverview' in c.get(f"/api/vectorizar/{jid}/descargar?formato=svg&tam_mm=100&trap_prensa=flexo_banda_angosta").text


# ---------------------------------------------------------------- T5
def touching_pdf(path: Path) -> Path:
    b = Builder()
    b.separation("CS0", "Amarillo Demo", (0, 0, 1, 0))
    b.separation("CS1", "Azul Demo", (1, 0.5, 0, 0))
    b.rect(20, 20, 100, 100, "/CS0 cs 1 scn")
    b.rect(120, 20, 100, 100, "/CS1 cs 1 scn")
    return b.build(path)


@gs
def test_preflight_bordes_sin_proteccion(tmp_path):
    src = touching_pdf(tmp_path / "t.pdf")
    res = pf_engine.run_preflight(src, "serigrafia")
    f = [x for x in res["hallazgos"] if x["regla"] == "bordes_sin_proteccion"]
    assert f and f[0]["bbox"] and "filete" in f[0]["mensaje"]
    assert not [x for x in pf_engine.run_preflight(src, "offset_hoja")["hallazgos"] if x["regla"] == "bordes_sin_proteccion"]


@gs
def test_receta_auto_trap_y_prueba_de_movimiento(tmp_path):
    src = touching_pdf(tmp_path / "t.pdf")
    solo_prueba = {"nombre": "solo prueba", "pasos": [{"accion": "prueba_movimiento", "parametros": {"perfil": "serigrafia_textil_automatica", "dpi": 300}}]}
    r = engine.run_file(solo_prueba, src, tmp_path / "o1")
    assert r["estado"] == "detenido" and "filetes" in r["motivo"]                       # sin trap: se detiene
    con_trap = {"nombre": "con trap", "pasos": [{"accion": "auto_trap", "parametros": {"dpi": 300}},
                                                {"accion": "prueba_movimiento", "parametros": {"dpi": 300}}]}
    r2 = engine.run_file(con_trap, src, tmp_path / "o2")
    assert r2["estado"] == "ok", r2
    assert any(Path(p).name == "placas_con_trap.zip" for p in r2["salidas"])
    assert any("sin filetes" in l for l in r2["log"])


def test_receta_separar_imagen_con_auto_trap(tmp_path):
    cv2.imwrite(str(tmp_path / "logo.png"), logo()[..., ::-1])
    rec = {"nombre": "x", "pasos": [{"accion": "separar.imagen", "parametros": {"modo": "planas", "auto_trap": True, "colores": 6}}]}
    r = engine.run_file(rec, tmp_path / "logo.png", tmp_path / "o")
    assert r["estado"] == "ok", r
    assert any("Auto-trap" in l for l in r["log"])
    assert engine.validate({"nombre": "y", "pasos": [{"accion": "auto_trap"}, {"accion": "prueba_movimiento"}]}) == []
