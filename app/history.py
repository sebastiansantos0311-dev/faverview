"""Historial de las últimas comparaciones (data/historial.json) y limpieza al iniciar."""
import json
import shutil
import threading
import time

from .config import DATA_DIR, RESULTS_DIR, UPLOADS_DIR

HISTORY_PATH = DATA_DIR / "historial.json"
MAX_ENTRIES = 50
_lock = threading.Lock()


def list_entries() -> list[dict]:
    with _lock:
        if not HISTORY_PATH.exists():
            return []
        try:
            return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []


def add_entry(entry: dict) -> None:
    with _lock:
        items = []
        if HISTORY_PATH.exists():
            try:
                items = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            except Exception:
                items = []
        items = [e for e in items if e.get("job_id") != entry["job_id"]]
        items.insert(0, entry)
        HISTORY_PATH.write_text(json.dumps(items[:MAX_ENTRIES], ensure_ascii=False, indent=1),
                                encoding="utf-8")


def cleanup(max_age_days: int = 30) -> None:
    """Vacía data/uploads y borra resultados con más de `max_age_days` días."""
    if UPLOADS_DIR.exists():
        for p in UPLOADS_DIR.iterdir():
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    limit = time.time() - max_age_days * 86400
    if RESULTS_DIR.exists():
        for p in RESULTS_DIR.iterdir():
            try:
                if p.is_dir() and p.stat().st_mtime < limit:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
