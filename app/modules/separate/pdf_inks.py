"""Inventario de tintas de un PDF (S2 §6.1): recorre páginas y recursos (incluidos los anidados) con pikepdf."""
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pikepdf

from app.core import colorscience as cs
from app.core import inks as inkmod
from app.core.errors import UserError
from app.core.pdffunctions import FunctionError, evaluate

PAINT_FILL = {"f", "F", "f*", "B", "B*", "b", "b*"}
PAINT_STROKE = {"S", "s", "B", "B*", "b", "b*"}
PAINT_TEXT = {"Tj", "TJ", "'", '"'}
_PROC = builtin = None  # se rellena al usarse


def _proc_inks():
    return [{"lab": i.lab, "opacity": 0.0} for i in inkmod.builtin_library().inks[:4]]


@dataclass
class InkUse:
    name: str
    norm: str
    kind: str                       # process | spot | white | varnish | technical
    space: str                      # Separation | DeviceN | DeviceCMYK | ...
    alt_space: str | None = None    # espacio alternativo (DeviceCMYK, DeviceRGB, Lab…)
    alt_is_rgb: bool = False
    alt_cmyk: tuple | None = None
    lab: tuple | None = None
    pages: set = field(default_factory=set)
    objects: int = 0
    defined: bool = True
    variants: set = field(default_factory=set)      # nombres originales que se unen en este
    resource_keys: set = field(default_factory=set)

    def to_dict(self) -> dict:
        ink = inkmod.Ink(name=self.name, kind=self.kind, lab=self.lab, alt_cmyk=self.alt_cmyk, source="pdf")
        return {"nombre": self.name, "normalizado": self.norm, "tipo": self.kind, "espacio": self.space,
                "alternativo": self.alt_space, "alt_rgb": self.alt_is_rgb,
                "alt_cmyk": list(self.alt_cmyk) if self.alt_cmyk else None, "lab": list(self.lab) if self.lab else None,
                "muestra": ink.swatch_hex(), "paginas": sorted(self.pages), "objetos": self.objects,
                "usada": self.objects > 0, "duplicados": sorted(self.variants - {self.name}) if len(self.variants) > 1 else [],
                "variantes": sorted(self.variants)}


@dataclass
class Inventory:
    inks: list[InkUse]
    process_used: dict          # {"DeviceCMYK": n, "DeviceRGB": n, "DeviceGray": n, "ICC-RGB": n, ..., "Lab": n}
    pages: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"tintas": [i.to_dict() for i in self.inks], "espacios": self.process_used, "paginas": self.pages,
                "avisos": self.warnings,
                "duplicadas": [i.norm for i in self.inks if len(i.variants) > 1],
                "no_usadas": [i.name for i in self.inks if i.objects == 0 and i.kind != "process"]}


def _name(o) -> str:
    return str(o).lstrip("/")


def _dec(name: str) -> str:
    return name  # pikepdf ya decodifica los #XX de los nombres


class _Walker:
    def __init__(self):
        self.inks: dict[str, InkUse] = {}
        self.used_spaces: dict[str, int] = defaultdict(int)
        self.warnings: list[str] = []
        self._seen_forms: set = set()
        self._cs_cache: dict = {}

    # ---------------------------------------------------------------- espacios de color
    def describe_cs(self, cso, resources=None):
        """Devuelve (tipo, [tintas]) de un espacio de color. tipo: 'DeviceGray'|'DeviceRGB'|'DeviceCMYK'|'ICC-n'|'Lab'|
        'Separation'|'DeviceN'|'Pattern'. Para Separation/DeviceN registra las tintas en self.inks."""
        try:
            if isinstance(cso, pikepdf.Name):
                n = _name(cso)
                if n in ("DeviceGray", "G", "CalGray"):
                    return "DeviceGray", []
                if n in ("DeviceRGB", "RGB", "CalRGB"):
                    return "DeviceRGB", []
                if n in ("DeviceCMYK", "CMYK"):
                    return "DeviceCMYK", []
                if n == "Pattern":
                    return "Pattern", []
                if resources is not None and "/ColorSpace" in resources and cso in resources.ColorSpace:
                    return self.describe_cs(resources.ColorSpace[cso], resources)
                return n, []
            if isinstance(cso, pikepdf.Array) and len(cso) > 0:
                kind = _name(cso[0])
                if kind == "ICCBased":
                    n = int(cso[1].get("/N", 0))
                    return {1: "ICC-Gray", 3: "ICC-RGB", 4: "ICC-CMYK"}.get(n, f"ICC-{n}"), []
                if kind in ("CalRGB", "CalGray"):
                    return ("DeviceRGB" if kind == "CalRGB" else "DeviceGray"), []
                if kind == "Lab":
                    return "Lab", []
                if kind == "Indexed":
                    return self.describe_cs(cso[1], resources)
                if kind == "Pattern":
                    return "Pattern", ([] if len(cso) < 2 else self.describe_cs(cso[1], resources)[1])
                if kind == "Separation":
                    return "Separation", [self._register(_name(cso[1]), "Separation", cso[2], cso[3], resources)]
                if kind == "DeviceN":
                    names = [_name(x) for x in cso[1]]
                    inks = [self._register(n, "DeviceN", cso[2], cso[3], resources, colorant_index=i, n_colorants=len(names))
                            for i, n in enumerate(names) if n != "None"]
                    return "DeviceN", inks
        except Exception as e:  # PDF raro: se avisa y se sigue
            self.warnings.append(f"No se pudo interpretar un espacio de color ({type(e).__name__}).")
        return "desconocido", []

    def _register(self, name, space, alt, tint_fn, resources, colorant_index=None, n_colorants=1):
        norm = inkmod.normalize_name(name)
        if norm == "NONE":
            return None
        ink = self.inks.get(norm)
        if ink is None:
            kind = "process" if norm in ("CYAN", "MAGENTA", "YELLOW", "BLACK") else inkmod.classify_ink(name)
            if norm == "ALL":
                kind = "technical"
            ink = InkUse(name=name, norm=norm, kind=kind, space=space)
            self.inks[norm] = ink
            self._alternate(ink, alt, tint_fn, colorant_index, n_colorants, resources)
        ink.variants.add(name)
        return ink

    def _alternate(self, ink, alt, fn, idx, n, resources):
        """Color de la tinta al 100 % según su espacio alternativo (evaluando la tint transform)."""
        try:
            alt_t, _ = self.describe_cs(alt, resources)
            ink.alt_space = alt_t
            ink.alt_is_rgb = alt_t in ("DeviceRGB", "ICC-RGB")
            tints = [0.0] * n
            if idx is None:
                tints = [1.0]
            else:
                tints[idx] = 1.0
            comps = evaluate(fn, tints)
            if alt_t in ("DeviceCMYK", "ICC-CMYK") and len(comps) >= 4:
                ink.alt_cmyk = tuple(float(min(max(v, 0), 1)) for v in comps[:4])
                ink.lab = tuple(float(v) for v in cs.mix_inks(inkmod.PAPER_PC1, _proc_inks(), list(ink.alt_cmyk)))
            elif alt_t in ("DeviceRGB", "ICC-RGB") and len(comps) >= 3:
                ink.lab = tuple(float(v) for v in cs.srgb_to_lab(np.clip(np.array(comps[:3]), 0, 1)))
            elif alt_t in ("DeviceGray", "ICC-Gray") and comps:
                g = float(min(max(comps[0], 0), 1))
                ink.lab = tuple(float(v) for v in cs.srgb_to_lab(np.array([g, g, g])))
            elif alt_t == "Lab" and len(comps) >= 3:
                ink.lab = (float(comps[0]), float(comps[1]), float(comps[2]))
        except FunctionError as e:
            self.warnings.append(f"No se pudo evaluar la tinta «{ink.name}»: {e}")
        except Exception:
            pass

    # ---------------------------------------------------------------- recorrido
    def walk_page(self, page, page_no):
        res = page.get("/Resources")
        # definiciones (aunque nada las pinte)
        if res is not None:
            self._defs(res, set())
        streams = page.get("/Contents")
        if streams is not None:
            self._content(page, res, page_no, set())
        for annot in (page.get("/Annots") or []):
            try:
                ap = annot.get("/AP")
                if ap is not None and "/N" in ap:
                    n = ap["/N"]
                    if isinstance(n, pikepdf.Stream):
                        self._form(n, page_no, set())
            except Exception:
                pass

    def _defs(self, res, seen):
        key = res.objgen if res.is_indirect else id(res)
        if key in seen:
            return
        seen.add(key)
        for _, cso in (res.get("/ColorSpace") or {}).items():
            t, _ = self.describe_cs(cso, res)
        for _, xo in (res.get("/XObject") or {}).items():
            r = xo.get("/Resources")
            if r is not None:
                self._defs(r, seen)

    def _form(self, form, page_no, stack):
        key = form.objgen
        if key in stack:
            return
        stack = stack | {key}
        self._content(form, form.get("/Resources"), page_no, stack)

    def _content(self, obj, res, page_no, stack):
        if res is None:
            res = pikepdf.Dictionary()
        try:
            ops = pikepdf.parse_content_stream(obj)
        except Exception:
            self.warnings.append("No se pudo leer el contenido de una página o formulario.")
            return
        state = {"fill": ("DeviceGray", []), "stroke": ("DeviceGray", [])}
        stackq = []
        for operands, op in ops:
            o = str(op)
            if o == "q":
                stackq.append(dict(state))
            elif o == "Q":
                if stackq:
                    state = stackq.pop()
            elif o in ("cs", "CS"):
                d = self.describe_cs(operands[0], res)
                state["fill" if o == "cs" else "stroke"] = d
            elif o in ("g", "G"):
                state["fill" if o == "g" else "stroke"] = ("DeviceGray", [])
            elif o in ("rg", "RG"):
                state["fill" if o == "rg" else "stroke"] = ("DeviceRGB", [])
            elif o in ("k", "K"):
                state["fill" if o == "k" else "stroke"] = ("DeviceCMYK", [])
            elif o in PAINT_FILL | PAINT_STROKE | PAINT_TEXT:
                if o in PAINT_FILL or o in PAINT_TEXT:
                    self._paint(state["fill"], page_no)
                if o in PAINT_STROKE:
                    self._paint(state["stroke"], page_no)
            elif o == "sh":
                sh = (res.get("/Shading") or {}).get(operands[0])
                if sh is not None and "/ColorSpace" in sh:
                    self._paint(self.describe_cs(sh["/ColorSpace"], res), page_no)
            elif o == "Do":
                xo = (res.get("/XObject") or {}).get(operands[0])
                if xo is None:
                    continue
                sub = str(xo.get("/Subtype"))
                if sub == "/Form":
                    self._form(xo, page_no, stack)
                elif sub == "/Image":
                    if "/ColorSpace" in xo:
                        self._paint(self.describe_cs(xo["/ColorSpace"], res), page_no)
                    else:
                        self.used_spaces["DeviceGray"] += 1

    def _paint(self, cs_state, page_no):
        t, inks = cs_state
        if t in ("Separation", "DeviceN"):
            self.used_spaces[t] += 1
            for i in inks:
                if i is not None:
                    i.objects += 1
                    i.pages.add(page_no)
        elif t == "Pattern":
            for i in inks:
                if i is not None:
                    i.objects += 1
                    i.pages.add(page_no)
            self.used_spaces["Pattern"] += 1
        else:
            self.used_spaces[t] += 1


def read_inventory(path) -> Inventory:
    try:
        pdf = pikepdf.open(str(path))
    except pikepdf.PasswordError:
        raise UserError("El PDF está protegido con contraseña.")
    except Exception:
        raise UserError("El PDF está dañado o no se puede abrir.")
    with pdf:
        w = _Walker()
        for i, page in enumerate(pdf.pages, 1):
            w.walk_page(page.obj, i)
        # las tintas de proceso del PDF (CMYK) también se listan, aunque no sean Separation
        inks = list(w.inks.values())
        for i in inks:
            i.defined = True
        proc_names = {i.norm for i in inks}
        used = {k: v for k, v in w.used_spaces.items() if v}
        return Inventory(inks=inks, process_used=used, pages=len(pdf.pages), warnings=list(dict.fromkeys(w.warnings)))
