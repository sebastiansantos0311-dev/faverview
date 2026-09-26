"""Calibración opcional del modelo de mezcla (S3 §7.6): gráfico de prueba, ajuste con Lab medidos y perfil de tintas.

El perfil mejora la precisión de la simulación (Lab del sólido real, ganancia de punto por tinta y factor n) pero sigue siendo
un modelo orientativo."""
import csv
import io
import json
import re

import numpy as np
import pikepdf
from scipy.optimize import minimize_scalar

from app.config import DATOS_DIR
from app.core import colorscience as cs
from app.core import inks as inkmod
from app.core.errors import UserError
from app.modules.separate.raster import PAPER, Ink

PROFILES_DIR = DATOS_DIR / "tintas" / "perfiles"
STEPS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def patches(inks: list[Ink]) -> list[dict]:
    """Parches del gráfico en orden fijo: rampas 0–100 % de cada tinta y sobreimpresión 100 % de cada par."""
    out = []
    for i in inks:
        for s in STEPS:
            out.append({"id": f"{i.name}|{s}", "tintas": {i.name: s}})
    for a in range(len(inks)):
        for b in range(a + 1, len(inks)):
            out.append({"id": f"{inks[a].name}+{inks[b].name}|100", "tintas": {inks[a].name: 100, inks[b].name: 100}})
    return out


def chart_pdf(inks: list[Ink], size_mm: float = 14.0) -> bytes:
    """PDF A4 con los parches (cada tinta como Separation) para imprimir con el juego de tintas real y medirlo."""
    pdf = pikepdf.new()
    pt = 72 / 25.4
    page = pdf.add_blank_page(page_size=(210 * pt, 297 * pt))
    cs_res = pikepdf.Dictionary()
    keys = {}
    for k, i in enumerate(inks):
        c = i.lab and cs.lab_to_srgb(i.lab)
        r, g, b = [float(x) for x in (c if c is not None else (0, 0, 0))]
        kk = 1 - max(r, g, b)
        cmyk = [0, 0, 0, 1] if kk >= 1 else [(1 - r - kk) / (1 - kk), (1 - g - kk) / (1 - kk), (1 - b - kk) / (1 - kk), kk]
        fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[round(v, 4) for v in cmyk], N=1)
        keys[i.name] = f"CS{k}"
        cs_res[f"/CS{k}"] = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + i.name.replace(" ", "_")), pikepdf.Name.DeviceCMYK, fn])
    ops, x0, y0 = [], 12.0, 12.0
    cols = int((210 - 24) // (size_mm + 2))
    for n, p in enumerate(patches(inks)):
        x = x0 + (n % cols) * (size_mm + 2)
        y = y0 + (n // cols) * (size_mm + 8)
        for name, pct in p["tintas"].items():
            # cada tinta rellena una mitad si hay dos; una sola ocupa todo el parche
            pass
        names = list(p["tintas"].items())
        if len(names) == 1:
            name, pct = names[0]
            ops.append(f"/{keys[name]} cs {pct / 100:.2f} scn {x * pt:.2f} {(297 - y - size_mm) * pt:.2f} {size_mm * pt:.2f} {size_mm * pt:.2f} re f")
        else:
            for j, (name, pct) in enumerate(names):
                ops.append(f"/{keys[name]} cs 1 scn {x * pt:.2f} {(297 - y - size_mm) * pt + j * size_mm * pt / 2:.2f} {size_mm * pt:.2f} {size_mm * pt / 2:.2f} re f")
        ops.append(f"BT /F1 5 Tf 0 0 0 1 k {x * pt:.2f} {(297 - y - size_mm - 4) * pt:.2f} Td ({p['id'].replace('(', '').replace(')', '')[:26]}) Tj ET")
    page.Resources = pikepdf.Dictionary(ColorSpace=cs_res, Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
    page.Contents = pdf.make_stream("\n".join(ops).encode("latin-1", "replace"))
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def template_csv(inks: list[Ink]) -> str:
    s = io.StringIO()
    w = csv.writer(s, delimiter=";")
    w.writerow(["id", "L", "a", "b"])
    for p in patches(inks):
        w.writerow([p["id"], "", "", ""])
    return s.getvalue()


def parse_measurements(text: str) -> dict[str, tuple]:
    rows = list(csv.reader(io.StringIO(text), delimiter=";" if text.split("\n")[0].count(";") else ","))
    out = {}
    for r in rows[1:]:
        if len(r) >= 4 and r[1].strip():
            try:
                out[r[0].strip()] = (float(r[1].replace(",", ".")), float(r[2].replace(",", ".")), float(r[3].replace(",", ".")))
            except ValueError:
                raise UserError(f"Valor Lab no válido en la fila «{r[0]}».")
    return out


def _mix1(sub, ink_lab, t, n):
    return np.asarray(cs.mix_inks(sub, [{"lab": ink_lab, "opacity": 0.0}], [np.float64(t)], n=n)).reshape(3)


def fit(inks: list[Ink], measured: dict[str, tuple]) -> dict:
    """Ajusta por tinta el Lab del sólido y la ganancia de punto (g50) y globalmente el factor n de Yule–Nielsen."""
    paper = measured.get(f"{inks[0].name}|0") or PAPER
    result = {"papel": list(paper), "tintas": {}, "n": 1.7}
    solids = {}
    for i in inks:
        s = measured.get(f"{i.name}|100")
        if s is None:
            raise UserError(f"Falta la medida del sólido de «{i.name}» ({i.name}|100).")
        solids[i.name] = s

    def ramp_error(name, n, g):
        errs = []
        for step in STEPS[1:-1]:
            m = measured.get(f"{name}|{step}")
            if m is None:
                continue
            t = step / 100
            teff = min(max(t + g * 4 * t * (1 - t), 0.0), 1.0)
            errs.append(float(cs.delta_e2000(_mix1(paper, solids[name], teff, n), m)))
        return float(np.mean(errs)) if errs else 0.0

    def fit_gains(n):
        gains, tot = {}, 0.0
        for i in inks:
            r = minimize_scalar(lambda g: ramp_error(i.name, n, g), bounds=(-0.2, 0.4), method="bounded", options={"xatol": 1e-3})
            gains[i.name] = float(r.x)
            tot += float(r.fun)
        return gains, tot / len(inks)

    # n y la ganancia de punto se compensan entre sí: se ajustan juntos (rejilla de n y g óptimo por tinta)
    grid = [(n, *fit_gains(n)) for n in np.arange(1.0, 3.01, 0.2)]
    n, gains, err = min(grid, key=lambda x: x[2])
    result["n"] = round(float(n), 3)
    for i in inks:
        result["tintas"][i.name] = {"lab": [round(float(v), 2) for v in solids[i.name]], "g50": round(gains[i.name], 4)}
    result["error_medio_de"] = round(err, 2)
    return result


def _safe(name: str) -> str:
    n = re.sub(r"[^\w\- ]", "_", name).strip()
    if not n:
        raise UserError("Nombre de perfil no válido.")
    return n


def save_profile(name: str, prof: dict) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    (PROFILES_DIR / f"{_safe(name)}.json").write_text(json.dumps(prof, indent=1, ensure_ascii=False), encoding="utf-8")


def load_profile(name: str) -> dict:
    f = PROFILES_DIR / f"{_safe(name)}.json"
    if not f.exists():
        raise UserError("No existe ese perfil de tintas.")
    return json.loads(f.read_text(encoding="utf-8"))


def list_profiles() -> list[str]:
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json")) if PROFILES_DIR.exists() else []


def apply_profile(inks: list[Ink], prof: dict) -> tuple[list[Ink], dict, float]:
    """Devuelve (tintas con el Lab del sólido calibrado, {nombre: g50}, n)."""
    out, gains = [], {}
    for i in inks:
        t = prof["tintas"].get(i.name)
        out.append(Ink(i.name, tuple(t["lab"]) if t else i.lab, i.opacity))
        if t:
            gains[i.name] = t["g50"]
    return out, gains, prof.get("n", 1.7)
