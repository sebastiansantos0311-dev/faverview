"""Generador de casos sintéticos con errores conocidos (reproducible con semilla fija).

Uso:  uv run python -m bench.synth [--out tests/sinteticos]

Cada caso queda en su carpeta con: diseno.pdf, cliente.jpg y esperado.json (mismo formato que los casos reales).
El "diseño" es lo que se corrige y el "cliente" es la referencia; los errores se inyectan donde corresponde
(en el cliente para cambios de texto/color/logo, en el diseño para tildes).
"""
import argparse
import copy
import io
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image

from app.compare_color import delta_e, hex_to_rgb
from app.compare_text import layout_words, order_words
from app.loaders import extract_pdf_layout

DPI = 200
S = DPI / 72.0
PAGE_W, PAGE_H = 595, 842
OUT_DEFAULT = Path(__file__).resolve().parent.parent / "tests" / "sinteticos"


# --------------------------------------------------------------------------- diseños base
def T(id_, x, y, s, size, font="helv", color=(0, 0, 0)):
    return {"t": "text", "id": id_, "x": x, "y": y, "s": s, "size": size, "font": font, "color": color}


def R(id_, rect, fill):
    return {"t": "rect", "id": id_, "rect": rect, "fill": fill}


def C(id_, c, r, fill):
    return {"t": "circle", "id": id_, "c": c, "r": r, "fill": fill}


def design_spec(key: str) -> dict:
    items = []
    bg = None
    if key == "d1_volante":
        items = [
            T("title", 50, 90, "Oferta de Verano", 34, "hebo", (0.1, 0.1, 0.1)),
            T("price", 50, 160, "Precio 10.000", 26, "helv", (0.8, 0, 0)),
            T("p1", 50, 210, "Aprovecha nuestras ofertas especiales de temporada", 13),
            T("p2", 50, 230, "en todos los productos de la tienda hasta agotar stock.", 13),
            R("rect1", (50, 300, 300, 420), (0.1, 0.45, 0.8)),
            T("rt", 70, 370, "Descuento hasta 40%", 18, "hebo", (1, 1, 1)),
            C("logo", (480, 120), 45, (0.0, 0.4, 0.8)),
            T("info", 50, 700, "Más información en www.tiendaejemplo.com", 12),
            T("tel", 50, 725, "Teléfono: 555-1234 · abierto los sábados", 12, "helv", (0.3, 0.3, 0.3)),
        ]
    elif key == "d2_texto_pequeno":
        lines = [
            "La comunidad se reunirá el próximo sábado para revisar las actividades del mes.",
            "Durante la jornada se presentarán los resultados de la campaña de reciclaje.",
            "Los vecinos podrán proponer nuevas ideas para mejorar el parque principal.",
            "Recuerda traer tu documento de identidad y el comprobante de residencia.",
            "La entrada es libre y habrá refrigerios para todos los asistentes.",
            "El comité agradece la participación de las familias en cada evento.",
            "Para más detalles comunícate con la oficina de atención al ciudadano.",
            "Los horarios de atención son de lunes a viernes por la mañana y la tarde.",
            "Si tienes alguna pregunta escribe a nuestro correo o visita la sede central.",
            "Gracias por ser parte de una comunidad activa, solidaria y comprometida.",
        ]
        items = [T("title", 50, 80, "Boletín Informativo Mensual", 20, "hebo", (0.1, 0.2, 0.4))]
        for i, ln in enumerate(lines):
            items.append(T(f"l{i}", 50, 130 + i * 24, ln, 8 if i % 2 else 9))
        items.append(T("price", 50, 420, "Cuota mensual 15.000", 9, "hebo"))
        items.append(T("foot", 50, 800, "Teléfono de atención 555-4321 - Horario continuo", 7, "helv", (0.4, 0.4, 0.4)))
        items.append(R("bar", (50, 440, 545, 470), (0.85, 0.9, 0.95)))
        items.append(T("bart", 60, 460, "Reunión general el sábado a las diez de la mañana", 9, "hebo", (0.1, 0.2, 0.4)))
    elif key == "d3_fondo_oscuro":
        bg = (0.08, 0.10, 0.18)
        items = [
            T("title", 50, 100, "Gran Venta Nocturna", 36, "hebo", (1, 1, 1)),
            T("sub", 50, 150, "Solo esta semana en todas las tiendas", 20, "helv", (0.95, 0.8, 0.2)),
            T("desc", 50, 200, "Descuentos de hasta 50% en toda la colección", 14, "helv", (1, 1, 1)),
            R("rect1", (60, 330, 340, 430), (0.95, 0.75, 0.1)),
            T("rt", 80, 388, "Llévate dos por uno", 20, "hebo", (0.1, 0.1, 0.15)),
            C("logo", (500, 110), 40, (1, 1, 1)),
            T("price", 60, 500, "Desde 29.900", 28, "hebo", (0.95, 0.8, 0.2)),
            T("foot", 50, 780, "Visítanos en la avenida principal número 45", 12, "helv", (0.75, 0.75, 0.8)),
        ]
    elif key == "d4_tabla_precios":
        items = [T("title", 50, 90, "Lista de Precios", 26, "hebo", (0.1, 0.1, 0.1)),
                 R("head", (50, 130, 545, 165), (0.15, 0.3, 0.55)),
                 T("h1", 60, 153, "Producto", 13, "hebo", (1, 1, 1)),
                 T("h2", 300, 153, "Cantidad", 13, "hebo", (1, 1, 1)),
                 T("h3", 450, 153, "Precio", 13, "hebo", (1, 1, 1))]
        rows = [("Camiseta básica", "12 unidades", "$25.000"), ("Pantalón clásico", "8 unidades", "$68.500"),
                ("Chaqueta ligera", "5 unidades", "$120.000"), ("Zapatos deportivos", "10 unidades", "$89.900"),
                ("Gorra de verano", "20 unidades", "$18.000")]
        for i, (a, b, c) in enumerate(rows):
            y0 = 165 + i * 38
            if i % 2 == 0:
                items.append(R(f"band{i}", (50, y0, 545, y0 + 38), (0.93, 0.95, 0.98)))
            items += [T(f"a{i}", 60, y0 + 24, a, 13), T(f"b{i}", 300, y0 + 24, b, 13),
                      T(f"c{i}", 450, y0 + 24, c, 13, "hebo")]
        items.append(T("foot", 50, 700, "Precios incluyen impuestos y envío gratis", 12, "helv", (0.3, 0.3, 0.3)))
    elif key == "d5_bandas":
        items = [
            R("b1", (0, 150, 595, 260), (0.85, 0.2, 0.2)), T("t1", 40, 215, "Ofertas de Primavera", 30, "hebo", (1, 1, 1)),
            R("b2", (0, 280, 595, 390), (0.15, 0.6, 0.3)), T("t2", 40, 345, "Descuentos en jardinería", 30, "hebo", (1, 1, 1)),
            R("b3", (0, 410, 595, 520), (0.15, 0.35, 0.75)), T("t3", 40, 475, "Nueva colección de flores", 30, "hebo", (1, 1, 1)),
            C("logo", (500, 80), 40, (0.85, 0.2, 0.2)),
            T("title", 50, 95, "Vivero Los Andes", 24, "hebo", (0.1, 0.1, 0.1)),
            T("cta", 50, 600, "Visita nuestra tienda esta semana", 16, "helv"),
            T("tel", 50, 630, "Teléfono: 555-7788", 16, "hebo", (0.6, 0.1, 0.1)),
        ]
    elif key == "d6_mixto":
        items = [
            C("logo", (100, 110), 40, (0.1, 0.55, 0.5)),
            T("title", 170, 105, "Clínica Dental Sonrisa", 30, "hebo", (0.1, 0.35, 0.35)),
            T("sub", 170, 135, "Cuidamos tu sonrisa cada día", 16, "heit", (0.3, 0.3, 0.3)),
            T("b1", 60, 260, "- Limpieza dental profesional", 14),
            T("b2", 60, 290, "- Blanqueamiento con garantía", 14),
            T("b3", 60, 320, "- Ortodoncia para niños y adultos", 14),
            T("b4", 60, 350, "- Atención de urgencias todos los días", 14),
            R("box", (50, 420, 545, 520), (0.9, 0.96, 0.95)),
            T("promo", 70, 480, "Primera consulta gratis este mes", 22, "hebo", (0.1, 0.35, 0.35)),
            T("tel", 60, 600, "Teléfono: 555-9876", 18, "hebo"),
            T("addr", 60, 630, "Calle Principal número 123, Bogotá", 12),
        ]
    return {"bg": bg, "items": items}


DESIGN_KEYS = ["d1_volante", "d2_texto_pequeno", "d3_fondo_oscuro", "d4_tabla_precios", "d5_bandas", "d6_mixto"]


def build_pdf(spec: dict, path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    if spec.get("bg"):
        page.draw_rect(page.rect, color=None, fill=spec["bg"])
    for it in spec["items"]:
        if it["t"] == "text":
            page.insert_text((it["x"], it["y"]), it["s"], fontsize=it["size"], fontname=it["font"], color=it["color"])
        elif it["t"] == "rect":
            page.draw_rect(pymupdf.Rect(*it["rect"]), color=None, fill=it["fill"])
        elif it["t"] == "circle":
            page.draw_circle(it["c"], it["r"], color=None, fill=it["fill"])
            inner = (1, 1, 1) if spec.get("bg") is None else (0.08, 0.10, 0.18)
            if it["fill"] == (1, 1, 1):
                inner = (0.08, 0.10, 0.18)
            page.draw_circle(it["c"], it["r"] * 0.4, color=None, fill=inner)
    doc.save(path)
    doc.close()


def render(path: Path) -> np.ndarray:
    with pymupdf.open(path) as doc:
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(S, S), alpha=False)
        return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()


# --------------------------------------------------------------------------- localizar elementos
def item_bbox_px(spec, spans, item_id):
    it = next(i for i in spec["items"] if i["id"] == item_id)
    if it["t"] == "rect":
        x0, y0, x1, y1 = it["rect"]
        return [round(x0 * S), round(y0 * S), round((x1 - x0) * S), round((y1 - y0) * S)]
    if it["t"] == "circle":
        (cx, cy), r = it["c"], it["r"]
        return [round((cx - r) * S), round((cy - r) * S), round(2 * r * S), round(2 * r * S)]
    sp = next(s for s in spans if s.text == it["s"].strip())
    x0, y0, x1, y1 = sp.bbox
    return [round(x0), round(y0), round(x1 - x0), round(y1 - y0)]


def word_bbox_px(spans, text, idx):
    sp = next(s for s in spans if s.text == text.strip())
    x0, y0, x1, y1 = sp.words[idx][1]
    return [round(x0), round(y0), round(x1 - x0), round(y1 - y0)]


def get_item(spec, item_id):
    return next(i for i in spec["items"] if i["id"] == item_id)


def text_items(spec, min_words=1, max_words=99):
    return [i for i in spec["items"] if i["t"] == "text" and min_words <= len(i["s"].split()) <= max_words]


def text_width(it) -> float:
    return pymupdf.get_text_length(it["s"], fontname=it["font"], fontsize=it["size"])


# --------------------------------------------------------------------------- errores
def _err(cat, bbox, sub=None, cliente=None, diseno=None, extra=None):
    e = {"categoria": cat, "bbox": bbox}
    if sub:
        e["subtipo"] = sub
    if cliente is not None:
        e["cliente_dice"] = cliente
    if diseno is not None:
        e["diseno_dice"] = diseno
    if extra:
        e.update(extra)
    return e


def inject_number(design, client, tmp, rng):
    """Cambia un número del texto del cliente (p. ej. 10.000 → 12.000)."""
    cands = [i for i in text_items(client) if any(ch.isdigit() for ch in i["s"]) and "-" not in i["s"]
             and "%" not in i["s"] and i["id"] not in ("tel", "foot", "l0")]
    it = rng.choice(cands)
    words = it["s"].split()
    widx = next(k for k, w in reversed(list(enumerate(words))) if any(c.isdigit() for c in w))
    old = words[widx]
    digits = [k for k, c in enumerate(old) if c.isdigit()]
    k = digits[0] if len(digits) > 1 else digits[0]
    new_d = str((int(old[k]) + rng.integers(1, 5)) % 10)
    new = old[:k] + new_d + old[k + 1:]
    old_text = it["s"]
    words[widx] = new
    get_item(client, it["id"])["s"] = " ".join(words)
    return lambda spans, cspans=None: [_err("text", word_bbox_px(spans, old_text, widx), "cambiada", new, old)]


def inject_word_removed(design, client, tmp, rng):
    """El cliente NO tiene una palabra que el diseño sí (palabra sobrante en el diseño)."""
    cands = [i for i in text_items(client, 4) if i["size"] >= 9]
    it = rng.choice(cands)
    words = it["s"].split()
    idx = 2 if len(words[2]) >= 4 and not any(c.isdigit() for c in words[2]) else 1
    removed = words.pop(idx)
    old_text = it["s"]
    get_item(client, it["id"])["s"] = " ".join(words)
    return lambda spans, cspans=None: [_err("text", word_bbox_px(spans, old_text, idx), "sobrante", "", removed)]


def inject_word_added(design, client, tmp, rng):
    """El cliente tiene una palabra extra al final de una línea (falta en el diseño)."""
    cands = [i for i in text_items(client, 2, 6) if i["x"] + text_width(i) + 90 < 560 and i["size"] >= 12
             and i["id"] not in ("tel",)]
    it = rng.choice(cands)
    old_text = it["s"]
    it["s"] = old_text + " gratis"
    new_text = it["s"]
    return lambda spans, cspans=None: [_err("text", word_bbox_px(cspans, new_text, len(new_text.split()) - 1),
                                            "faltante", "gratis", "")]


def _deaccent(s: str) -> str:
    for a, b in zip("áéíóúÁÉÍÓÚ", "aeiouAEIOU"):
        s = s.replace(a, b)
    return s


def inject_tilde(design, client, tmp, rng):
    """Al diseño se le quita una tilde; el cliente la tiene (error de ortografía + texto)."""
    cands = [i for i in text_items(design) if _deaccent(i["s"]) != i["s"] and i["size"] >= 9]
    it = rng.choice(cands)
    words = it["s"].split()
    widx = next(k for k, w in enumerate(words) if _deaccent(w) != w and not w.isupper())
    old_word, new_word = words[widx], _deaccent(words[widx])
    old_text = it["s"]
    words[widx] = new_word
    get_item(design, it["id"])["s"] = " ".join(words)
    new_text = get_item(design, it["id"])["s"]
    return lambda spans, cspans=None: [
        _err("text", word_bbox_px(spans, new_text, widx), "cambiada", old_word, new_word),
        _err("spelling", word_bbox_px(spans, new_text, widx), "tilde_faltante", None, new_word)]


def _shift_color(rgb, target):
    base = np.array(rgb, float)
    for goal in ((0, 0, 0), (1, 1, 1), (0.9, 0.1, 0.1), (0.1, 0.7, 0.2), (0.2, 0.2, 0.9)):
        g = np.array(goal, float)
        if delta_e(tuple(g * 255), tuple(base * 255)) < target:
            continue
        lo, hi = 0.0, 1.0
        for _ in range(20):
            mid = (lo + hi) / 2
            c = base * (1 - mid) + g * mid
            if delta_e(tuple(c * 255), tuple(base * 255)) < target:
                lo = mid
            else:
                hi = mid
        c = base * (1 - hi) + g * hi
        return tuple(float(v) for v in c)
    return tuple(1 - v for v in rgb)


def make_inject_color(target):
    def inject(design, client, tmp, rng):
        rects = [i for i in client["items"] if i["t"] == "rect" and i["id"].startswith(("rect", "b1", "b2", "b3", "box", "bar"))]
        it = rng.choice(rects)
        old = it["fill"]
        it["fill"] = _shift_color(old, target)
        real = delta_e(tuple(v * 255 for v in old), tuple(v * 255 for v in it["fill"]))
        rid = it["id"]
        if real < 12:  # cambio sutil: NO debe reportarse
            return lambda spans, cspans=None: []
        return lambda spans, cspans=None: [_err("color", item_bbox_px(design, spans, rid), "zona", None, None,
                                   {"delta_e": round(real, 1)})]
    return inject


def inject_logo_removed(design, client, tmp, rng):
    target = next(i["id"] for i in client["items"] if i["id"] in ("logo", "band0", "bar"))
    client["items"] = [i for i in client["items"] if i["id"] != target]
    return lambda spans, cspans=None: [_err("visual", item_bbox_px(design, spans, target), "elemento_sobrante")]


def inject_logo_moved(design, client, tmp, rng):
    it = get_item(client, "logo")
    old_c = it["c"]
    it["c"] = (old_c[0], old_c[1] + 150) if old_c[1] < 300 else (old_c[0], old_c[1] - 150)
    new = copy.deepcopy(it)

    def exp(spans, cspans=None):
        old_box = item_bbox_px(design, spans, "logo")
        new_box = item_bbox_px({"items": [new]}, spans, "logo")
        return [_err("visual", old_box, "elemento_movido"), _err("visual", new_box, "elemento_movido")]
    return exp


def inject_font_size(design, client, tmp, rng):
    cands = [i for i in text_items(client, 3) if i["size"] >= 13 and i["x"] + text_width(i) * 1.2 < 560
             and i["id"] not in ("tel",)]
    it = rng.choice(cands)
    it["size"] = round(it["size"] * 1.2, 1)
    iid = it["id"]
    return lambda spans, cspans=None: [_err("font", item_bbox_px(design, spans, iid), "tamano")]


def inject_bold(design, client, tmp, rng):
    cands = [i for i in text_items(client, 3) if i["font"] == "helv" and i["size"] >= 13
             and i["x"] + text_width(i) * 1.1 < 560]
    it = rng.choice(cands)
    it["font"] = "hebo"
    iid = it["id"]
    return lambda spans, cspans=None: [_err("font", item_bbox_px(design, spans, iid), "negrita")]


# --------------------------------------------------------------------------- degradaciones
def d_rotate(img, deg):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                          borderValue=(255, 255, 255))


def d_perspective(img, k, rng):
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    j = lambda: rng.uniform(-k, k)
    dst = np.float32([[j() * w, j() * h], [w + j() * w, j() * h], [w + j() * w, h + j() * h], [j() * w, h + j() * h]])
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                               borderValue=(255, 255, 255))


def d_blur(img, sigma):
    return cv2.GaussianBlur(img, (0, 0), sigma)


def d_noise(img, std, rng):
    n = rng.normal(0, std, img.shape)
    return np.clip(img.astype(np.float32) + n, 0, 255).astype(np.uint8)


def d_illum(img, strength):
    h, w = img.shape[:2]
    gx = np.linspace(1 - strength, 1, w)[None, :]
    gy = np.linspace(1 - strength / 2, 1, h)[:, None]
    return np.clip(img.astype(np.float32) * (gx * gy)[..., None], 0, 255).astype(np.uint8)


def d_crop(img, pct):
    h, w = img.shape[:2]
    dy, dx = int(h * pct), int(w * pct)
    return img[dy:h - dy, dx:w - dx]


def d_scale(img, f):
    return cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)


def d_frame(img):
    """Marco de captura de pantalla: barra superior de estado, barra inferior y márgenes."""
    h, w = img.shape[:2]
    bar_t, bar_b, side = int(h * 0.06), int(h * 0.04), int(w * 0.03)
    out = np.full((h + bar_t + bar_b, w + 2 * side, 3), (32, 33, 36), np.uint8)
    out[bar_t:bar_t + h, side:side + w] = img
    cv2.putText(out, "12:45", (side + 10, int(bar_t * 0.7)), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (230, 230, 230), 2)
    return out


def save_client(img, path: Path, quality: int, cmyk=False):
    im = Image.fromarray(img)
    if cmyk:
        im = im.convert("CMYK")
    im.save(path, "JPEG", quality=quality)


def degrade(img, deg: dict, rng, path: Path):
    if "scale" in deg:
        img = d_scale(img, deg["scale"])
    if "rotate" in deg:
        img = d_rotate(img, deg["rotate"])
    if "perspective" in deg:
        img = d_perspective(img, deg["perspective"], rng)
    if "crop" in deg:
        img = d_crop(img, deg["crop"])
    if deg.get("frame"):
        img = d_frame(img)
    if "illum" in deg:
        img = d_illum(img, deg["illum"])
    if "blur" in deg:
        img = d_blur(img, deg["blur"])
    if "noise" in deg:
        img = d_noise(img, deg["noise"], rng)
    save_client(img, path, deg.get("jpeg", 85), deg.get("cmyk", False))


# --------------------------------------------------------------------------- matriz de casos
def variants():
    """(nombre, [inyectores], degradaciones)."""
    return [
        ("identico", [], {"jpeg": 85}),
        ("numero", [inject_number], {"jpeg": 75}),
        ("palabra_quitada", [inject_word_removed], {"rotate": 3.0, "jpeg": 80}),
        ("palabra_agregada", [inject_word_added], {"scale": 0.7, "blur": 0.8, "jpeg": 80}),
        ("tilde", [inject_tilde], {"jpeg": 50, "noise": 4}),
        ("color", [make_inject_color(25)], {"illum": 0.15, "jpeg": 80}),
        ("logo", [inject_logo_removed], {"perspective": 0.012, "jpeg": 80}),
        ("fuente_tamano", [inject_font_size], {"jpeg": 80}),
        ("negrita", [inject_bold], {"crop": 0.03, "jpeg": 85}),
        ("mixto", [inject_number, inject_tilde, make_inject_color(30)], {"rotate": -4.0, "jpeg": 60}),
        ("color_sutil", [make_inject_color(5)], {"jpeg": 70}),
        ("cmyk_marco", [], {"cmyk": True, "frame": True, "jpeg": 88}),
    ]


def generate(out: Path = OUT_DEFAULT, seed: int = 1000, quiet=False) -> int:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    n = 0
    for di, dkey in enumerate(DESIGN_KEYS):
        for vi, (vname, injectors, deg) in enumerate(variants()):
            n += 1
            rng = np.random.default_rng(seed + n)
            case = f"sint_{n:03d}_{dkey.split('_')[0]}_{vname}"
            cdir = out / case
            cdir.mkdir()
            base = design_spec(dkey)
            dspec, cspec = copy.deepcopy(base), copy.deepcopy(base)
            makers = []
            for inj in injectors:
                try:
                    makers.append(inj(dspec, cspec, cdir, rng))
                except (ValueError, StopIteration, IndexError):
                    continue  # el diseño no admite ese error; el caso queda con menos errores
            design_pdf, client_pdf = cdir / "diseno.pdf", cdir / "_cliente.pdf"
            build_pdf(dspec, design_pdf)
            build_pdf(cspec, client_pdf)
            spans = extract_pdf_layout(design_pdf, DPI)
            cspans = extract_pdf_layout(client_pdf, DPI)
            errors = []
            for mk in makers:
                errors += mk(spans, cspans)
            client_img = render(client_pdf)
            degrade(client_img, deg, rng, cdir / "cliente.jpg")
            words = order_words(layout_words(cspans))
            (cdir / "esperado.json").write_text(json.dumps({
                "caso": case, "tipo": "sintetico", "cliente": "cliente.jpg", "diseno": "diseno.pdf",
                "pagina_cliente": 1, "pagina_diseno": 1, "degradaciones": deg,
                "errores": errors, "texto_cliente": " ".join(w.text for w in words), "notas": ""},
                ensure_ascii=False, indent=1), encoding="utf-8")
            client_pdf.unlink()
            if not quiet:
                print(f"{case}: {len(errors)} errores")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--seed", type=int, default=1000)
    a = ap.parse_args()
    print(generate(a.out, a.seed), "casos generados en", a.out)


if __name__ == "__main__":
    main()
