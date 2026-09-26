"""Edición de tintas de un PDF (S2 §6.4): trabaja siempre sobre una copia; el original nunca se toca.

Operaciones: renombrar / unir duplicadas (mapa A→B), convertir una directa a proceso CMYK, eliminar definiciones sin uso."""
from pathlib import Path

import numpy as np
import pikepdf

from app.core import inks as inkmod
from app.core.errors import UserError
from app.core.pdffunctions import FunctionError, evaluate
from app.modules.separate.pdf_inks import _name, read_inventory


def _walk(pdf):
    """Recorre todo el grafo de objetos (incluidos los directos) sin repetir los indirectos."""
    seen = set()
    stack = [pdf.Root]
    while stack:
        o = stack.pop()
        if isinstance(o, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)):
            if o.is_indirect:
                if o.objgen in seen:
                    continue
                seen.add(o.objgen)
            yield o
            if isinstance(o, pikepdf.Array):
                stack.extend(o)
            else:
                for k, v in o.items():
                    if k in ("/Parent", "/P"):
                        continue
                    stack.append(v)


def _iter_colorspaces(pdf):
    """Todas las arrays [/Separation …] y [/DeviceN …] del documento."""
    for obj in _walk(pdf):
        if isinstance(obj, pikepdf.Array) and len(obj) >= 4 and isinstance(obj[0], pikepdf.Name)                 and str(obj[0]) in ("/Separation", "/DeviceN"):
            yield obj


def rename_inks(pdf, mapping: dict[str, str]) -> int:
    """Cambia el nombre de las tintas (Separation y DeviceN) según `mapping` (claves normalizadas). Devuelve nº de cambios."""
    norm_map = {inkmod.normalize_name(k): v for k, v in mapping.items()}
    changed = 0
    for arr in _iter_colorspaces(pdf):
        if str(arr[0]) == "/Separation":
            new = norm_map.get(inkmod.normalize_name(_name(arr[1])))
            if new and new != _name(arr[1]):
                arr[1] = pikepdf.Name("/" + new)
                changed += 1
        else:
            names = arr[1]
            for i in range(len(names)):
                new = norm_map.get(inkmod.normalize_name(_name(names[i])))
                if new and new != _name(names[i]):
                    names[i] = pikepdf.Name("/" + new)
                    changed += 1
    # /Colorants de atributos NChannel
    for arr in _iter_colorspaces(pdf):
        if str(arr[0]) == "/DeviceN" and len(arr) > 4 and isinstance(arr[4], pikepdf.Dictionary) and "/Colorants" in arr[4]:
            col = arr[4]["/Colorants"]
            for k in list(col.keys()):
                new = norm_map.get(inkmod.normalize_name(_name(k)))
                if new and new != _name(k):
                    col[pikepdf.Name("/" + new)] = col[k]
                    del col[k]
    return changed


def _spot_to_cmyk(cso, tint: float) -> list[float]:
    """Evalúa la función de un Separation contra su espacio alternativo (debe ser DeviceCMYK o ICC-CMYK)."""
    alt = cso[2]
    kind = _name(alt) if isinstance(alt, pikepdf.Name) else _name(alt[0])
    if kind == "DeviceCMYK" or (kind == "ICCBased" and int(alt[1].get("/N", 0)) == 4):
        return [min(max(v, 0.0), 1.0) for v in evaluate(cso[3], [tint])]
    raise UserError("Solo se pueden convertir a proceso las directas cuyo color alternativo es CMYK.")


def convert_to_process(pdf, targets: set[str]) -> int:
    """Reescribe el contenido: las directas cuyo nombre normalizado esté en `targets` pasan a `k`/`K` con su equivalente CMYK."""
    total = [0]
    done_forms: set = set()

    def is_target(res, name_obj):
        try:
            cso = res["/ColorSpace"][name_obj]
        except Exception:
            return None
        if isinstance(cso, pikepdf.Array) and str(cso[0]) == "/Separation" and inkmod.normalize_name(_name(cso[1])) in targets:
            return cso
        return None

    def process(stream_obj, res, is_page):
        res = res if res is not None else pikepdf.Dictionary()
        try:
            ops = pikepdf.parse_content_stream(stream_obj)
        except Exception:
            return
        out = []
        cur = {"cs": None, "CS": None}     # espacio Separation objetivo activo (fill / stroke)
        stack = []
        modified = False
        for operands, op in ops:
            o = str(op)
            if o == "q":
                stack.append(dict(cur))
            elif o == "Q" and stack:
                cur = stack.pop()
            elif o in ("cs", "CS"):
                t = is_target(res, operands[0])
                cur[o] = t
                if t is not None:
                    modified = True
                    continue                       # se elimina la selección del espacio
            elif o in ("scn", "sc", "SCN", "SC"):
                key = "cs" if o.islower() else "CS"
                t = cur[key]
                if t is not None:
                    cmyk = _spot_to_cmyk(t, float(operands[0]))
                    out.append(pikepdf.ContentStreamInstruction([float(round(v, 4)) for v in cmyk],
                                                                 pikepdf.Operator("k" if key == "cs" else "K")))
                    total[0] += 1
                    modified = True
                    continue
            elif o in ("g", "rg", "k", "G", "RG", "K"):
                cur["cs" if o.islower() else "CS"] = None
            elif o == "Do":
                xo = (res.get("/XObject") or {}).get(operands[0])
                if xo is not None and str(xo.get("/Subtype")) == "/Form" and xo.objgen not in done_forms:
                    done_forms.add(xo.objgen)
                    process(xo, xo.get("/Resources"), False)
            out.append(pikepdf.ContentStreamInstruction(operands, op))
        if modified:
            data = pikepdf.unparse_content_stream(out)
            stream_obj.write(data)

    for page in pdf.pages:
        contents = page.obj.get("/Contents")
        if contents is None:
            continue
        # se unen los flujos del contenido para poder reescribirlos como uno
        data = b"\n".join(s.read_bytes() for s in (contents if isinstance(contents, pikepdf.Array) else [contents]))
        page.obj["/Contents"] = pdf.make_stream(data)
        process(page.obj["/Contents"], page.obj.get("/Resources"), True)
    return total[0]


def remove_unused(pdf, names_norm: set[str]) -> int:
    """Quita de los recursos las definiciones de Separation sin uso."""
    n = 0
    for obj in list(_walk(pdf)):
        if isinstance(obj, pikepdf.Dictionary) and not isinstance(obj, pikepdf.Stream) and "/ColorSpace" in obj:
            cs = obj["/ColorSpace"]
            if not isinstance(cs, pikepdf.Dictionary):
                continue
            for k in list(cs.keys()):
                v = cs[k]
                if isinstance(v, pikepdf.Array) and len(v) >= 4 and str(v[0]) == "/Separation" \
                        and inkmod.normalize_name(_name(v[1])) in names_norm:
                    del cs[k]
                    n += 1
    return n


def apply_edits(src, dst, *, rename: dict[str, str] | None = None, convert: list[str] | None = None,
                delete_unused: bool = False) -> dict:
    """Aplica las ediciones a una copia `dst` (nunca sobre `src`). Devuelve un resumen y el inventario resultante."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise UserError("No se puede sobrescribir el PDF original.")
    inv0 = read_inventory(src)
    unused = {i.norm for i in inv0.inks if i.objects == 0 and i.kind != "process"}
    try:
        pdf = pikepdf.open(str(src))
    except Exception:
        raise UserError("El PDF está dañado o no se puede abrir.")
    summary = {"renombradas": 0, "convertidas": 0, "eliminadas": 0}
    with pdf:
        if convert:
            try:
                summary["convertidas"] = convert_to_process(pdf, {inkmod.normalize_name(c) for c in convert})
            except FunctionError as e:
                raise UserError(f"No se pudo evaluar el color de la tinta: {e}")
            if not summary["convertidas"]:
                raise UserError("No se encontró ningún objeto para convertir. Solo se convierten tintas directas simples "
                                "(Separation); las de DeviceN no se pueden convertir todavía.")
        if rename:
            summary["renombradas"] = rename_inks(pdf, rename)
        if delete_unused and unused:
            summary["eliminadas"] = remove_unused(pdf, unused)
        pdf.save(str(dst))
    summary["inventario"] = read_inventory(dst).to_dict()
    return summary


def verify_untouched(src, dst, touched: set[str], page: int = 0, dpi: float = 100) -> dict:
    """Renderiza ambos PDF y compara las placas de las tintas no tocadas (diferencia media en % de tinta)."""
    from app.modules.separate.pdf_render import render_plates
    a = render_plates(src, page, dpi, use_cache=False)
    b = render_plates(dst, page, dpi, use_cache=False)
    touched = {inkmod.normalize_name(t) for t in touched}
    diffs = {}
    for n in a.names:
        if inkmod.normalize_name(n) in touched or n not in b.arrays:
            continue
        d = np.abs(a.arrays[n].astype(np.int16) - b.arrays[n].astype(np.int16)).mean() / 255 * 100
        diffs[n] = round(float(d), 4)
    return {"diferencias": diffs, "maximo": max(diffs.values(), default=0.0)}
