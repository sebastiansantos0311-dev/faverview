"""Nivel 2 – confusiones de lectura del OCR aprendidas (rn→m, l→i, e→é, …).

Regla de seguridad: una sustitución dígito↔dígito (10.000 → 12.000) NUNCA se considera error de lectura."""
import re
from difflib import SequenceMatcher

from . import store

FILE = "confusiones.json"
_DIGIT = re.compile(r"\d")


def char_edits(read: str, true: str) -> list[tuple[str, str]]:
    """Ediciones de caracteres para pasar de lo leído a lo correcto: [(leído, correcto), …]."""
    sm = SequenceMatcher(None, read, true, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            out.append((read[i1:i2], true[j1:j2]))
    return out


def _key(r: str, t: str) -> str:
    return f"{r}>{t}"


def load() -> dict:
    return store.load_json(FILE, {"pares": {}, "ejemplos": {}})


def add_pair(read: str, true: str, context: dict | None = None) -> None:
    edits = char_edits(read, true)
    if not edits or len(edits) > 3:
        return
    data = load()
    for r, t in edits:
        if _DIGIT.search(r) and _DIGIT.search(t):  # dígito↔dígito: nunca es lectura errónea
            continue
        k = _key(r, t)
        data["pares"][k] = data["pares"].get(k, 0) + 1
        ex = data["ejemplos"].setdefault(k, [])
        if len(ex) < 3 and [read, true] not in ex:
            ex.append([read, true])
    store.save_json(FILE, data)


def add_from_review(result) -> None:
    """Cada error de texto marcado ✘ (falso positivo) es una lectura equivocada: (leído, correcto)."""
    for d in result.differences:
        if d.category == "text" and d.review == "falso_positivo" and d.subtype in ("cambiada", "mayusculas") \
                and d.expected and d.found:
            add_pair(d.expected, d.found)


def explains(read: str, true: str, min_count: int = 3) -> bool:
    """¿La diferencia se explica SOLO con confusiones vistas ≥ `min_count` veces (y sin dígito↔dígito)?"""
    if not read or not true or read == true:
        return False
    edits = char_edits(read, true)
    if not edits or len(edits) > 3:
        return False
    pares = load()["pares"]
    for r, t in edits:
        if _DIGIT.search(r) and _DIGIT.search(t):
            return False
        if pares.get(_key(r, t), 0) < min_count:
            return False
    return True


def remove(key: str) -> None:
    data = load()
    data["pares"].pop(key, None)
    data["ejemplos"].pop(key, None)
    store.save_json(FILE, data)


def summary() -> list[dict]:
    d = load()
    rows = [{"clave": k, "leido": k.split(">", 1)[0], "correcto": k.split(">", 1)[1], "veces": v,
             "ejemplos": d["ejemplos"].get(k, [])} for k, v in d["pares"].items()]
    return sorted(rows, key=lambda r: -r["veces"])
