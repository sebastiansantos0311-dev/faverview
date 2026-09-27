"""Auto-trap (AUTOTRAP T0–T2): perfiles de máquina, reglas R1–R12, prueba de movimiento y regresiones D1–D5."""
import numpy as np
import pytest

from app.core import press as pr
from app.core.errors import UserError
from app.core.press import PressProfile
from app.modules.separate.pdf_render import Plates
from app.modules.tools import registration_check as rc
from app.modules.tools import trapping as t

DPI = 254.0          # 10 px por mm


def plates_lr(a="A", b="B", w=200, h=100, x=100):
    A = np.zeros((h, w), np.uint8)
    B = A.copy()
    A[:, :x] = 255
    B[:, x:] = 255
    return Plates([a, b], {a: A, b: B}, DPI, 0, w, h)


def M(labs, tipos=None, op=None):
    return {n: {"lab": lab, "tipo": (tipos or {}).get(n, "spot"), **({"opacity": op[n]} if op and n in op else {})} for n, lab in labs.items()}


PRESS = PressProfile(tolerancia_mm=0.2)


def test_perfiles_de_ejemplo_y_reglas_de_ancho(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "PRESS_DIR", tmp_path)
    ids = {p["id"] for p in pr.list_profiles()}
    assert {"serigrafia_textil_manual", "flexo_banda_angosta", "offset_pliego", "digital"} <= ids
    assert pr.load("serigrafia_textil_manual").tolerancia_mm == 0.40
    p = PressProfile(tolerancia_mm=0.2, factor_trap=1.5)
    assert abs(p.trap_mm() - 0.3) < 1e-9 and p.choke_mm() == 0.2 and p.pullback_mm() == 0.2
    pr.save("mia", PressProfile(nombre="Mi máquina", tolerancia_mm=[0.3, 0.1]))
    assert pr.load("mia").tol_xy() == (0.3, 0.1)
    with pytest.raises(UserError):
        pr.delete("digital")
    with pytest.raises(ValueError):
        PressProfile(tolerancia_mm=9)
    assert pr.resolve("offset_pliego", 0.3).tolerancia_mm == 0.3


def test_R4_ancho_exacto_y_tolerancia_por_factor():
    p = plates_lr("Yellow", "Cyan")
    r = t.trap(p, press=PRESS, tac_max=None)
    y = r.plates.arrays["Yellow"]
    assert (y[:, 100:102] == 255).all() and (y[:, 102:] == 0).all()
    r2 = t.trap(p, press=PressProfile(tolerancia_mm=0.2, factor_trap=1.5), tac_max=None)
    assert (r2.plates.arrays["Yellow"][:, 100:103] == 255).all()
    assert r.traps[0]["regla"] == "R4"


def test_D1_luminosidad_parecida_trap_centrado():
    p = plates_lr()
    meta = M({"A": (52, 60, 40), "B": (50, -60, 40)})
    r = t.trap(p, meta, press=PRESS, tac_max=None)
    a, b = r.plates.arrays["A"], r.plates.arrays["B"]
    assert (a[:, 100:101] == 255).all() and (a[:, 101:] == 0).all()             # 0,1 mm = 1 px cada una
    assert (b[:, 99:100] == 255).all() and (b[:, :99] == 0).all()
    assert {x["regla"] for x in r.traps} == {"R5"}


def test_R3_negro_no_se_mueve():
    p = plates_lr("Yellow", "Black")
    r = t.trap(p, press=PRESS, tac_max=None)
    assert (r.plates.arrays["Black"] == p.arrays["Black"]).all() and r.plates.arrays["Yellow"][:, 100].max() == 255


def test_R1_tecnica_y_barniz_sin_cambios():
    for kind in ("technical", "varnish"):
        p = plates_lr()
        meta = M({"A": (80, 0, 0), "B": (30, 0, 0)}, tipos={"A": kind})
        r = t.trap(p, meta, press=PRESS)
        assert not r.traps and all((r.plates.arrays[n] == p.arrays[n]).all() for n in ("A", "B"))


def test_R2_blanco_solo_choke():
    h, w = 60, 120
    wh = np.zeros((h, w), np.uint8)
    wh[10:50, 10:110] = 255
    p = Plates(["Blanco"], {"Blanco": wh}, DPI, 0, w, h)
    r = t.trap(p, {"Blanco": {"lab": (94, 0, -2), "tipo": "white", "opacity": 1}}, press=PRESS)
    assert (r.plates.arrays["Blanco"][10, 10:110] == 0).all() and r.plates.arrays["Blanco"][30, 12] == 255      # se contrae 2 px
    assert r.traps[0]["regla"] == "R2"


def test_R6_transparente_bajo_opaca():
    p = plates_lr("Metal", "Tinta")
    meta = M({"Metal": (70, 0, 0), "Tinta": (40, 0, 0)}, op={"Metal": 1.0})
    r = t.trap(p, meta, press=PRESS, tac_max=None)
    assert r.traps[0]["de"] == "Tinta" and r.traps[0]["regla"] == "R6"
    assert (r.plates.arrays["Metal"] == p.arrays["Metal"]).all()


def test_R7_retraccion_de_cmy_bajo_negro_enriquecido():
    h, w = 80, 160
    K = np.zeros((h, w), np.uint8)
    K[:, 40:120] = 255
    p = Plates(["Cyan", "Black"], {"Cyan": K.copy(), "Black": K}, DPI, 0, w, h)
    r = t.trap(p, press=PRESS, tac_max=None)
    c = r.plates.arrays["Cyan"]
    assert (c[:, 40:42] == 0).all() and (c[:, 118:120] == 0).all() and c[:, 60].min() == 255
    assert (r.plates.arrays["Black"] == K).all()
    assert any(x["regla"] == "R7" for x in r.traps)


def test_R8_objeto_fino_trap_limitado():
    h, w = 60, 200
    Y = np.zeros((h, w), np.uint8)
    Y[:, :100] = 255
    C = np.zeros((h, w), np.uint8)
    C[:, 100:103] = 255                                                   # trazo de 0,3 mm
    p = Plates(["Yellow", "Cyan"], {"Yellow": Y, "Cyan": C}, DPI, 0, w, h)
    r = t.trap(p, press=PressProfile(tolerancia_mm=0.3), tac_max=None)
    assert int((r.plates.arrays["Yellow"][:, 100:103] > 0).sum() / h) <= 1     # trap de 3 px reducido a ≈ 1/3 del grosor
    assert (r.plates.arrays["Cyan"] == C).all()
    sin = t.trap(p, press=PressProfile(tolerancia_mm=0.3, trap_max_fraccion_objeto=0.0), tac_max=None)
    assert int((sin.plates.arrays["Yellow"][:, 100:103] > 0).sum() / h) == 3


def test_R9_texto_pequeno_sin_trap():
    p = plates_lr("Yellow", "Cyan")
    mask = np.zeros((100, 200), bool)
    mask[:, 90:110] = True
    assert not t.trap(p, press=PRESS, mantener_texto=mask).traps


def test_R10_degradados_no_se_trapean():
    p = plates_lr("Yellow", "Cyan")
    p.arrays["Cyan"][:, 100:] = 100                                       # < 50 %: degradado
    assert not t.trap(p, press=PRESS).traps


def test_R11_tope_de_tac():
    p = plates_lr("Yellow", "Black")
    r = t.trap(p, press=PRESS, tac_max=150)
    assert 125 <= int(r.plates.arrays["Yellow"][30, 100]) <= 130


def test_R12_tolerancia_eliptica():
    h, w = 100, 100
    A = np.zeros((h, w), np.uint8)
    A[:50, :] = 255
    B = np.zeros((h, w), np.uint8)
    B[50:, :] = 255
    p = Plates(["Yellow", "Cyan"], {"Yellow": A, "Cyan": B}, DPI, 0, w, h)         # frontera horizontal: cuenta la tolerancia en y
    r = t.trap(p, press=PressProfile(tolerancia_mm=[0.5, 0.1]), tac_max=None)
    assert (r.plates.arrays["Yellow"][50:51] == 255).all() and (r.plates.arrays["Yellow"][51:] == 0).all()
    r2 = t.trap(plates_lr("Yellow", "Cyan"), press=PressProfile(tolerancia_mm=[0.5, 0.1]), tac_max=None)      # vertical: cuenta x
    assert (r2.plates.arrays["Yellow"][:, 100:105] == 255).all() and (r2.plates.arrays["Yellow"][:, 105:] == 0).all()


def test_digital_sin_trap():
    r = t.trap(plates_lr("Yellow", "Cyan"), press=pr.EXAMPLES["digital"])
    assert not r.traps and any("Tolerancia 0" in w for w in r.warnings)


# ---------------------------------------------------------------- T2
def test_prueba_de_movimiento_D5():
    p = plates_lr("Yellow", "Cyan")
    sin = rc.check(p, PRESS)
    trapped = t.trap(p, press=PRESS, tac_max=None).plates
    con = rc.check(trapped, PRESS)
    doble = rc.check(trapped, PRESS, factor=2)
    assert sin.filetes_px > 0 and con.filetes_px == 0 and doble.filetes_px > 0
    assert con.to_dict()["ok"] and con.bordes_protegidos_pct == 100
    assert sin.peor_par and sin.mapa.shape == (100, 200, 3) and rc.side_by_side(sin, con).shape[1] == 408


def test_prueba_de_movimiento_centrado_y_elipse():
    meta = M({"A": (52, 60, 40), "B": (50, -60, 40)})
    p = plates_lr()
    pe = PressProfile(tolerancia_mm=[0.4, 0.1])
    assert rc.check(t.trap(p, meta, press=pe, tac_max=None).plates, pe, meta).filetes_px == 0
    assert rc.check(p, pe, meta).filetes_px > 0


def test_rendimiento_a4_300dpi():
    import time
    big = np.zeros((3508, 2480), np.uint8)
    big[:, :1200] = 255
    b2 = np.zeros_like(big)
    b2[:, 1200:] = 255
    P = Plates(["Yellow", "Cyan"], {"Yellow": big, "Cyan": b2}, 300.0, 0, 2480, 3508)
    t0 = time.time()
    r = t.trap(P, press=PressProfile(tolerancia_mm=0.15))
    assert rc.check(r.plates, PressProfile(tolerancia_mm=0.15)).filetes_px == 0
    assert time.time() - t0 < 10


# ---------------------------------------------------------------- T3
def _logo():
    import cv2
    img = np.full((300, 420, 3), 255, np.uint8)
    cv2.rectangle(img, (40, 40), (380, 260), (30, 60, 200), -1)
    cv2.circle(img, (150, 150), 70, (230, 200, 20), -1)
    cv2.circle(img, (300, 150), 50, (20, 150, 60), -1)
    return img


def test_separar_imagen_con_auto_trap_sin_filetes():
    from app.modules.separate import autotrap, raster
    res = raster.separate_flat(_logo(), 254, None, 6)
    r = autotrap.apply_raster(res, 254, PressProfile(tolerancia_mm=0.2))
    assert r.reg_before.filetes_px > 0 and r.reg_after.filetes_px == 0
    assert autotrap.registro_texto(r).startswith("✔")
    assert any("sustrato" in w for w in r.warnings)                 # el fondo blanco no se imprime ni se trapea
    assert r.stats["auto_trap"]["filetes_mm2_despues"] == 0


def test_modos_indice_y_proceso():
    from app.modules.separate import autotrap, raster
    idx = raster.separate_index(_logo(), k=4)
    assert autotrap.apply_raster(idx, 254, PRESS, modo="indice").stats["auto_trap"] == "no aplica"
    inks = [raster.Ink("Blanco", (95, 0, -2), 1.0), raster.Ink("Cyan", (55, -37, -50))]
    pr_ = raster.separate_process(_logo(), inks, raster.SUBSTRATES["Prenda negra"], white_index=0)
    r = autotrap.apply_raster(pr_, 254, PRESS, raster.SUBSTRATES["Prenda negra"], "proceso")
    assert any("proceso simulado" in w for w in r.warnings)


def test_api_imagen_y_pdf_con_auto_trap():
    import io
    import time
    import zipfile
    import cv2
    from fastapi.testclient import TestClient
    from app.core import ghostscript
    from app.main import app
    c = TestClient(app)
    ok, buf = cv2.imencode(".png", _logo()[..., ::-1])
    jid = c.post("/api/separar/img", files={"file": ("l.png", buf.tobytes(), "image/png")}).json()["job_id"]
    a = c.post(f"/api/separar/img/{jid}/procesar", json={"modo": "planas", "auto_trap": True, "prensa": "serigrafia_textil_automatica", "dpi": 254}).json()["job_id"]
    for _ in range(100):
        st = c.get(f"/api/jobs/{a}").json()
        if st["status"] != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done", st
    tp = st["result"]["trap"]
    assert tp["ok"] is True and "Sin filetes" in tp["registro"]
    assert c.get(f"/api/separar/img/{jid}/trap.png").status_code == 200 and c.get(f"/api/separar/img/{jid}/prueba.png").status_code == 200
    z = c.post(f"/api/separar/img/{jid}/exportar", json={})
    assert "Trapping" in zipfile.ZipFile(io.BytesIO(z.content)).read("informe.txt").decode("utf-8")
    assert c.get("/api/prensas").json()["perfiles"]
    if ghostscript.available():
        from pathlib import Path
        with open(Path(__file__).parent / "sinteticos_sep" / "completo.pdf", "rb") as f:
            pj = c.post("/api/separar/pdf", files={"file": ("c.pdf", f, "application/pdf")}).json()["job_id"]
        a = c.post(f"/api/separar/pdf/{pj}/autotrap?dpi=300").json()["job_id"]
        for _ in range(200):
            st = c.get(f"/api/jobs/{a}").json()
            if st["status"] != "running":
                break
            time.sleep(0.3)
        assert st["status"] == "done" and st["result"]["ok"] is True
        assert c.get(f"/api/separar/pdf/{pj}/composicion.png?dpi=300&trap=true").status_code == 200
        assert c.get(f"/api/separar/pdf/{pj}/movimiento.png?dpi=300&tinta=Black&mm=0.2").status_code == 200
        ex = c.post(f"/api/separar/pdf/{pj}/exportar", json={"trap": True, "dpi": 300, "formato": "informe"})
        assert "Trapping" in zipfile.ZipFile(io.BytesIO(ex.content)).read("informe_separaciones.txt").decode("utf-8")
