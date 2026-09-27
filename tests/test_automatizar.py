"""Automatización (S8): recetas, carpeta, condiciones y carpeta vigilada."""
import io
import json
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core import ghostscript
from app.core.errors import UserError
from app.main import app
from app.modules.automation import engine, steps
from bench.synth_separations import Builder


def make_pdf(path: Path, dup=True):
    b = Builder()
    b.separation("CS0", "Demo Rojo", (0, 0.9, 0.8, 0))
    b.separation("CS1", "DEMO ROJO", (0, 0.9, 0.8, 0))
    b.rect(20, 20, 100, 100, "/CS0 cs 1 scn")
    b.rect(140, 20, 100, 100, "/CS1 cs 1 scn")
    b.text(20, 150, 12, "Texto", "0 0 0 1 k")
    return b.build(path)


RECETA = {"nombre": "Prueba de 3 pasos", "pasos": [
    {"accion": "preflight", "parametros": {"perfil": {"x": 1} and "basico", "detener_si_errores": False}},
    {"modulo": "separar", "accion": "unir_duplicadas"},
    {"accion": "reporte"}]}


@pytest.fixture
def carpeta(tmp_path):
    ent = tmp_path / "entrada"
    ent.mkdir()
    for i in range(5):
        make_pdf(ent / f"trabajo{i}.pdf")
    (ent / "roto.pdf").write_bytes(b"esto no es un pdf")
    return ent


def test_validacion_de_recetas():
    assert engine.validate(RECETA) == []
    assert engine.validate({"nombre": "", "pasos": []})
    assert any("no existe" in e for e in engine.validate({"nombre": "x", "pasos": [{"accion": "inventada"}]}))
    assert any("parámetro" in e for e in engine.validate({"nombre": "x", "pasos": [{"accion": "reporte", "parametros": {"zzz": 1}}]}))
    assert engine.step_key({"modulo": "tools", "accion": "trapping"}) == "tools.trapping"


def test_recetas_de_ejemplo_validas():
    ids = {r["id"] for r in engine.list_recipes()}
    assert {"revision_rapida", "etiqueta_flexo", "logo_serigrafia"} <= ids
    for i in ids:
        assert engine.validate(engine.load_recipe(i)) == [], i


def test_receta_3_pasos_sobre_5_archivos_y_1_con_error(carpeta, tmp_path):
    salida = tmp_path / "salida_lote"
    r = engine.run_folder(RECETA, carpeta, salida)
    assert r["archivos"] == 6 and r["ok"] == 5 and r["errores"] == 1
    assert len([d for d in (salida / "salida").iterdir() if d.is_dir()]) == 5
    assert (salida / "errores" / "roto.pdf").exists() and (salida / "errores" / "roto.log.txt").exists()
    assert (salida / "reportes" / "resumen.md").exists() and (salida / "reportes" / "trabajo0.txt").exists()
    one = salida / "salida" / "trabajo0"
    assert (one / "sin_duplicadas.pdf").exists() and (one / "resumen.txt").exists() and (one / "preflight.pdf").exists()
    assert "Preflight" in (salida / "reportes" / "trabajo0.txt").read_text(encoding="utf-8")


def test_condicion_detiene_y_mueve_a_errores(carpeta, tmp_path):
    rec = {"nombre": "estricta", "pasos": [{"accion": "preflight", "parametros": {"perfil": "basico", "detener_si_errores": True}}, {"accion": "reporte"}]}
    r = engine.run_folder(rec, carpeta, tmp_path / "s")
    assert r["detenidos"] == 5 and r["ok"] == 0                  # las fuentes Helvetica no incrustadas son error en el perfil básico
    assert (tmp_path / "s" / "errores" / "trabajo1.pdf").exists()
    assert "DETENIDO" in (tmp_path / "s" / "errores" / "trabajo1.log.txt").read_text(encoding="utf-8")
    assert not (tmp_path / "s" / "salida" / "trabajo1").exists()


def test_paso_con_archivo_de_tipo_equivocado(tmp_path):
    cv2.imwrite(str(tmp_path / "i.png"), np.full((50, 50, 3), 255, np.uint8))
    r = engine.run_file({"nombre": "x", "pasos": [{"accion": "separar.unir_duplicadas"}]}, tmp_path / "i.png", tmp_path / "o")
    assert r["estado"] == "error" and "PDF" in r["motivo"]


def test_receta_de_imagen(tmp_path):
    img = np.full((200, 300, 3), 255, np.uint8)
    cv2.circle(img, (100, 100), 60, (220, 30, 30), -1)
    cv2.imwrite(str(tmp_path / "logo.png"), img)
    rec = engine.load_recipe("logo_serigrafia")
    r = engine.run_file(rec, tmp_path / "logo.png", tmp_path / "o")
    assert r["estado"] == "ok", r
    names = {Path(p).name for p in r["salidas"]}
    assert {"separacion.zip", "vector.svg", "vector.pdf", "resumen.txt"} <= names


def test_guardar_y_borrar_receta(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "USER_DIR", tmp_path)
    engine.save_recipe("mia", RECETA)
    assert engine.load_recipe("mia")["nombre"] == RECETA["nombre"]
    assert any(r["id"] == "mia" and r["propia"] for r in engine.list_recipes())
    engine.delete_recipe("mia")
    with pytest.raises(UserError):
        engine.delete_recipe("revision_rapida")
    with pytest.raises(UserError):
        engine.save_recipe("mala", {"nombre": "x", "pasos": []})
    with pytest.raises(UserError):
        engine.save_recipe("../fuera", RECETA)


def test_carpeta_vigilada(tmp_path):
    ent, sal = tmp_path / "in", tmp_path / "out"
    ent.mkdir()
    engine.start_watch("t1", RECETA, ent, sal)
    try:
        make_pdf(ent / "nuevo.pdf")
        for _ in range(80):
            st = engine.watch_status()
            if st and st[0]["procesados"]:
                break
            time.sleep(0.25)
        assert engine.watch_status()[0]["procesados"][0]["estado"] == "ok"
        assert (sal / "salida" / "nuevo").exists()
        with pytest.raises(UserError):
            engine.start_watch("t1", RECETA, ent, sal)
    finally:
        engine.stop_watch("t1")
    assert engine.watch_status() == []


def test_api(carpeta, tmp_path):
    c = TestClient(app)
    assert any(r["id"] == "revision_rapida" for r in c.get("/api/automatizar/recetas").json())
    assert any(s["id"] == "preflight" for s in c.get("/api/automatizar/catalogo").json())
    assert c.post("/api/automatizar/validar", json={"receta": {"nombre": "x", "pasos": [{"accion": "no"}]}}).json()["errores"]
    with open(carpeta / "trabajo0.pdf", "rb") as f:
        jid = c.post("/api/automatizar/ejecutar", files={"file": ("trabajo0.pdf", f, "application/pdf")}, data={"receta_json": json.dumps(RECETA)}).json()["job_id"]
    for _ in range(100):
        st = c.get(f"/api/jobs/{jid}").json()
        if st["status"] != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done" and st["result"]["estado"] == "ok"
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/automatizar/descargar/{jid}").content))
    assert "resumen.txt" in z.namelist()
    j2 = c.post("/api/automatizar/carpeta", json={"receta": RECETA, "entrada": str(carpeta), "salida": str(tmp_path / "s2")}).json()["job_id"]
    for _ in range(200):
        st = c.get(f"/api/jobs/{j2}").json()
        if st["status"] != "running":
            break
        time.sleep(0.3)
    assert st["status"] == "done" and st["result"]["errores"] == 1
    assert c.post("/api/automatizar/carpeta", json={"receta": "revision_rapida", "entrada": str(tmp_path / "no"), "salida": str(tmp_path)}).json()["job_id"]
