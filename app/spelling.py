"""Ortografía en español con pyspellchecker + diccionario personal."""
import re
import threading

from spellchecker import SpellChecker

from .compare_text import Word
from .config import BASE_DIR, DATA_DIR
from .models import Difference

DICT_PATH = DATA_DIR / "diccionario_personal.txt"
_lock = threading.Lock()
_spell: SpellChecker | None = None
_TRIM = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)


def _personal_words() -> list[str]:
    if not DICT_PATH.exists():
        return []
    return [w.strip().lower() for w in DICT_PATH.read_text(encoding="utf-8").splitlines() if w.strip()]


def get_spell() -> SpellChecker:
    global _spell
    with _lock:
        if _spell is None:
            _spell = SpellChecker(language="es")
            _spell.word_frequency.load_words(_personal_words())
        return _spell


def add_to_dictionary(word: str) -> None:
    w = _TRIM.sub("", word.strip()).lower()
    if not w:
        return
    with _lock:
        if w not in _personal_words():
            DICT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(DICT_PATH, "a", encoding="utf-8") as f:
                f.write(w + "\n")
    get_spell().word_frequency.load_words([w])


EXTRA_LIST = BASE_DIR / "tools" / "palabras_es.txt"
_extra: set[str] | None = None

_VERB_ENDINGS = {
    "ar": ["a", "as", "amos", "áis", "an", "o", "é", "aste", "ó", "aron", "ando", "ado", "ada", "ados",
           "adas", "aba", "abas", "aban", "ábamos", "aré", "arás", "ará", "arán", "aría", "arías",
           "arían", "e", "es", "emos", "en", "ar"],
    "er": ["e", "es", "emos", "éis", "en", "o", "í", "iste", "ió", "ieron", "iendo", "ido", "ida",
           "idos", "idas", "ía", "ías", "ían", "eré", "erá", "erán", "ería", "a", "as", "an", "er"],
    "ir": ["e", "es", "imos", "ís", "en", "o", "í", "iste", "ió", "ieron", "iendo", "ido", "ida",
           "idos", "idas", "ía", "ías", "ían", "iré", "irá", "irán", "iría", "a", "as", "an", "ir"],
}


def _extra_words() -> set[str]:
    global _extra
    if _extra is None:
        _extra = set()
        if EXTRA_LIST.exists():
            _extra = {w.strip().lower() for w in EXTRA_LIST.read_text(encoding="utf-8").splitlines()
                      if w.strip()}
    return _extra


def _known(spell: SpellChecker, w: str) -> bool:
    """Palabra válida: diccionario base, lista ampliada o derivable por plural/género/conjugación."""
    extra = _extra_words()

    def base(x: str) -> bool:
        return (x in extra) or (not spell.unknown([x]))

    if base(w):
        return True
    forms = set()
    for suf in ("es", "s"):  # plurales
        if w.endswith(suf) and len(w) > len(suf) + 2:
            stem = w[: -len(suf)]
            forms.add(stem)
            if stem.endswith("c"):
                forms.add(stem[:-1] + "z")
    if w.endswith("ces"):
        forms.add(w[:-3] + "z")
    for suf, rep in (("a", "o"), ("as", "o"), ("os", "o"), ("as", "a"), ("ísima", "o"), ("ísimo", "o")):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            forms.add(w[: -len(suf)] + rep)
    if any(base(f) for f in forms):
        return True
    for inf, endings in _VERB_ENDINGS.items():
        for e in endings:
            if w.endswith(e) and len(w) - len(e) >= 3:
                if base(w[: -len(e)] + inf):
                    return True
    return False


def _should_skip(raw: str, w: str) -> bool:
    if any(ch.isdigit() for ch in raw):
        return True
    low = raw.lower()
    if "@" in raw or "http" in low or "www" in low or ".com" in low:
        return True
    if len(w) <= 2:
        return True
    if raw.isupper() and len(w) <= 4:  # siglas
        return True
    return False


def check_spelling(words: list[Word], known_keys: set[str] | None = None) -> tuple[list[Difference], int]:
    """Devuelve (diferencias, total de palabras revisadas). `known_keys`: palabras ya validadas
    por aparecer igual en el arte del cliente."""
    spell = get_spell()
    known_keys = known_keys or set()
    diffs: list[Difference] = []
    checked = 0
    for wd in words:
        for part in re.split(r"[-–/]", wd.text):
            raw = _TRIM.sub("", part)
            if not raw:
                continue
            w = raw.lower()
            if _should_skip(raw, w):
                continue
            checked += 1
            if w in known_keys or _known(spell, w):
                continue
            cands = spell.candidates(w) or set()
            sugg = sorted(cands - {w}, key=lambda c: -spell.word_frequency[c])[:3]
            x0, y0, x1, y1 = wd.bbox
            diffs.append(Difference(
                category="spelling", subtype="ortografia",
                bbox=(int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0))),
                severity="media",
                message=f"Posible error de ortografía: «{raw}»"
                        + (f". Sugerencias: {', '.join(sugg)}" if sugg else ""),
                found=raw, suggestions=sugg))
    return diffs, checked
