"""Gama extendida tipo «Equinox» (S7 §11.5) y prueba en pantalla (S7 §11.6).

Todo es una ESTIMACIÓN basada en el modelo de mezcla orientativo (core/colorscience.mix_inks): confirma con una prueba impresa."""
import itertools

import cv2
import numpy as np
import pikepdf
from PIL import Image, ImageDraw
from scipy.optimize import least_squares

from app.core import colorscience as cs
from app.core import inks as inkmod
from app.core.errors import UserError
from app.modules.separate import raster
from app.modules.separate.pdf_inks import _name
from app.modules.separate.pdf_render import Plates, compose
from app.modules.separate.raster_export import _tint_ps

PAPER = inkmod.PAPER_PC1
SOFTPROOF_NOTE = "Vista orientativa, no es una prueba contractual."
NOTE = "Estimación basada en un modelo; confirmar con prueba impresa."


def semaforo(de: float) -> str:
    return "verde" if de <= 2 else ("amarillo" if de <= 4 else "rojo")


def _mix(sub, inks, t, n):
    return np.asarray(cs.mix_inks(sub, [i.as_model() for i in inks], [np.float64(v) for v in t], n=n)).reshape(3)


def recipe_for(target_lab, fixed: list[raster.Ink], substrate=PAPER, max_inks: int = 3, n: float = 1.7, pref_penalty: float = 0.4) -> dict:
    """Mejor combinación (≤ `max_inks` tintas activas, preferentemente 2) que minimiza ΔE2000 al Lab objetivo."""
    if not fixed:
        raise UserError("Indica el juego de tintas fijo (por ejemplo CMYK + Naranja, Verde, Violeta).")
    best = None
    for k in range(1, min(max_inks, len(fixed)) + 1):
        for combo in itertools.combinations(range(len(fixed)), k):
            inks = [fixed[i] for i in combo]

            def res(t, inks=inks):
                return _mix(substrate, inks, t, n) - np.asarray(target_lab, float)

            sol = None
            for x0 in ([0.5] * k, [0.9] * k, [0.15] * k):
                s = least_squares(res, x0, bounds=(0, 1), max_nfev=40)
                if sol is None or s.cost < sol.cost:
                    sol = s
            t = np.clip(sol.x, 0, 1)
            active = int((t > 0.02).sum())
            de = float(cs.delta_e2000(_mix(substrate, inks, t, n), target_lab))
            score = de + pref_penalty * max(active - 2, 0) * 0 + pref_penalty * max(active - 1, 0)
            if best is None or score < best[0]:
                best = (score, combo, t, de)
    _, combo, t, de = best
    rec = {fixed[i].name: round(float(v) * 100, 1) for i, v in zip(combo, t) if v > 0.02}
    return {"receta": rec, "de": round(de, 2), "semaforo": semaforo(de), "reproducible": de <= 4}


def recipes(targets: list[dict], fixed: list[raster.Ink], substrate=PAPER, max_inks: int = 3) -> list[dict]:
    """Tabla tinta directa → receta (%), ΔE estimado y semáforo (≤ 2 verde, ≤ 4 amarillo, > 4 rojo = no reproducible con este juego)."""
    out = []
    for tg in targets:
        r = recipe_for(tg["lab"], fixed, substrate, max_inks)
        r.update(nombre=tg["name"], lab_objetivo=list(tg["lab"]))
        # Lab conseguido, para comparar swatches antes/después
        inks = [i for i in fixed if i.name in r["receta"]]
        if inks:
            got = _mix(substrate, inks, [r["receta"][i.name] / 100 for i in inks], 1.7)
            r["lab_resultado"] = [round(float(v), 2) for v in got]
        out.append(r)
    return out


def _rewrite(pdf, target_norm: str, names: list[str], cov: list[float], fixed_by_name: dict[str, raster.Ink]) -> int:
    """Sustituye en el contenido un Separation por un DeviceN de las tintas fijas: cada tinte t se convierte en (cov_j · t)."""
    count = [0]
    done = set()
    inks = [fixed_by_name[n] for n in names]
    tint = pdf.make_stream(_tint_ps(inks).encode(), FunctionType=4, Domain=[0, 1] * len(inks), Range=[0, 1] * 4)
    dn = pikepdf.Array([pikepdf.Name.DeviceN, pikepdf.Array([pikepdf.Name("/" + n) for n in names]), pikepdf.Name.DeviceCMYK, tint])

    def is_target(res, key):
        try:
            cso = res["/ColorSpace"][key]
        except Exception:
            return False
        return isinstance(cso, pikepdf.Array) and str(cso[0]) == "/Separation" and inkmod.normalize_name(_name(cso[1])) == target_norm

    def process(stream, res_owner):
        res = res_owner.get("/Resources")
        if res is None:
            return
        try:
            ops = pikepdf.parse_content_stream(stream)
        except Exception:
            return
        if "/ColorSpace" not in res:
            res["/ColorSpace"] = pikepdf.Dictionary()
        key = "/FVDN" + str(abs(hash(target_norm)) % 10 ** 6)
        res["/ColorSpace"][key] = dn
        out, cur, changed, stack = [], {"cs": False, "CS": False}, False, []
        for operands, op in ops:
            o = str(op)
            if o == "q":
                stack.append(dict(cur))
            elif o == "Q" and stack:
                cur = stack.pop()
            if o in ("cs", "CS"):
                cur[o] = is_target(res, operands[0])
                if cur[o]:
                    out.append(pikepdf.ContentStreamInstruction([pikepdf.Name(key)], op))
                    changed = True
                    continue
            elif o in ("scn", "sc", "SCN", "SC") and cur["cs" if o.islower() else "CS"]:
                t = float(operands[0])
                out.append(pikepdf.ContentStreamInstruction([float(round(c * t, 4)) for c in cov], op))
                count[0] += 1
                changed = True
                continue
            elif o in ("g", "rg", "k", "G", "RG", "K"):
                cur["cs" if o.islower() else "CS"] = False
            elif o == "Do":
                xo = (res.get("/XObject") or {}).get(operands[0])
                if xo is not None and str(xo.get("/Subtype")) == "/Form" and xo.objgen not in done:
                    done.add(xo.objgen)
                    process(xo, xo)
            out.append(pikepdf.ContentStreamInstruction(operands, op))
        if changed:
            stream.write(pikepdf.unparse_content_stream(out))

    for page in pdf.pages:
        c = page.obj.get("/Contents")
        if c is None:
            continue
        data = b"\n".join(s.read_bytes() for s in (c if isinstance(c, pikepdf.Array) else [c]))
        page.obj["/Contents"] = pdf.make_stream(data)
        process(page.obj["/Contents"], page.obj)
    return count[0]


def apply_to_pdf(src, dst, table: list[dict], fixed: list[raster.Ink], only_reproducible: bool = True) -> dict:
    """Reemplaza cada directa convertible por un DeviceN de las tintas fijas. Devuelve qué se convirtió y qué no."""
    fixed_by = {i.name: i for i in fixed}
    done, skipped = [], []
    with pikepdf.open(str(src)) as pdf:
        for row in table:
            if only_reproducible and not row["reproducible"]:
                skipped.append({"nombre": row["nombre"], "motivo": "no reproducible con este juego (ΔE > 4)"})
                continue
            names = list(row["receta"])
            cov = [row["receta"][n] / 100 for n in names]
            n = _rewrite(pdf, inkmod.normalize_name(row["nombre"]), names, cov, fixed_by)
            (done if n else skipped).append({"nombre": row["nombre"], "objetos": n} if n else {"nombre": row["nombre"], "motivo": "sin objetos"})
        pdf.save(str(dst))
    return {"convertidas": done, "omitidas": skipped, "nota": NOTE}


# ---------------------------------------------------------------- prueba en pantalla
def dot_gain(cov: np.ndarray, g50: float) -> np.ndarray:
    """Ganancia de punto: curva simple con `g50` de ganancia (0–0,3) en el 50 %. cov 0–255 → 0–255."""
    c = cov.astype(np.float32) / 255.0
    return np.clip((c + g50 * 4 * c * (1 - c)) * 255, 0, 255).astype(np.uint8)


def texture(shape, kind: str, seed: int = 3) -> np.ndarray:
    """Factor multiplicativo (0.85–1.1) que imita la fibra del sustrato."""
    if kind in ("", "ninguna", None):
        return np.ones(shape[:2], np.float32)
    rng = np.random.default_rng(seed)
    scale = {"kraft": 3, "carton": 5, "prenda": 2}.get(kind, 3)
    n = rng.normal(0, 1, (shape[0] // scale + 2, shape[1] // scale + 2)).astype(np.float32)
    n = cv2.resize(n, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)
    amp = {"kraft": 0.05, "carton": 0.06, "prenda": 0.04}.get(kind, 0.05)
    return np.clip(1 + amp * n, 0.85, 1.1)


def soft_proof(plates: Plates, meta: dict, *, substrate_lab=PAPER, gain: dict | None = None, default_gain: float = 0.0,
               sin_blanco: bool = False, textura: str = "ninguna", escala: float = 1.0) -> np.ndarray:
    """PNG sRGB de la simulación del trabajo con las tintas reales, el sustrato y la ganancia de punto. Lleva siempre la etiqueta de orientativa."""
    arrays = {n: dot_gain(a, (gain or {}).get(n, default_gain)) if ((gain or {}).get(n, default_gain)) else a for n, a in plates.arrays.items()}
    p2 = Plates(plates.names, arrays, plates.dpi, plates.page, plates.width, plates.height)
    visible = {n for n in plates.names if not (sin_blanco and (meta.get(n) or {}).get("tipo") == "white")}
    img = compose(p2, meta, visible, substrate_lab, scale=escala).astype(np.float32)
    img *= texture(img.shape, textura)[..., None]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    txt = SOFTPROOF_NOTE
    w = d.textlength(txt)
    d.rectangle([0, im.height - 16, w + 12, im.height], fill=(0, 0, 0))
    d.text((6, im.height - 14), txt, fill=(255, 255, 255))
    return np.array(im)
