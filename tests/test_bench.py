import json
import shutil

from fastapi.testclient import TestClient

from bench import metrics, synth


def _det(cat, bbox):
    return {"category": cat, "bbox": bbox}


def _exp(cat, bbox):
    return {"categoria": cat, "bbox": bbox}


def test_match_counts_tp_fp_fn():
    det = [_det("text", [100, 100, 50, 20]), _det("text", [400, 400, 50, 20]), _det("font", [0, 0, 10, 10])]
    exp = [_exp("text", [102, 101, 48, 20]), _exp("color", [700, 700, 30, 30])]
    c = metrics.case_counts(det, exp)["counts"]
    assert c["text"] == {"tp": 1, "fp": 1, "fn": 0}
    assert c["font"]["fp"] == 1 and c["color"]["fn"] == 1


def test_color_and_visual_are_interchangeable():
    c = metrics.case_counts([_det("visual", [10, 10, 100, 100])], [_exp("color", [20, 20, 80, 80])])["counts"]
    assert c["color"]["tp"] == 1 and c["visual"]["fp"] == 0


def test_prf_and_cer():
    r = metrics.prf(8, 2, 0)
    assert r["precision"] == 80.0 and r["recall"] == 100.0
    assert metrics.cer("Hola mundo", "hola  mundo") == 0
    assert 0 < metrics.cer("Precio 10.000", "Precio 12.000") < 0.2


def test_synthetic_cases_are_reproducible(tmp_path, monkeypatch):
    assert len(synth.DESIGN_KEYS) * len(synth.variants()) >= 60
    monkeypatch.setattr(synth, "DESIGN_KEYS", synth.DESIGN_KEYS[:1])
    a, b = tmp_path / "a", tmp_path / "b"
    assert synth.generate(a, quiet=True) == len(synth.variants())
    synth.generate(b, quiet=True)
    for case in sorted(p.name for p in a.iterdir()):
        ja = json.loads((a / case / "esperado.json").read_text(encoding="utf-8"))
        jb = json.loads((b / case / "esperado.json").read_text(encoding="utf-8"))
        assert ja == jb
        assert (a / case / "cliente.jpg").exists() and (a / case / "diseno.pdf").exists()
    num = next(p for p in a.iterdir() if p.name.endswith("_numero"))
    e = json.loads((num / "esperado.json").read_text(encoding="utf-8"))["errores"]
    assert len(e) == 1 and e[0]["categoria"] == "text" and e[0]["subtipo"] == "cambiada"


def test_save_review_as_case(tmp_path, monkeypatch):
    import app.main as m
    import app.modules.compare.api as capi  # (S0) las rutas de Comparar viven ahora en su propio módulo
    monkeypatch.setattr(capi, "DATOS_DIR", tmp_path / "datos")
    client = TestClient(m.app)
    with open("samples/cliente_errores.png", "rb") as c, open("samples/diseno.pdf", "rb") as d:
        r = client.post("/api/compare", files={"client_file": ("c.png", c), "design_file": ("d.pdf", d)}, params={"wait": 1})
    assert r.status_code == 200
    res = r.json()["result"]
    job = res["job_id"]
    first = res["differences"][0]["id"]
    r2 = client.post(f"/api/cases/{job}", json={
        "verdicts": {str(first): "falso_positivo"},
        "missed": [{"categoria": "text", "bbox": [10, 10, 100, 30], "cliente_dice": "Hola"}],
        "client_text": "Oferta de Verano", "tipo": "exportado"})
    assert r2.status_code == 200, r2.text
    cdir = tmp_path / "datos" / "casos" / "caso_001"
    esp = json.loads((cdir / "esperado.json").read_text(encoding="utf-8"))
    assert esp["texto_cliente"] == "Oferta de Verano"
    assert len(esp["errores"]) == len(res["differences"]) - 1 + 1
    assert (cdir / "cliente.png").exists() and (cdir / "diseno.pdf").exists()
    shutil.rmtree(m.RESULTS_DIR / job, ignore_errors=True)
    shutil.rmtree(m.UPLOADS_DIR / job, ignore_errors=True)


def test_async_job_reports_progress(monkeypatch):
    import time
    import app.main as m
    client = TestClient(m.app)
    with open("samples/cliente_ok.png", "rb") as c, open("samples/diseno.pdf", "rb") as d:
        r = client.post("/api/compare", files={"client_file": ("c.png", c), "design_file": ("d.pdf", d)})
    job = r.json()["job_id"]
    seen = set()
    for _ in range(200):
        st = client.get(f"/api/jobs/{job}").json()
        seen.add(st["stage"])
        if st["status"] != "running":
            break
        time.sleep(0.3)
    assert st["status"] == "done" and st["result"]["status"] == "aprobado"
    assert len(seen) >= 3  # pasó por varias etapas
    shutil.rmtree(m.RESULTS_DIR / job, ignore_errors=True)
    shutil.rmtree(m.UPLOADS_DIR / job, ignore_errors=True)


def test_bad_upload_returns_spanish_error():
    import app.main as m
    client = TestClient(m.app)
    r = client.post("/api/compare", files={"client_file": ("a.txt", b"hola"), "design_file": ("d.pdf", b"x")})
    assert r.status_code == 400 and "Formato no admitido" in r.json()["detail"]
