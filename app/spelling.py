"""Ortografía en español con pyspellchecker + diccionario personal."""
import re
import threading
from functools import lru_cache

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


# ---------------------------------------------------------------------------------- Hunspell (spylls)
HUNSPELL_DIR = BASE_DIR / "tools" / "hunspell"
_hun = None
_hun_lang = None


def _hunspell():
    """Diccionario Hunspell de LibreOffice (es_CO por defecto; configurable con "spell_lang")."""
    global _hun, _hun_lang
    from .config import load_config
    lang = load_config().get("spell_lang", "es_CO")
    if _hun is not None and _hun_lang == lang:
        return _hun
    with _lock:
        try:
            from spylls.hunspell import Dictionary
            base = HUNSPELL_DIR / lang
            if not base.with_suffix(".dic").exists():
                base = HUNSPELL_DIR / "es_ES"
            _hun = Dictionary.from_files(str(base)) if base.with_suffix(".dic").exists() else False
        except Exception:
            _hun = False
        _hun_lang = lang
        _hun_cache.cache_clear()
    return _hun


@lru_cache(maxsize=100_000)
def _hun_cache(word: str) -> bool:
    d = _hun
    if not d:
        return False
    try:
        return bool(d.lookup(word) or d.lookup(word.capitalize()))
    except Exception:
        return False


def _hun_ok(word: str) -> bool:
    _hunspell()
    return _hun_cache(word)


def _hun_suggest(word: str, n: int = 3) -> list[str]:
    d = _hunspell()
    if not d:
        return []
    try:
        return [s for s in d.suggest(word) if s.lower() != word][:n]
    except Exception:
        return []


def _learned() -> set[str]:
    try:
        from .learning import vocab
        return vocab.known_words()
    except Exception:
        return set()


_ACCENT_MAP = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}


def accent_variants(w: str) -> list[str]:
    """Palabras que resultan de ponerle UNA tilde a `w` (informacion → información)."""
    out = []
    for i, ch in enumerate(w):
        if ch in _ACCENT_MAP:
            out.append(w[:i] + _ACCENT_MAP[ch] + w[i + 1:])
    return out


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


def _strip_acc(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").replace("n\u0303", "ñ")


def _stem_ok(base, stem: str) -> bool:
    """¿`stem` es una forma verbal válida (imperativo, infinitivo, gerundio)?"""
    if base(stem):
        return True
    for inf, endings in _VERB_ENDINGS.items():
        for e in endings:
            if stem.endswith(e) and len(stem) - len(e) >= 3 and base(stem[: -len(e)] + inf):
                return True
    return base(stem + "r")


def _known(spell: SpellChecker, w: str) -> bool:
    """Palabra válida: diccionario base, lista ampliada o derivable por plural/género/conjugación."""
    extra = _extra_words()

    learned = _learned()

    def base(x: str) -> bool:
        return (x in extra) or (x in learned) or _hun_ok(x) or (not spell.unknown([x]))

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
    # verbo + pronombre enclítico: «visítanos», «comunícate», «dímelo»
    for cl in ("selos", "selas", "selo", "sela", "nos", "les", "los", "las", "me", "te", "se", "le", "lo", "la", "os"):
        if w.endswith(cl) and len(w) - len(cl) >= 3:
            stem = _strip_acc(w[: -len(cl)])
            if _stem_ok(base, stem):
                return True
    for inf, endings in _VERB_ENDINGS.items():
        for e in endings:
            if w.endswith(e) and len(w) - len(e) >= 3:
                if base(w[: -len(e)] + inf):
                    return True
    return False


def is_known_word(word: str) -> bool:
    w = _TRIM.sub("", word.strip()).lower()
    if not w or _should_skip(_TRIM.sub("", word.strip()), w):
        return True  # números, siglas, correos: no se juzgan
    return _known(get_spell(), w)


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
            x0, y0, x1, y1 = wd.bbox
            bbox = (int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0)))
            # ¿existe la palabra con una tilde? (informacion → información): error de tilde, sugerencia única
            tv = [v for v in accent_variants(w) if _known(spell, v)]
            if len(tv) == 1:
                fix = tv[0].capitalize() if raw[:1].isupper() else tv[0]
                diffs.append(Difference(
                    category="spelling", subtype="tilde_faltante", bbox=bbox, severity="alta",
                    message=f"Falta la tilde: «{raw}» → «{fix}»", found=raw, suggestions=[fix]))
                continue
            sugg = _hun_suggest(raw)
            if not sugg:
                cands = spell.candidates(w) or set()
                sugg = sorted(cands - {w}, key=lambda c: -spell.word_frequency[c])[:3]
            diffs.append(Difference(
                category="spelling", subtype="ortografia", bbox=bbox, severity="media",
                message=f"Posible error de ortografía: «{raw}»"
                        + (f". Sugerencias: {', '.join(sugg)}" if sugg else ""),
                found=raw, suggestions=sugg))
    return diffs, checked
