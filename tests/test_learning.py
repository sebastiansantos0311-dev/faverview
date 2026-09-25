import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from app.compare_text import Word
from app.config import load_config, setup_tesseract
from app.learning import confusions, portability, store, tuning, vocab
from app.learning.imagetype import classify
from app.models import Difference, Result

needs_ocr = pytest.mark.skipif(setup_tesseract() is None, reason="Tesseract no instalado")


@pytest.fixture()
def datos(tmp_path, monkeypatch):
    """Aísla datos_locales en una carpeta temporal."""
    import app.config as config
    import app.learning.tuning as tun
    monkeypatch.setattr(config, "DATOS_DIR", tmp_path)
    monkeypatch.setattr(store, "DATOS_DIR", tmp_path)
    monkeypatch.setattr(tun, "DATOS_DIR", tmp_path)
    vocab._cache["mtime"] = None
    return tmp_path


def test_confusion_needs_three_sightings_and_never_hides_digit_changes(datos):
    assert not confusions.explains("Preclo", "Precio", 3)
    for _ in range(3):
        confusions.add_pair("Preclo", "Precio")
    assert confusions.explains("Preclo", "Precio", 3)
    assert confusions.explains("Preclo", "Precio", 4) is False  # aún no se vio 4 veces
    # regla de seguridad: dígito ↔ dígito no se aprende ni se explica jamás
    for _ in range(5):
        confusions.add_pair("12.000", "10.000")
    assert not confusions.explains("12.000", "10.000", 1)
    assert "2>0" not in confusions.load()["pares"]


def test_learned_vocabulary_avoids_brand_spelling_flag(datos):
    from app.spelling import check_spelling
    w = Word("Zyxxoria", (0, 0, 50, 20))
    assert [d.found for d in check_spelling([w])[0]] == ["Zyxxoria"]
    vocab.add_words(["zyxxoria"])
    assert not check_spelling([w])[0]


def test_vocab_from_review_skips_confirmed_typos(datos):
    res = Result(job_id="x", width=1, height=1, aligned=True, alignment_quality=1, scores={}, status="aprobado",
                 differences=[Difference(category="spelling", bbox=(0, 0, 1, 1), found="ofertaa", review="real")],
                 pages={"design": 1})
    import fitz  # noqa
    import pymupdf
    pdf = datos / "d.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 100), "Zyxxoria ofertaa nueva")
    doc.save(pdf)
    vocab.add_from_review(res, pdf)
    known = vocab.known_words()
    assert "zyxxoria" in known and "ofertaa" not in known
    assert "--user-words" in vocab.ocr_extra_config()


def test_export_import_roundtrip_without_client_images(datos):
    vocab.add_words(["marcaexclusiva"], 4)
    confusions.add_pair("rn", "m")
    (store.path("lineas")).mkdir(exist_ok=True)
    (store.path("lineas") / "a.png").write_bytes(b"png")
    data = portability.export_zip(include_lines=False)
    import zipfile, io
    assert not [n for n in zipfile.ZipFile(io.BytesIO(data)).namelist() if n.startswith("lineas/")]
    added = portability.import_zip(data)
    assert added["vocabulario"] >= 1
    assert vocab.counts()["marcaexclusiva"] == 8  # frecuencias sumadas
    assert portability.import_zip(portability.export_zip(True))["lineas"] == 1
    with pytest.raises(Exception):
        portability.import_zip(b"no es un zip")


def test_image_type_rules(tmp_path):
    png = tmp_path / "a.png"
    Image.new("RGB", (1200, 800), "white").save(png)
    assert classify(png) == "exportado"
    wa = tmp_path / "wa.jpg"
    Image.new("RGB", (1600, 1200), "white").save(wa, "JPEG", quality=60)
    assert classify(wa) == "whatsapp"
    assert classify(png, framed=True) == "captura"
    assert classify(png, illumination_fixed=True) == "foto"
    tif = tmp_path / "s.tif"
    Image.new("RGB", (800, 600), "white").save(tif)
    assert classify(tif) == "escaneo"


@needs_ocr
def test_tuning_collects_reviewed_lines_and_measures_cer(datos):
    src = Path("tests/sinteticos/sint_001_d1_identico")
    dst = datos / "casos" / "caso_001"
    shutil.copytree(src, dst)
    exp = json.loads((dst / "esperado.json").read_text(encoding="utf-8"))
    exp["tipo"] = "exportado"
    (dst / "esperado.json").write_text(json.dumps(exp), encoding="utf-8")
    groups = tuning.collect_samples(None, max_per_case=5)
    assert len(groups["exportado"]) == 5
    from app.ocr_guided import DEFAULT_TUNE
    cer = tuning.evaluate(dict(DEFAULT_TUNE), groups["exportado"], load_config())
    assert cer < 0.15


@needs_ocr
def test_reviewed_case_feeds_learning_and_line_export(datos, monkeypatch):
    """Guardar un caso revisado alimenta vocabulario, confusiones y recortes para entrenar."""
    from fastapi.testclient import TestClient
    import app.main as m
    monkeypatch.setattr(m, "DATOS_DIR", datos)
    client = TestClient(m.app)
    with open("samples/cliente_errores.png", "rb") as c, open("samples/diseno.pdf", "rb") as d:
        r = client.post("/api/compare", files={"client_file": ("c.png", c), "design_file": ("d.pdf", d)},
                        params={"wait": 1})
    res = r.json()["result"]
    ver = {str(x["id"]): "real" for x in res["differences"]}
    r2 = client.post(f"/api/cases/{res['job_id']}", json={"verdicts": ver, "missed": [], "tipo": "exportado"})
    assert r2.status_code == 200
    st = store.state()
    assert st["casos_revisados"] == 1 and st["lineas_guardadas"] > 0
    assert len(list((store.path("lineas")).glob("*.gt.txt"))) == st["lineas_guardadas"]
    shutil.rmtree(m.RESULTS_DIR / res["job_id"], ignore_errors=True)
    shutil.rmtree(m.UPLOADS_DIR / res["job_id"], ignore_errors=True)


def test_tuning_needs_pipeline_confirmation(monkeypatch):
    """Un ajuste que mejora el CER por línea pero empeora el pipeline completo NO se adopta."""
    from app.ocr_guided import DEFAULT_TUNE
    samples = [(None, None, 1.0, f"caso_{i}") for i in range(9)]

    def fake_eval(params, samples_, cfg, extra=""):
        return 0.10 if params == DEFAULT_TUNE else 0.05  # cualquier ajuste «mejora» por línea

    monkeypatch.setattr(tuning, "evaluate", fake_eval)
    monkeypatch.setattr("app.learning.vocab.ocr_extra_config", lambda: "")
    monkeypatch.setattr(tuning, "OPTIONS", {"target_px": [40, 60]})
    worse = {"base": {"err": 1, "cer": 0.01}, "nuevo": {"err": 3, "cer": 0.02}}
    monkeypatch.setattr(tuning, "pipeline_guard", lambda *a, **k: worse)
    assert tuning.tune_type("foto", samples, log=lambda *_: None)["adoptado"] is False
    better = {"base": {"err": 3, "cer": 0.02}, "nuevo": {"err": 1, "cer": 0.01}}
    monkeypatch.setattr(tuning, "pipeline_guard", lambda *a, **k: better)
    res = tuning.tune_type("foto", samples, log=lambda *_: None)
    assert res["adoptado"] is True and res["params"]["target_px"] == 40


def test_tuning_needs_several_cases(datos, monkeypatch):
    lines = [(None, None, 1.0, "caso_001")] * 20  # muchas líneas pero de un solo caso
    monkeypatch.setattr(tuning, "collect_samples", lambda tipo: {"foto": lines})
    res = tuning.autotune(log=lambda *_: None)
    assert "pocos datos" in res["foto"]["estado"]
