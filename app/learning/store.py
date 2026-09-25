"""Almacén del aprendizaje: todo vive en datos_locales/aprendizaje/ (NUNCA se sube a git)."""
import hashlib
import json
import os
import threading
from pathlib import Path

from ..config import DATOS_DIR

_LOCK = threading.RLock()


def root() -> Path:
    d = DATOS_DIR / "aprendizaje"
    d.mkdir(parents=True, exist_ok=True)
    return d


def path(name: str) -> Path:
    return root() / name


def load_json(name: str, default):
    p = path(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(name: str, data) -> None:
    with _LOCK:
        p = path(name)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)


def enabled() -> bool:
    from ..config import load_config
    return bool(load_config().get("learning_enabled", True))


def state() -> dict:
    st = load_json("estado.json", {})
    st.setdefault("casos_revisados", 0)
    st.setdefault("ultimo_autoajuste_en", 0)
    st.setdefault("lineas_guardadas", 0)
    return st


def fingerprint() -> str | None:
    """Huella corta del aprendizaje en uso (vocabulario + confusiones + ajustes + modelo)."""
    if not enabled():
        return None
    h = hashlib.sha1()
    found = False
    for name in ("vocabulario.txt", "patrones.txt", "confusiones.json", "ajustes_ocr.json"):
        p = path(name)
        if p.exists():
            h.update(p.read_bytes())
            found = True
    model = path("modelos") / "activo.txt"
    if model.exists():
        h.update(b"modelo")
        found = True
    return h.hexdigest()[:8] if found else None


def record_review(result, body: dict, case_dir: Path, design_path, client_path) -> dict:
    """Se llama al guardar un caso revisado: alimenta los 4 niveles de aprendizaje.
    Devuelve {"autoajuste": True} si arrancó el auto-ajuste del OCR en segundo plano."""
    if not enabled():
        return {"autoajuste": False}
    from . import confusions, finetune, tuning, vocab
    from ..config import RESULTS_DIR

    with _LOCK:
        st = state()
        st["casos_revisados"] += 1
        try:
            vocab.add_from_review(result, design_path)
        except Exception:
            pass
        try:
            confusions.add_from_review(result)
        except Exception:
            pass
        try:
            n = finetune.save_lines(result, body, RESULTS_DIR / result.job_id, design_path, case_dir.name)
            st["lineas_guardadas"] += n
        except Exception:
            pass
        save_json("estado.json", st)

    from ..config import load_config
    every = int(load_config().get("learning_autotune_every", 5))
    if every > 0 and st["casos_revisados"] - st["ultimo_autoajuste_en"] >= every and not tuning.is_running():
        tuning.autotune_background()
        return {"autoajuste": True}
    return {"autoajuste": False}
