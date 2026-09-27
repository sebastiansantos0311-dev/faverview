"""Verificación de códigos de barras en un PDF o imagen (S6 §10.2): decodificación, magnificación, zonas de silencio,
contraste y una estimación de grado A–F inspirada en ISO/IEC 15416. NO es una verificación certificada."""
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import zxingcpp as z
from PIL import Image

from app.core.errors import UserError
from app.modules.barcodes import gs1
from app.modules.barcodes.generate import TIPOS

FMT_TO_TIPO = {"EAN-13": "ean13", "EAN-8": "ean8", "UPC-A": "upca", "UPC-E": "upce", "ITF": "itf14", "Code 128": "code128",
               "Code 39": "code39", "DataMatrix": "datamatrix", "QR Code": "qr", "DataBar": "databar", "GS1 DataBar": "databar"}
LETTERS = "FDCBA"
NOTE = "Estimación A–F inspirada en ISO/IEC 15416; no es una verificación certificada."


def _load(path, dpi: int, page: int):
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        with pymupdf.open(str(p)) as doc:
            if not 1 <= page <= len(doc):
                raise UserError("Esa página no existe.")
            pix = doc[page - 1].get_pixmap(dpi=dpi, alpha=False)
            return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy(), dpi
    try:
        im = Image.open(p)
        d = im.info.get("dpi", (dpi, dpi))[0] or dpi
        return np.array(im.convert("RGB")), float(d)
    except Exception:
        raise UserError("No se pudo abrir el archivo.")


def _lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _grade(value: float, thresholds, higher_better=True) -> int:
    """Nota 4 (A) … 0 (F) según umbrales descendentes A, B, C, D."""
    for i, t in enumerate(thresholds):
        if (value >= t) if higher_better else (value <= t):
            return 4 - i
    return 0


def _rotate(img, angle, cx, cy):
    M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))


def _profile_metrics(rgb_rot, box, tipo):
    """Métricas de un símbolo 1D sobre el perfil de reflectancia (banda central del símbolo girado a horizontal)."""
    x0, y0, x1, y1 = box
    h = y1 - y0
    m = int(0.3 * (x1 - x0) + 12)
    band = rgb_rot[int(y0 + h * 0.35):int(y0 + h * 0.65) + 1, max(int(x0) - m, 0):int(x1) + m]
    gray = band.mean(axis=2)
    prof = gray.mean(axis=0)
    ref = _lin(prof.astype(np.float64))
    rmax, rmin = float(np.percentile(ref, 97)), float(np.percentile(ref, 3))
    sc = rmax - rmin
    thr = (rmax + rmin) / 2
    dark = ref < thr
    # elementos
    edges = np.flatnonzero(np.diff(dark.astype(int)) != 0) + 1
    segs = np.split(np.arange(len(ref)), edges)
    seg_ref = [ref[s] for s in segs if len(s) > 0]
    inner = [(s, r) for s, r in zip(segs, seg_ref)][1:-1] if len(segs) > 4 else list(zip(segs, seg_ref))
    lens = np.array([len(s) for s, _ in inner]) if inner else np.array([1])
    x_px = float(np.median(lens[lens <= np.percentile(lens, 30) * 1.5])) if len(lens) > 3 else float(lens.min())
    # reflectancia de cada elemento (centro) y contraste de bordes
    vals = [float(np.median(r[len(r) // 4: max(len(r) * 3 // 4, len(r) // 4 + 1)])) for _, r in inner]
    ec = [abs(vals[i] - vals[i + 1]) for i in range(len(vals) - 1)] or [sc]
    ecmin = min(ec)
    mod = ecmin / sc if sc > 1e-6 else 0
    # irregularidad dentro de cada elemento
    core = [r[len(r) // 4: max(len(r) * 3 // 4, len(r) // 4 + 1)] for _, r in inner if len(r) > 3]
    ern = max((float(c.max() - c.min()) for c in core), default=0.0) / sc if sc > 1e-6 else 1.0
    first, last = (np.flatnonzero(dark)[[0, -1]] if dark.any() else (0, len(dark) - 1))
    MODS = {"ean13": 95, "ean8": 67, "upca": 95, "upce": 51}
    if tipo in MODS:                                    # ancho total del símbolo / nº de módulos: más preciso que el ancho de un elemento
        x_px = float((last - first + 1) / MODS[tipo])
    return {"sc": sc, "rmax": rmax, "rmin": rmin, "mod": mod, "ern": ern, "x_px": max(x_px, 1.0), "dark": dark, "left": None}


def _quiet(dark, x_px):
    """Módulos de silencio a cada lado dentro de la banda muestreada."""
    idx = np.flatnonzero(dark)
    if not len(idx):
        return 0, 0
    return idx[0] / x_px, (len(dark) - 1 - idx[-1]) / x_px


def verify(path, dpi: int = 600, page: int = 1, direccion_impresion: str | None = None) -> dict:
    """Detecta y evalúa todos los códigos. `direccion_impresion`: 'horizontal' | 'vertical' | None (flexo)."""
    rgb, real_dpi = _load(path, dpi, page)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    results = z.read_barcodes(gray)
    out = []
    for r in results:
        name = str(r.format).split(".")[-1] if not hasattr(r.format, "name") else r.format.name
        fmt_name = getattr(r, "symbology", None) or name
        tipo = None
        for k, v in FMT_TO_TIPO.items():
            if k.replace("-", "").replace(" ", "").lower() in str(r.format).replace("-", "").replace(" ", "").lower():
                tipo = v
        if tipo == "code128" and str(getattr(r, "symbology_identifier", "")).startswith("]C1"):
            tipo = "gs1_128"
        if tipo == "datamatrix" and str(getattr(r, "symbology_identifier", "")).startswith("]d2"):
            tipo = "gs1_datamatrix"
        info = {"formato": str(r.format), "contenido": r.text, "tipo": tipo, "avisos": [], "valido": bool(r.valid)}
        pts = r.position
        xs = [pts.top_left.x, pts.top_right.x, pts.bottom_right.x, pts.bottom_left.x]
        ys = [pts.top_left.y, pts.top_right.y, pts.bottom_right.y, pts.bottom_left.y]
        bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
        info["bbox"] = [int(bx0), int(by0), int(bx1 - bx0), int(by1 - by0)]
        is1d = TIPOS.get(tipo, (0, 0, 0, 0, 0, 0, True))[6] if tipo else True
        # dígito de control
        if tipo in ("ean13", "ean8", "upca", "itf14"):
            info["digito_control_ok"] = gs1.valid_check(r.text)
            if not info["digito_control_ok"]:
                info["avisos"].append({"severidad": "error", "mensaje": "El dígito de control es incorrecto."})
        # orientación
        ori = int(round(r.orientation)) % 360 if r.orientation is not None else 0
        info["orientacion"] = ori
        if is1d and direccion_impresion in ("horizontal", "vertical"):
            bars_vertical = ori % 180 == 0
            parallel = (direccion_impresion == "vertical") == bars_vertical
            if parallel:
                info["avisos"].append({"severidad": "advertencia", "mensaje":
                                       "Las barras son paralelas a la dirección de impresión (flexo): se ensanchan más. Gira el código 90°."})
        # medidas sobre el símbolo girado a horizontal
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        rot = _rotate(rgb, ori if ori % 180 else 0, cx, cy) if ori % 180 else rgb
        if ori in (90, 270):
            rot = _rotate(rgb, -(ori - 0) if False else (ori), cx, cy)
        w, h = bx1 - bx0, by1 - by0
        if ori % 180 == 90:
            w, h = h, w
        box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if is1d:
            m = _profile_metrics(rot, box, tipo)
            x_mm = m["x_px"] / real_dpi * 25.4
            info["x_mm"] = round(x_mm, 3)
            if tipo in ("ean13", "ean8", "upca", "upce"):
                info["magnificacion_pct"] = round(x_mm / 0.33 * 100, 1)
                if not 80 <= info["magnificacion_pct"] <= 200:
                    info["avisos"].append({"severidad": "error", "mensaje": f"Magnificación de {info['magnificacion_pct']:.0f} % (permitido 80–200 %)."})
            ql, qr_ = m["dark"], None
            need_l, need_r = (TIPOS[tipo][4], TIPOS[tipo][5]) if tipo in TIPOS else (10, 10)
            if tipo == "ean13" and r.text.startswith("0"):      # un UPC-A se lee como EAN-13 con 0 delante
                need_l, need_r = min(need_l, TIPOS["upca"][4]), min(need_r, TIPOS["upca"][5])
            ql, qr_ = _quiet(m["dark"], m["x_px"])
            info["silencio_modulos"] = {"izq": round(float(ql), 1), "der": round(float(qr_), 1), "requerido": [need_l, need_r]}
            if ql < need_l * 0.9 - 0.5 or qr_ < need_r * 0.9 - 0.5:
                info["avisos"].append({"severidad": "advertencia", "mensaje":
                                       f"Zona de silencio corta ({ql:.1f} / {qr_:.1f} módulos; se necesitan {need_l} y {need_r})."})
            sc, mod, ern = m["sc"], m["mod"], m["ern"]
            info["contraste_simbolo_pct"] = round(sc * 100, 1)
            grades = {"contraste": _grade(sc * 100, (70, 55, 40, 20)), "modulacion": _grade(mod, (0.70, 0.60, 0.50, 0.40)),
                      "defectos": _grade(ern, (0.15, 0.20, 0.25, 0.30), False),
                      "reflectancia_minima": 4 if m["rmin"] <= 0.5 * m["rmax"] else 0, "decodificacion": 4}
            g = min(grades.values())
            info["grado"] = {"letra": LETTERS[g], "parciales": {k: LETTERS[v] for k, v in grades.items()}, "nota": NOTE}
            sc_red = sc
        else:
            sub = gray[max(int(by0), 0):int(by1), max(int(bx0), 0):int(bx1)]
            rmax, rmin = float(np.percentile(_lin(sub.astype(float)), 97)), float(np.percentile(_lin(sub.astype(float)), 3))
            sc_red = rmax - rmin
            info["contraste_simbolo_pct"] = round(sc_red * 100, 1)
            side = max(sub.shape) / max(np.sqrt(len(r.text)) * 2, 1)
            g = _grade(sc_red * 100, (70, 55, 40, 20))
            info["grado"] = {"letra": LETTERS[g], "parciales": {"contraste": LETTERS[g], "decodificacion": "A"}, "nota": NOTE}
        # contraste en luz roja (canal R): rojo sobre blanco ⇒ error
        crop = rgb[max(int(by0), 0):int(by1), max(int(bx0), 0):int(bx1)].astype(np.float64)
        gcrop = cv2.cvtColor(crop.astype(np.uint8), cv2.COLOR_RGB2GRAY)
        if gcrop.size:
            t, _ = cv2.threshold(gcrop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            dk, lt = gcrop < t, gcrop >= t
            if dk.any() and lt.any():
                red_d = float(_lin(crop[..., 0][dk]).mean())
                red_l = float(_lin(crop[..., 0][lt]).mean())
                pcs_red = (red_l - red_d) / max(red_l, 1e-6)
                info["contraste_luz_roja_pct"] = round(pcs_red * 100, 1)
                if pcs_red < 0.4:
                    info["avisos"].append({"severidad": "error", "mensaje":
                                           f"Contraste en luz roja de solo {pcs_red * 100:.0f} %: los escáneres de luz roja pueden no leerlo (p. ej. barras rojas sobre blanco)."})
                    info["grado"]["letra"] = "F" if pcs_red < 0.2 else info["grado"]["letra"]
        out.append(info)
    if not out:
        return {"codigos": [], "mensaje": "No se detectó ningún código de barras legible.", "dpi": real_dpi, "nota": NOTE}
    return {"codigos": out, "mensaje": f"{len(out)} código(s) detectado(s).", "dpi": real_dpi, "nota": NOTE}
