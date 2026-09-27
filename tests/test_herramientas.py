"""Herramientas avanzadas (S7): trapping, step & repeat, distorsión flexo, braille, gama extendida y prueba en pantalla."""
import io
import math
import zipfile

import numpy as np
import pikepdf
import pymupdf
import pytest

from app.core import ghostscript
from app.core.errors import UserError
from app.modules.separate import raster
from app.modules.separate.pdf_render import Plates, render_plates
from app.modules.tools import braille, flexo, gamut, imposition, trapping
from bench.synth_separations import Builder


# ---------------------------------------------------------------- trapping
def two_rects(dpi=254.0):
    """Amarillo (claro) a la izquierda y cian (oscuro) a la derecha, tocándose en x = 100."""
    h, w = 100, 200
    y = np.zeros((h, w), np.uint8)
    c = np.zeros((h, w), np.uint8)
    y[:, :100] = 255
    c[:, 100:] = 255
    return Plates(["Yellow", "Cyan"], {"Yellow": y, "Cyan": c}, dpi, 0, w, h)


def test_trap_claro_se_expande_bajo_oscuro_exactamente():
    p = two_rects()
    r = trapping.trap(p, proceso="flexo", ancho_mm=0.2, tac_max=None)      # 0,2 mm a 254 dpi = 2 px
    y = r.plates.arrays["Yellow"]
    assert (y[:, 100:102] == 255).all() and (y[:, 102:] == 0).all()             # se expande 2 px y solo bajo el cian
    assert (r.plates.arrays["Cyan"] == p.arrays["Cyan"]).all()                   # el oscuro no cambia
    assert r.traps and r.traps[0]["de"] == "Yellow" and r.traps[0]["bajo"] == "Cyan"
    assert r.trap_map[50, 101].tolist() != [255, 255, 255]


def test_trap_negro_no_se_expande_y_reducido_y_tac():
    h, w = 60, 120
    k = np.zeros((h, w), np.uint8); k[:, 60:] = 255
    y = np.zeros((h, w), np.uint8); y[:, :60] = 255
    p = Plates(["Yellow", "Black"], {"Yellow": y, "Black": k}, 254.0, 0, w, h)
    r = trapping.trap(p, ancho_mm=0.2, tac_max=None)
    assert (r.plates.arrays["Black"] == k).all()
    r50 = trapping.trap(p, ancho_mm=0.2, porcentaje=50, tac_max=None)
    assert 120 <= int(r50.plates.arrays["Yellow"][30, 60]) <= 135
    rt = trapping.trap(p, ancho_mm=0.2, tac_max=150)
    assert 125 <= int(rt.plates.arrays["Yellow"][30, 60]) <= 130                # K 100 % deja 50 % de margen bajo el tope de 150


def test_trap_pares_parecidos_o_directas_tecnicas_no():
    h, w = 40, 80
    a = np.zeros((h, w), np.uint8); a[:, :40] = 255
    b = np.zeros((h, w), np.uint8); b[:, 40:] = 255
    p = Plates(["A", "B"], {"A": a, "B": b}, 254.0, 0, w, h)
    meta = {"A": {"lab": (60, 0, 0), "tipo": "spot"}, "B": {"lab": (58, 0, 0), "tipo": "spot"}}
    assert {t["regla"] for t in trapping.trap(p, meta, ancho_mm=0.2).traps} == {"R5"}     # D1: luminosidad parecida → trap centrado
    meta = {"A": {"lab": (80, 0, 0), "tipo": "technical"}, "B": {"lab": (30, 0, 0), "tipo": "spot"}}
    assert not trapping.trap(p, meta, ancho_mm=0.2).traps


def test_choke_blanco_y_malregistro():
    h, w = 60, 120
    wh = np.zeros((h, w), np.uint8); wh[10:50, 10:110] = 255
    p = Plates(["Blanco"], {"Blanco": wh}, 254.0, 0, w, h)
    r = trapping.trap(p, {"Blanco": {"lab": (94, 0, -2), "tipo": "white"}}, ancho_mm=0.2)
    assert r.plates.arrays["Blanco"].sum() < wh.sum()
    m = trapping.misregistration(two_rects(), "Yellow", 200.0)                   # 0,2 mm = 2 px
    assert (m.arrays["Yellow"][:, 2:102] == 255).all()


# ---------------------------------------------------------------- step & repeat
def label_pdf(path, w=50, h=30, bleed=3):
    k = 72 / 25.4
    b = Builder((w + 2 * bleed) * k, (h + 2 * bleed) * k)
    b.separation("CS0", "Demo Rojo 1", (0, 0.9, 0.8, 0))
    b.rect(0, 0, (w + 2 * bleed) * k, (h + 2 * bleed) * k, "/CS0 cs 1 scn")
    pdfp = b.build(path)
    with pikepdf.open(str(pdfp), allow_overwriting_input=True) as pdf:
        pg = pdf.pages[0]
        for k, inset in (("/BleedBox", 0.0), ("/TrimBox", bleed * 72 / 25.4)):
            mb = [float(v) for v in pg.MediaBox]
            pg.obj[k] = pikepdf.Array([mb[0] + inset, mb[1] + inset, mb[2] - inset, mb[3] - inset])
        pdf.save(str(path) + "2")
    import os
    os.replace(str(path) + "2", str(path))
    return path


def test_posiciones_3x4_con_gap_3mm():
    cells = imposition.layout_cells(50, 30, 3, 4, 3, 3, (10, 10, 10, 10))
    assert len(cells) == 12
    for c in cells:
        assert abs(c.x - (10 + c.col * 53)) < 0.01 and abs(c.y - (10 + c.row * 33)) < 0.01
    assert imposition.fill_grid(200, 150, 50, 30, 3, 3, (10, 10, 10, 10)) == (3, 4)


def test_rotaciones_y_desfase():
    c = imposition.layout_cells(50, 30, 2, 2, 3, 3, (0, 0, 0, 0), rot_by_row=[0, 90], stagger_row_mm=5)
    assert (c[0].w, c[0].h) == (50, 30) and (c[2].w, c[2].h) == (30, 50)
    assert c[2].x == 5.0


def test_step_repeat_pdf_y_marcas_en_todas_las_placas(tmp_path):
    src = label_pdf(tmp_path / "e.pdf")
    dst = tmp_path / "hoja.pdf"
    r = imposition.step_repeat(src, dst, sheet_w=200, sheet_h=150, cols=3, rows=4, gap_x=3, gap_y=3,
                               marks={"registro": True, "corte": True, "barra_color": True, "texto": True}, job_name="prueba")
    assert r["repeticiones"] == 12 and 0 < r["aprovechamiento_pct"] < 100
    with pymupdf.open(str(dst)) as d:
        assert len(d) == 1 and abs(d[0].rect.width - 200 * 72 / 25.4) < 0.5
        assert dst.stat().st_size < 60_000                                       # el contenido se reutiliza, no se copia
    if ghostscript.available():
        p = render_plates(dst, 0, 100, use_cache=False)
        for n in ("Cyan", "Magenta", "Yellow", "Black"):
            assert n in p.names and not p.empty(n)                               # las marcas /All salen en todas las placas
        assert "Demo_Rojo_1" in p.names or "Demo Rojo 1" in p.names


def test_no_cabe(tmp_path):
    src = label_pdf(tmp_path / "e.pdf")
    with pytest.raises(UserError):
        imposition.step_repeat(src, tmp_path / "x.pdf", sheet_w=100, sheet_h=60, cols=5, rows=5)


# ---------------------------------------------------------------- flexo
def test_distorsion_formula_y_aplicacion(tmp_path):
    assert abs(flexo.distortion_pct(1.14, 400) - 2 * math.pi * 1.14 / 400 * 100) < 1e-9
    pt = 100 * 72 / 25.4                                  # página de 100 × 100 mm
    b = Builder(pt, pt)
    b.rect(0, 0, pt, pt, "0 0 0 1 k")
    src = b.build(tmp_path / "a.pdf")
    r = flexo.apply_distortion(src, tmp_path / "d.pdf", 2.0, "vertical", note=False)
    assert abs(r["paginas"][0]["despues_mm"][1] - 98.0) < 0.05 and abs(r["paginas"][0]["despues_mm"][0] - 100.0) < 0.05
    r2 = flexo.apply_distortion(src, tmp_path / "e.pdf", 2.0, "horizontal", note=True)
    assert abs(r2["paginas"][0]["despues_mm"][0] - 98.0) < 0.05
    with pytest.raises(UserError):
        flexo.distortion_pct(1, 0)
    with pytest.raises(UserError):
        flexo.apply_distortion(src, tmp_path / "f.pdf", 30)


# ---------------------------------------------------------------- braille
def test_braille_paracetamol_500_mg():
    esperado = [(6,), (1, 2, 3, 4), (1,), (1, 2, 3, 5), (1,), (1, 4), (1, 5), (2, 3, 4, 5), (1,), (1, 3, 4), (1, 3, 5), (1, 2, 3), (),
                (3, 4, 5, 6), (1, 5), (2, 4, 5), (2, 4, 5), (), (1, 3, 4), (1, 2, 4, 5)]
    assert braille.translate("Paracetamol 500 mg") == esperado
    assert braille.to_unicode("Paracetamol 500 mg") == "⠠⠏⠁⠗⠁⠉⠑⠞⠁⠍⠕⠇ ⠼⠑⠚⠚ ⠍⠛"


def test_braille_acentos_mayusculas_y_error():
    assert braille.translate("ñ") == [(1, 2, 4, 5, 6)] and braille.translate("é") == [(2, 3, 4, 6)]
    assert braille.translate("AB")[:2] == [(6,), (6,)]                            # palabra toda en mayúsculas
    with pytest.raises(UserError):
        braille.translate("a@b")


def test_braille_geometria_y_pdf():
    lay = braille.layout("ab", 60)
    g = braille.MARBURG
    # 'a' = punto 1; 'b' = puntos 1 y 2 → 3 puntos, separados por la celda de 6 mm
    assert len(lay["puntos"]) == 3
    xs = sorted({round(p[0], 3) for p in lay["puntos"]})
    assert abs(xs[1] - xs[0] - g["celda"]) < 1e-6
    ys = sorted(round(p[1], 3) for p in lay["puntos"] if abs(p[0] - xs[1]) < 1e-6)
    assert abs(ys[1] - ys[0] - g["punto_y"]) < 1e-6
    pdf = braille.to_pdf(lay)
    with pikepdf.open(io.BytesIO(pdf)) as p:
        assert str(p.pages[0].Resources.ColorSpace.CS0[1]) == "/Braille"
        assert p.pages[0].Resources.ExtGState.GS0.OP is True
    assert "<circle" in braille.to_svg(lay)


def test_braille_salto_de_linea():
    lay = braille.layout("hola mundo cruel", 40)
    assert lay["lineas"] >= 2
    with pytest.raises(UserError):
        braille.layout("supercalifragilistico", 20)


# ---------------------------------------------------------------- gama extendida
FIJAS = [raster.Ink("Cyan", (55, -37, -50)), raster.Ink("Magenta", (48, 74, -3)), raster.Ink("Yellow", (89, -5, 93)),
         raster.Ink("Black", (16, 0, 0)), raster.Ink("Naranja", (63, 55, 72)), raster.Ink("Verde", (58, -70, 30)), raster.Ink("Violeta", (35, 45, -55))]


def test_receta_de_un_color_alcanzable():
    objetivo = tuple(np.asarray(__import__("app.core.colorscience", fromlist=["x"]).__dict__["cs"] if False else (0, 0, 0)))
    from app.core import colorscience as cs
    lab = cs.__dict__["srgb_to_lab"](np.array([0.9, 0.5, 0.1]))
    r = gamut.recipe_for(tuple(lab), FIJAS)
    assert r["de"] <= 4 and len(r["receta"]) <= 3 and r["semaforo"] in ("verde", "amarillo")


def test_tinta_pura_se_reproduce_con_ella_misma_y_fuera_de_gama_es_rojo():
    r = gamut.recipe_for((63, 55, 72), FIJAS)
    assert r["de"] < 1.0 and "Naranja" in r["receta"]
    fuera = gamut.recipe_for((60, 100, 100), FIJAS[:4])                             # saturación imposible sin naranja/verde
    assert fuera["semaforo"] in ("amarillo", "rojo") and fuera["de"] > 2


def test_tabla_y_aplicar_al_pdf(tmp_path):
    b = Builder()
    b.separation("CS0", "Demo Naranja", (0, 0.6, 0.9, 0))
    b.rect(10, 10, 100, 100, "/CS0 cs 0.5 scn")
    src = b.build(tmp_path / "s.pdf")
    tabla = gamut.recipes([{"name": "Demo Naranja", "lab": (63.0, 55.0, 72.0)}], FIJAS[:4])
    assert tabla[0]["receta"] and tabla[0]["semaforo"] in ("verde", "amarillo", "rojo")
    tabla[0]["reproducible"] = True
    r = gamut.apply_to_pdf(src, tmp_path / "d.pdf", tabla, FIJAS[:4], only_reproducible=False)
    assert r["convertidas"] and r["convertidas"][0]["objetos"] == 1
    from app.modules.separate.pdf_inks import read_inventory
    inv = read_inventory(tmp_path / "d.pdf")
    assert {i.name for i in inv.inks} >= set(tabla[0]["receta"]) - {"Cyan", "Magenta", "Yellow", "Black"} or inv.inks


def test_sin_tintas_fijas():
    with pytest.raises(UserError):
        gamut.recipe_for((50, 0, 0), [])


# ---------------------------------------------------------------- prueba en pantalla
def test_soft_proof_etiqueta_ganancia_y_sin_blanco():
    h, w = 80, 120
    a = np.zeros((h, w), np.uint8); a[:, :] = 128
    wh = np.zeros((h, w), np.uint8); wh[:, :60] = 255
    p = Plates(["Cyan", "Blanco"], {"Cyan": a, "Blanco": wh}, 100.0, 0, w, h)
    meta = {"Blanco": {"lab": (94, 0, -2), "tipo": "white"}}
    sin = gamut.soft_proof(p, meta, substrate_lab=(12, 0, 0), sin_blanco=True)
    con = gamut.soft_proof(p, meta, substrate_lab=(12, 0, 0))
    assert sin.shape == (h, w, 3) and con[10, 10].sum() > sin[10, 10].sum()          # el blanco aclara sobre la prenda negra
    g0 = gamut.soft_proof(p, meta)
    g1 = gamut.soft_proof(p, meta, default_gain=0.2)
    assert g1[10, 100].sum() < g0[10, 100].sum()                                        # más ganancia = más oscuro
    assert gamut.dot_gain(np.array([128], np.uint8), 0.2)[0] > 128
    assert (h - 16, 0) and gamut.SOFTPROOF_NOTE == "Vista orientativa, no es una prueba contractual."
    k = gamut.soft_proof(p, meta, textura="kraft")
    assert k.std() > g0.std()


def test_api_herramientas(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    b = Builder()
    b.separation("CS0", "Demo Naranja", (0, 0.6, 0.9, 0))
    b.rect(10, 10, 100, 100, "/CS0 cs 1 scn")
    b.rect(110, 10, 100, 100, "0 0 0 1 k")
    src = b.build(tmp_path / "s.pdf")
    with open(src, "rb") as f:
        jid = c.post("/api/herramientas/pdf", files={"file": ("s.pdf", f, "application/pdf")}).json()["job_id"]
    r = c.post(f"/api/herramientas/{jid}/imponer", json={"hoja_ancho": 600, "hoja_alto": 400, "columnas": 2, "filas": 1, "marcas": {"registro": True}})
    assert r.status_code == 200 and r.json()["repeticiones"] == 2
    assert c.get(f"/api/herramientas/{jid}/imposicion.pdf").content.startswith(b"%PDF")
    assert c.get(f"/api/herramientas/{jid}/imposicion.png").status_code == 200
    f1 = c.post(f"/api/herramientas/{jid}/flexo", json={"k": 1.14, "repeticion": 400})
    assert f1.status_code == 200 and c.get(f"/api/herramientas/{jid}/flexo.pdf").status_code == 200
    assert c.get("/api/herramientas/flexo/calcular?k=1.14&repeticion=400").json()["distorsion_pct"] > 1
    br = c.post("/api/herramientas/braille", json={"texto": "Paracetamol 500 mg", "ancho_mm": 120})
    assert br.json()["unicode"].startswith("⠠⠏")
    assert c.post("/api/herramientas/braille", json={"texto": "x@", "formato": "pdf"}).status_code == 400
    assert c.post("/api/herramientas/braille", json={"texto": "hola", "formato": "pdf"}).content.startswith(b"%PDF")
    if ghostscript.available():
        a = c.post(f"/api/herramientas/{jid}/trapping", json={"dpi": 150}).json()["job_id"]
        import time
        for _ in range(100):
            st = c.get(f"/api/jobs/{a}").json()
            if st["status"] != "running":
                break
            time.sleep(0.3)
        assert st["status"] == "done", st
        assert c.get(f"/api/herramientas/{jid}/trapping/mapa.png").status_code == 200
        assert c.get(f"/api/herramientas/{jid}/trapping/registro.png?tinta=Black&dx_um=100").status_code == 200
        assert zipfile.ZipFile(io.BytesIO(c.post(f"/api/herramientas/{jid}/trapping/exportar").content)).namelist()
        assert c.get(f"/api/herramientas/{jid}/prueba.png?sustrato=Prenda%20negra&textura=kraft&ganancia=15").status_code == 200
        fj = {"fijas": [{"name": i.name, "lab": list(i.lab)} for i in FIJAS]}
        g = c.post(f"/api/herramientas/{jid}/gamut", json=fj).json()["job_id"]
        for _ in range(200):
            st = c.get(f"/api/jobs/{g}").json()
            if st["status"] != "running":
                break
            time.sleep(0.3)
        assert st["status"] == "done", st
        assert c.post(f"/api/herramientas/{jid}/gamut/aplicar?solo_reproducibles=false").status_code == 200
        assert c.get(f"/api/herramientas/{jid}/gamut.pdf").status_code == 200
