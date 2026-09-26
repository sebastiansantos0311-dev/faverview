"""Modelo de tintas, normalización de nombres y bibliotecas del usuario (CxF3, ASE, CSV, JSON).

Las bibliotecas Pantone/HKS/RAL/TOYO/DIC tienen licencia: FAVERVIEW NO las incluye. El usuario importa las suyas
(se guardan en datos_locales/tintas/, que nunca se sube a GitHub). Lo que sí trae la app: las cuatro tintas de proceso con
los valores de referencia públicos de ISO 12647-2 PC1 (FOGRA51), blanco, barniz y tintas técnicas."""
import csv
import io
import json
import re
import struct
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from app.config import DATOS_DIR, load_config
from app.core import colorscience as cs
from app.core.errors import UserError

Kind = Literal["process", "spot", "white", "varnish", "technical"]
KINDS = ("process", "spot", "white", "varnish", "technical")


class Ink(BaseModel):
    name: str
    kind: Kind = "spot"
    lab: tuple[float, float, float] | None = None       # sólido al 100 % sobre el sustrato de referencia
    alt_cmyk: tuple[float, float, float, float] | None = None  # alternativa del PDF (0–1)
    opacity: float = 0.0                                  # 0 = transparente (proceso), 1 = opaca (blanco, metálicos)
    print_order: int | None = None
    source: str = ""                                      # "pdf", "biblioteca:<nombre>", "usuario"

    def swatch_hex(self) -> str | None:
        """Color sRGB APROXIMADO para mostrar en pantalla (el color de impresión no siempre cabe en sRGB)."""
        if self.lab is not None:
            return cs.lab_to_hex(self.lab)
        if self.alt_cmyk is not None:
            c, m, y, k = self.alt_cmyk
            return "#%02X%02X%02X" % tuple(int(round(255 * (1 - min(1, v + k)))) for v in (c, m, y))
        return None


class InkLibrary(BaseModel):
    name: str
    inks: list[Ink] = Field(default_factory=list)
    readonly: bool = False


# ---------------------------------------------------------------- nombres
def normalize_name(name: str) -> str:
    """Une variantes de un mismo nombre: mayúsculas, sin espacios dobles, PANTONE/PMS/P unificados y sufijos
    C/U/M/CP/UP separados por un espacio: «Pantone 485C» ≡ «PANTONE 485 C»."""
    n = re.sub(r"\s+", " ", (name or "").replace("®", "").strip()).upper()
    n = re.sub(r"^(?:PANTONE|PMS|P)\s*[-_ ]?(?=\d)", "PANTONE ", n)
    n = re.sub(r"(\d)\s*(CP|UP|C|U|M)$", r"\1 \2", n)
    return re.sub(r"\s+", " ", n).strip()


_PROCESS = {"cyan": "C", "cian": "C", "magenta": "M", "yellow": "Y", "amarillo": "Y", "black": "K", "negro": "K", "key": "K"}


def classify_ink(name: str) -> Kind:
    """Tipo de tinta a partir del nombre (palabras clave configurables en config.json → ink_keywords)."""
    n = normalize_name(name).lower()
    if n in _PROCESS or n in ("c", "m", "y", "k"):
        return "process"
    kw = load_config().get("ink_keywords", {})
    for kind in ("white", "varnish", "technical"):
        for w in kw.get(kind, []):
            if re.search(rf"(?<![a-zñáéíóú]){re.escape(w.lower())}", n):
                return kind  # type: ignore[return-value]
    return "spot"


# ---------------------------------------------------------------- biblioteca incorporada (valores públicos de referencia)
def builtin_library() -> InkLibrary:
    """Cian, magenta, amarillo y negro con los Lab sólidos de referencia de ISO 12647-2 PC1 (FOGRA51), más blanco,
    barniz y tintas técnicas. Son valores de referencia públicos de la caracterización, no de una tinta concreta."""
    return InkLibrary(name="ISO 12647-2 PC1 (FOGRA51) + básicas", readonly=True, inks=[
        Ink(name="Cyan", kind="process", lab=(55.0, -37.0, -50.0), alt_cmyk=(1, 0, 0, 0), print_order=1, source="referencia"),
        Ink(name="Magenta", kind="process", lab=(48.0, 74.0, -3.0), alt_cmyk=(0, 1, 0, 0), print_order=2, source="referencia"),
        Ink(name="Yellow", kind="process", lab=(89.0, -5.0, 93.0), alt_cmyk=(0, 0, 1, 0), print_order=3, source="referencia"),
        Ink(name="Black", kind="process", lab=(16.0, 0.0, 0.0), alt_cmyk=(0, 0, 0, 1), print_order=4, source="referencia"),
        Ink(name="Blanco", kind="white", lab=(94.0, 0.0, -2.0), opacity=1.0, source="referencia"),
        Ink(name="Barniz", kind="varnish", source="referencia"),
        Ink(name="Troquel", kind="technical", source="referencia"),
        Ink(name="Braille", kind="technical", source="referencia"),
        Ink(name="Cotas", kind="technical", source="referencia"),
    ])


PAPER_PC1 = (95.0, 0.0, -2.0)   # papel de referencia PC1 (Lab D50)


# ---------------------------------------------------------------- importadores
def _f(x: str) -> float:
    return float(str(x).strip().replace(",", "."))


def import_csv(text: str, source: str = "csv") -> list[Ink]:
    """CSV `nombre,L,a,b[,tipo][,opacidad]` (coma, punto y coma o tabulador; decimales con punto o coma)."""
    text = text.lstrip("﻿")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = ";" if ";" in first else ("\t" if "\t" in first else ",")  # con «;» los decimales pueden llevar coma
    inks, errors = [], []
    for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim), 1):
        row = [c.strip() for c in row if c is not None]
        if not row or not row[0] or row[0].startswith("#"):
            continue
        if len(row) < 4:
            errors.append(f"línea {i}: faltan columnas (nombre,L,a,b)")
            continue
        try:
            L, a, b = _f(row[1]), _f(row[2]), _f(row[3])
        except ValueError:
            if i == 1:
                continue  # encabezado
            errors.append(f"línea {i}: L, a y b deben ser números")
            continue
        if not (0 <= L <= 100 and -200 <= a <= 200 and -200 <= b <= 200):
            errors.append(f"línea {i}: valores Lab fuera de rango")
            continue
        kind = row[4].lower() if len(row) > 4 and row[4] else classify_ink(row[0])
        if kind not in KINDS:
            kind = classify_ink(row[0])
        opacity = _f(row[5]) if len(row) > 5 and row[5] else (1.0 if kind == "white" else 0.0)
        inks.append(Ink(name=row[0], kind=kind, lab=(L, a, b), opacity=min(1.0, max(0.0, opacity)), source=source))
    if not inks:
        raise UserError("No se encontró ninguna tinta en el CSV. Formato: nombre,L,a,b[,tipo][,opacidad]."
                        + (" " + "; ".join(errors[:3]) if errors else ""))
    return inks


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def import_cxf(data: bytes, source: str = "cxf") -> list[Ink]:
    """CxF3 (ISO 17972, XML): cada `Object` con un `ColorCIELab` se importa como una tinta directa."""
    from lxml import etree
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
    except Exception:
        raise UserError("El archivo no es un CxF válido (XML mal formado).")
    inks = []
    for obj in root.iter():
        if _local(obj.tag) != "Object":
            continue
        name = obj.get("Name") or obj.get("name") or obj.get("Id") or ""
        lab = None
        for el in obj.iter():
            if _local(el.tag) == "ColorCIELab":
                vals = {_local(c.tag).upper(): c.text for c in el}
                try:
                    lab = (_f(vals["L"]), _f(vals["A"]), _f(vals["B"]))
                except (KeyError, ValueError, TypeError):
                    lab = None
                break
        if name and lab:
            inks.append(Ink(name=name, kind=classify_ink(name), lab=lab, source=source))
    if not inks:
        raise UserError("No se encontraron colores con valores Lab en el CxF. FAVERVIEW lee el bloque ColorCIELab de cada objeto.")
    return inks


def import_ase(data: bytes, source: str = "ase") -> list[Ink]:
    """Adobe Swatch Exchange (binario, big-endian). Lab/RGB/CMYK/Gray; CMYK se convierte a Lab con el modelo de mezcla."""
    if data[:4] != b"ASEF":
        raise UserError("El archivo no es un ASE válido (no empieza por «ASEF»).")
    try:
        nblocks = struct.unpack(">I", data[8:12])[0]
        pos, inks = 12, []
        proc = builtin_library().inks[:4]
        for _ in range(nblocks):
            btype, blen = struct.unpack(">HI", data[pos:pos + 6])
            body = data[pos + 6:pos + 6 + blen]
            pos += 6 + blen
            if btype != 0x0001:
                continue
            nlen = struct.unpack(">H", body[:2])[0]
            name = body[2:2 + nlen * 2].decode("utf-16-be").rstrip("\x00")
            off = 2 + nlen * 2
            model = body[off:off + 4].decode("ascii", "replace")
            off += 4
            ctype = struct.unpack(">H", body[-2:])[0]
            if model == "LAB ":
                L, a, b = struct.unpack(">3f", body[off:off + 12])
                lab, cmyk = (L * 100 if L <= 1.0 else L, a, b), None
            elif model == "CMYK":
                c, m, y, k = struct.unpack(">4f", body[off:off + 16])
                cmyk = (c, m, y, k)
                lab = tuple(float(v) for v in cs.mix_inks(PAPER_PC1, [{"lab": i.lab, "opacity": 0} for i in proc],
                                                            [c, m, y, k]))
            elif model == "RGB ":
                rgb = struct.unpack(">3f", body[off:off + 12])
                lab, cmyk = tuple(float(v) for v in cs.srgb_to_lab(np.array(rgb))), None
            elif model == "Gray":
                g = struct.unpack(">f", body[off:off + 4])[0]
                lab, cmyk = tuple(float(v) for v in cs.srgb_to_lab(np.array([g, g, g]))), None
            else:
                continue
            kind = classify_ink(name) if ctype == 1 else ("process" if normalize_name(name) in ("CYAN", "MAGENTA", "YELLOW", "BLACK") else "spot")
            inks.append(Ink(name=name, kind=kind, lab=lab, alt_cmyk=cmyk, source=source))
    except (struct.error, UnicodeDecodeError, IndexError):
        raise UserError("El archivo ASE está dañado o incompleto.")
    if not inks:
        raise UserError("El ASE no contiene colores utilizables.")
    return inks


def import_any(filename: str, data: bytes) -> list[Ink]:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    src = f"biblioteca:{filename}"
    if ext == "ase":
        return import_ase(data, src)
    if ext in ("cxf", "xml", "cxf3"):
        return import_cxf(data, src)
    if ext in ("csv", "txt", "tsv"):
        return import_csv(data.decode("utf-8", "replace"), src)
    if ext == "json":
        return InkLibrary.model_validate_json(data).inks
    raise UserError(f"Formato de biblioteca no admitido (.{ext}). Usa CxF, ASE, CSV o JSON.")


# ---------------------------------------------------------------- exportadores
def to_json(lib: InkLibrary) -> str:
    return lib.model_dump_json(indent=1)


def to_csv(lib: InkLibrary) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["nombre", "L", "a", "b", "tipo", "opacidad"])
    for i in lib.inks:
        L, a, b = i.lab if i.lab else ("", "", "")
        w.writerow([i.name, L, a, b, i.kind, i.opacity])
    return out.getvalue()


def dedupe(inks: list[Ink]) -> list[Ink]:
    """Une tintas con el mismo nombre normalizado (gana la primera que tenga Lab)."""
    seen: dict[str, Ink] = {}
    for i in inks:
        k = normalize_name(i.name)
        if k not in seen or (seen[k].lab is None and i.lab is not None):
            seen[k] = i
    return list(seen.values())


# ---------------------------------------------------------------- almacenamiento
def library_dir():
    d = DATOS_DIR / "tintas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(name: str) -> str:
    n = re.sub(r"[^\w\- .()áéíóúñÁÉÍÓÚÑ]", "", name or "").strip().strip(".")
    if not n:
        raise UserError("Ponle un nombre a la biblioteca.")
    return n[:80]


def list_libraries() -> list[dict]:
    out = [{"nombre": builtin_library().name, "tintas": len(builtin_library().inks), "solo_lectura": True}]
    for p in sorted(library_dir().glob("*.json")):
        try:
            lib = InkLibrary.model_validate_json(p.read_text(encoding="utf-8"))
            out.append({"nombre": lib.name, "tintas": len(lib.inks), "solo_lectura": False})
        except Exception:
            continue
    return out


def load_library(name: str) -> InkLibrary:
    if name == builtin_library().name:
        return builtin_library()
    p = library_dir() / f"{_safe(name)}.json"
    if not p.exists():
        raise UserError("No existe esa biblioteca de tintas.")
    return InkLibrary.model_validate_json(p.read_text(encoding="utf-8"))


def save_library(lib: InkLibrary) -> InkLibrary:
    if lib.name == builtin_library().name:
        raise UserError("La biblioteca incorporada es de solo lectura: duplícala con otro nombre para editarla.")
    lib.name = _safe(lib.name)
    lib.readonly = False
    (library_dir() / f"{lib.name}.json").write_text(to_json(lib), encoding="utf-8")
    return lib


def delete_library(name: str) -> None:
    if name == builtin_library().name:
        raise UserError("La biblioteca incorporada no se puede borrar.")
    (library_dir() / f"{_safe(name)}.json").unlink(missing_ok=True)


def lookup(name: str, libraries: list[InkLibrary]) -> Ink | None:
    """Busca una tinta por nombre normalizado en las bibliotecas dadas (en orden)."""
    key = normalize_name(name)
    for lib in libraries:
        for i in lib.inks:
            if normalize_name(i.name) == key:
                return i
    return None
