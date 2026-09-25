"""Nivel 1 – vocabulario y patrones aprendidos de los casos revisados."""
import re

from . import store

_cache: dict = {"mtime": None, "words": set()}
_NUM = re.compile(r"\d")


def _read() -> dict[str, int]:
    p = store.path("vocabulario.txt")
    out: dict[str, int] = {}
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            w, _, c = ln.partition("\t")
            out[w.strip().lower()] = int(c) if c.strip().isdigit() else 1
    return out


def _write(d: dict[str, int]) -> None:
    lines = [f"{w}\t{c}" for w, c in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))]
    store.path("vocabulario.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    _cache["mtime"] = None


def counts() -> dict[str, int]:
    return _read()


def known_words() -> set[str]:
    """Palabras aprendidas (el corrector ortográfico no las marca)."""
    if not store.enabled():
        return set()
    p = store.path("vocabulario.txt")
    m = p.stat().st_mtime if p.exists() else None
    if _cache["mtime"] != m or _cache["mtime"] is None:
        _cache["words"] = set(_read())
        _cache["mtime"] = m
    return _cache["words"]


def add_words(words, weight: int = 1) -> int:
    d = _read()
    n = 0
    for w in words:
        w = w.strip().lower()
        if len(w) < 3 or _NUM.search(w):
            continue
        d[w] = d.get(w, 0) + weight
        n += 1
    _write(d)
    return n


def remove_word(word: str) -> None:
    d = _read()
    d.pop(word.strip().lower(), None)
    _write(d)


def pattern_of(token: str) -> str | None:
    """Patrón de Tesseract para un token con dígitos: $10.000 → $\\d\\d.\\d\\d\\d (precios, teléfonos, fechas)."""
    if not _NUM.search(token) or len(token) < 3 or len(token) > 24:
        return None
    out = []
    for ch in token:
        if ch.isdigit():
            out.append("\\d")
        elif ch.isalpha():
            out.append("\\A" if ch.isupper() else "\\a")
        elif ch in "\\*?+[]":
            return None
        else:
            out.append(ch)
    return "".join(out)


def add_patterns(tokens) -> None:
    p = store.path("patrones.txt")
    cur = set(p.read_text(encoding="utf-8").splitlines()) if p.exists() else set()
    for t in tokens:
        pat = pattern_of(t.strip(".,;:"))
        if pat:
            cur.add(pat)
    p.write_text("\n".join(sorted(cur)) + ("\n" if cur else ""), encoding="utf-8")


def add_from_review(result, design_path) -> None:
    """Palabras del diseño que el corrector desconoce (marcas, nombres) y que NO se confirmaron como error."""
    from ..loaders import extract_pdf_layout
    from ..spelling import is_known_word_dictionaries

    real_spelling = {d.found.lower() for d in result.differences
                     if d.category == "spelling" and d.review == "real" and d.found}
    spans = extract_pdf_layout(design_path, 200, result.pages.get("design", 1) - 1)
    words, tokens = [], []
    for sp in spans:
        for t, _ in sp.words:
            tokens.append(t)
            w = re.sub(r"^[^\w]+|[^\w]+$", "", t).lower()
            if w and w not in real_spelling and not is_known_word_dictionaries(w):
                words.append(w)
    add_words(words)
    add_patterns(tokens)


def ocr_extra_config(full: bool = True) -> str:
    """Argumentos de Tesseract con lo aprendido ("" si no hay). Los patrones son baratos; el vocabulario
    (`--user-words`) cuesta ~0,25 s por lectura, así que `full=False` lo omite (primera lectura de cada línea) y
    `full=True` lo incluye (relecturas y verificaciones, donde de verdad ayuda)."""
    if not store.enabled():
        return ""
    parts = []
    if full:
        d = _read()
        if d:
            wp = store.path("vocabulario_tesseract.txt")
            wp.write_text("\n".join(sorted(d)) + "\n", encoding="utf-8")
            parts.append(f"--user-words {wp.as_posix()}")
    pp = store.path("patrones.txt")
    if pp.exists() and pp.read_text(encoding="utf-8").strip():
        parts.append(f"--user-patterns {pp.as_posix()}")
    return " ".join(parts)
