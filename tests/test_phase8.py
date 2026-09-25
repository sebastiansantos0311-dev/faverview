import json
import shutil
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import ignore_zones
from app.config import setup_tesseract
from app.models import Difference, Result
from make_samples import make_pdf

needs_ocr = pytest.mark.skipif(setup_tesseract() is None, reason="Tesseract no instalado")


def _diff(cat, bbox, **kw):
    return Difference(category=cat, bbox=bbox, **kw)


# ------------------------------------------------------------------------------------------ 8.1 zonas
@pytest.fixture()
def plantillas(tmp_path, monkeypatch):
    monkeypatch.setattr(ignore_zones, "DATOS_DIR", tmp_path)
    return tmp_path


def test_zone_modes_only_hide_what_they_should():
    W, H = 1000, 1000
    z_all = [{"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5, "modo": "todo"}]
    z_col = [{"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5, "modo": "color"}]
    z_txt = [{"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5, "modo": "texto"}]
    inside = (100, 100, 50, 50)
    outside = (700, 700, 50, 50)
    assert ignore_zones.affected(_diff("text", inside), z_all, W, H)
    assert not ignore_zones.affected(_diff("text", outside), z_all, W, H)
    assert ignore_zones.affected(_diff("color", inside), z_col, W, H)
    assert not ignore_zones.affected(_diff("text", inside), z_col, W, H)
    assert ignore_zones.affected(_diff("spelling", inside), z_txt, W, H)
    assert not ignore_zones.affected(_diff("color", inside), z_txt, W, H)


def test_templates_roundtrip_and_suggestions(plantillas):
    ignore_zones.save_template("Cliente Pérez – volante", [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "modo": "color"}],
                               1653, 2339)
    assert [t["nombre"] for t in ignore_zones.list_templates()] == ["Cliente Pérez – volante"]
    t = ignore_zones.load_template("Cliente Pérez – volante")
    assert t["zonas"][0]["modo"] == "color"
    assert ignore_zones.suggest("arte_cliente pérez – volante_v2.png", None, None)
    assert ignore_zones.suggest("otro.png", 1650, 2340) == ["Cliente Pérez – volante"]  # por tamaño
    assert not ignore_zones.suggest("otro.png", 800, 600)
    with pytest.raises(ValueError):
        ignore_zones.save_template("   ", [])
    ignore_zones.delete_template("Cliente Pérez – volante")
    assert not ignore_zones.list_templates()


@needs_ocr
def test_ignored_zone_does_not_count_in_scores(tmp_path):
    from app.pipeline import run_comparison
    base = run_comparison("t_z0", "samples/cliente_errores.png", "samples/diseno.pdf", persist=False, out_dir=tmp_path / "a")
    price = next(d for d in base.differences if d.category == "text" and d.subtype == "cambiada")
    x, y, w, h = price.bbox
    zone = {"x": (x - 5) / base.width, "y": (y - 5) / base.height, "w": (w + 10) / base.width,
            "h": (h + 10) / base.height, "modo": "todo"}
    r = run_comparison("t_z1", "samples/cliente_errores.png", "samples/diseno.pdf", {"zones": [zone]}, persist=False,
                       out_dir=tmp_path / "b")
    ign = [d for d in r.differences if d.ignored_by_zone]
    assert any(d.category == "text" and d.subtype == "cambiada" for d in ign)
    assert r.scores["text"] > base.scores["text"]
    assert r.counts.get("text", 0) < base.counts.get("text", 0)


# ------------------------------------------------------------------------------------------ 8.3 versiones
def test_versions_compare_exact_text_fonts_and_colors(tmp_path):
    from app.versions import run_versions, verify_corrections
    v1, v2 = tmp_path / "v1.pdf", tmp_path / "v2.pdf"
    make_pdf(v1, price="Precio 10.000", title="Gran Oferta Especial Verano", title_size=30)
    make_pdf(v2, price="Precio 12.000", title="Gran Oferta Especial Verano", title_size=38, rect=(0.85, 0.45, 0.10))
    r = run_versions("t_v", v1, v2, persist=False, out_dir=tmp_path / "o")
    cats = {(d.category, d.subtype) for d in r.differences}
    assert ("text", "cambiada") in cats and ("font", "version") in cats
    assert any(d.category == "color" for d in r.differences)
    price = next(d for d in r.differences if d.subtype == "cambiada")
    assert "v1 dice" in price.message and "v2 dice" in price.message
    assert r.mode == "versiones"

    # verificar correcciones: v3 corrige el precio pero deja el cambio de fuente
    v3 = tmp_path / "v3.pdf"
    make_pdf(v3, price="Precio 10.000", title="Gran Oferta Especial Verano", title_size=38, rect=(0.1, 0.45, 0.8))
    r2 = run_versions("t_v2", v1, v3, persist=False, out_dir=tmp_path / "o2")
    fix = verify_corrections(r, r2)
    assert any(c["message"].startswith("Texto cambiado") or "Texto" in c["message"] for c in fix["corregidos"])
    assert any(p["category"] == "font" for p in fix["persisten"])


def test_verify_corrections_matches_by_position():
    from app.versions import verify_corrections
    mk = lambda i, cat, bb, **kw: Difference(id=i, category=cat, bbox=bb, message=f"m{i}", **kw)
    prev = Result(job_id="a", width=1, height=1, aligned=True, alignment_quality=1, scores={}, status="revisar",
                  differences=[mk(1, "text", (10, 10, 50, 20)), mk(2, "color", (200, 200, 80, 80)),
                               mk(3, "font", (400, 10, 60, 20), status="no_aplica")])
    new = Result(job_id="b", width=1, height=1, aligned=True, alignment_quality=1, scores={}, status="revisar",
                 differences=[mk(1, "color", (205, 205, 70, 70), status="pendiente"), mk(2, "spelling", (600, 600, 30, 10))])
    fix = verify_corrections(prev, new)
    assert [c["id"] for c in fix["corregidos"]] == [1]   # el error de texto ya no está
    assert [p["id"] for p in fix["persisten"]] == [2]    # el de color sigue
    assert fix["nuevos"] == [2]                           # aparece uno nuevo (ortografía)


# ------------------------------------------------------------------------------------------ 8.4 lote
def _pdf_pages(path: Path, prices: list[str]):
    doc = pymupdf.open()
    for i, pr in enumerate(prices):
        tmp = path.parent / f"_p{i}.pdf"
        make_pdf(tmp, price=pr, title=f"Pagina numero {i + 1} especial")
        with pymupdf.open(tmp) as sub:
            doc.insert_pdf(sub)
        tmp.unlink()
    doc.save(path)
    doc.close()


def test_pages_are_paired_by_similarity_when_counts_differ(tmp_path):
    from app.batch import pair_pages
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    doc = pymupdf.open()
    for fill, txt in (((0.9, 0.1, 0.1), "uno"), ((0.1, 0.8, 0.1), "dos"), ((0.1, 0.1, 0.9), "tres")):
        p = doc.new_page(width=595, height=842)
        p.draw_rect(pymupdf.Rect(50, 100, 545, 400), color=None, fill=fill)
        p.insert_text((60, 500), txt, fontsize=30)
    doc.save(a)
    doc2 = pymupdf.open()
    doc2.insert_pdf(doc, from_page=1, to_page=2)  # solo las páginas 2 y 3
    doc2.save(b)
    pairs, sin_c, sin_d = pair_pages(a, b)
    assert pairs == [(1, 0), (2, 1)] and sin_c == [0] and sin_d == []


@needs_ocr
def test_batch_compares_every_page_and_builds_merged_report(tmp_path, monkeypatch):
    import app.batch as batch
    from app.config import RESULTS_DIR
    c, d = tmp_path / "c.pdf", tmp_path / "d.pdf"
    _pdf_pages(c, ["Precio 10.000", "Precio 20.000"])
    _pdf_pages(d, ["Precio 10.000", "Precio 25.000"])
    s = batch.run_batch("b" * 12, c, d, "c.pdf", "d.pdf", None)
    try:
        assert len(s["paginas"]) == 2
        assert s["paginas"][0]["total"] > s["paginas"][1]["total"]
        assert s["paginas"][1]["errores"] >= 1
        out = tmp_path / "lote.pdf"
        batch.merge_reports("b" * 12, out)
        with pymupdf.open(out) as doc:
            assert doc.page_count >= 1 + 2 * 3
    finally:
        for p in [RESULTS_DIR / ("b" * 12)] + [RESULTS_DIR / r["job_id"] for r in s["paginas"]]:
            shutil.rmtree(p, ignore_errors=True)


# ------------------------------------------------------------------------------------------ 8.5 checklist
@needs_ocr
def test_checklist_marks_ready_and_report_includes_state():
    import app.main as m
    client = TestClient(m.app)
    with open("samples/cliente_errores.png", "rb") as c, open("samples/diseno.pdf", "rb") as d:
        r = client.post("/api/compare", files={"client_file": ("c.png", c), "design_file": ("d.pdf", d)}, params={"wait": 1})
    res = r.json()["result"]
    job = res["job_id"]
    try:
        n = len(res["differences"])
        assert client.patch(f"/api/results/{job}/checklist", json={"items": {}}).json()["pendientes"] == n
        items = {str(d["id"]): {"status": "corregido" if i else "no_aplica", "comment": "ok" if i == 0 else ""}
                 for i, d in enumerate(res["differences"])}
        out = client.patch(f"/api/results/{job}/checklist", json={"items": items}).json()
        assert out["listo"] and out["pendientes"] == 0
        saved = Result.model_validate_json((m.RESULTS_DIR / job / "result.json").read_text(encoding="utf-8"))
        assert saved.differences[0].status == "no_aplica" and saved.differences[0].comment == "ok"
        rep = client.get(f"/api/report/{job}")
        assert rep.status_code == 200
        out_pdf = m.RESULTS_DIR / job / "t.pdf"
        out_pdf.write_bytes(rep.content)
        with pymupdf.open(out_pdf) as doc:
            assert "Listo para enviar" in doc[0].get_text()
    finally:
        shutil.rmtree(m.RESULTS_DIR / job, ignore_errors=True)
        shutil.rmtree(m.UPLOADS_DIR / job, ignore_errors=True)


@needs_ocr
def test_compare_fix_reports_corrected_errors(tmp_path):
    """Sube un diseño corregido contra el mismo arte del cliente: los errores previos quedan como corregidos."""
    import app.main as m
    client = TestClient(m.app)
    fixed = tmp_path / "corregido.pdf"
    make_pdf(fixed, price="Precio 12.000", paragraph_drop="especiales", rect=(0.85, 0.45, 0.10), logo=False)
    jobs = []
    try:
        with open("samples/cliente_errores.png", "rb") as c, open("samples/diseno.pdf", "rb") as d:
            r1 = client.post("/api/compare", files={"client_file": ("c.png", c), "design_file": ("d.pdf", d)},
                             params={"wait": 1}).json()
        jobs.append(r1["job_id"])
        n_prev = len(r1["result"]["differences"])
        with open(fixed, "rb") as f:
            r2 = client.post("/api/compare-fix", data={"previous_job_id": r1["job_id"]},
                             files={"design_file": ("corregido.pdf", f)}, params={"wait": 1}).json()
        jobs.append(r2["job_id"])
        fix = r2["result"]["fix_report"]
        assert len(fix["corregidos"]) >= n_prev - 1 and len(fix["nuevos"]) <= 1
        assert r2["result"]["scores"]["total"] > r1["result"]["scores"]["total"]
        assert "corregidos" in fix["resumen"]
    finally:
        for j in jobs:
            shutil.rmtree(m.RESULTS_DIR / j, ignore_errors=True)
            shutil.rmtree(m.UPLOADS_DIR / j, ignore_errors=True)
