"""Aviso de nueva versión: compara el repositorio local con origin/main (máximo 1 vez al día, sin bloquear nunca).

Solo funciona si FAVERVIEW se instaló con `git clone` y hay internet; cualquier fallo se ignora en silencio."""
import json
import os
import subprocess
import threading
import time

from .config import BASE_DIR, DATOS_DIR, load_config

STATE = DATOS_DIR / "actualizaciones.json"
_status: dict = {"disponible": False, "commits": 0, "comprobado": None, "mensaje": ""}
_lock = threading.Lock()
TIMEOUT = 3
DAY = 86400


def _git(*args, timeout=TIMEOUT):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    return subprocess.run(["git", "-c", "credential.interactive=never", "-C", str(BASE_DIR), *args], capture_output=True,
                          text=True, timeout=timeout, env=env, encoding="utf-8", errors="replace")


def _is_repo() -> bool:
    try:
        return _git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    except Exception:
        return False


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def check(force: bool = False) -> dict:
    """Consulta si hay commits nuevos en origin/main. Nunca lanza excepciones."""
    with _lock:
        if not load_config().get("update_check", True) and not force:
            return dict(_status)
        last = _load().get("ultima", 0)
        if not force and time.time() - last < DAY:
            return dict(_status, comprobado=last)
        try:
            if not _is_repo():
                return dict(_status)
            r = _git("fetch", "--quiet", "origin", "main")
            if r.returncode != 0:  # sin internet / sin permisos: se intenta otro día
                return dict(_status)
            n = int(_git("rev-list", "--count", "HEAD..origin/main").stdout.strip() or 0)
            _status.update(disponible=n > 0, commits=n, comprobado=time.time(),
                           mensaje=("Hay una versión nueva. Cierra la app y ejecuta «git pull» "
                                    "(o pulsa Actualizar).") if n > 0 else "")
            _save({"ultima": time.time(), "commits": n})
        except Exception:
            pass
        return dict(_status)


def check_background() -> None:
    """Se lanza al iniciar; no bloquea el arranque."""
    threading.Thread(target=check, daemon=True).start()


def status() -> dict:
    return dict(_status)


def apply() -> dict:
    """`git pull --ff-only`. Solo si el árbol de trabajo está limpio; después hay que reiniciar la app."""
    try:
        if _git("status", "--porcelain").stdout.strip():
            return {"ok": False, "mensaje": "Hay cambios locales sin guardar en la carpeta de la app; actualiza a mano con git pull."}
        r = _git("pull", "--ff-only", timeout=60)
        if r.returncode != 0:
            return {"ok": False, "mensaje": "No se pudo actualizar: " + (r.stderr or r.stdout).strip()[:300]}
        _status.update(disponible=False, commits=0, mensaje="")
        return {"ok": True, "mensaje": "Actualizado. Cierra la ventana negra y vuelve a abrir FAVERVIEW."}
    except Exception as e:
        return {"ok": False, "mensaje": f"No se pudo actualizar ({type(e).__name__})."}
