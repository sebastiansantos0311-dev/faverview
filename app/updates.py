"""Aviso de nueva versión: compara el repositorio local con origin/main (máximo 1 vez al día, sin bloquear nunca).

Solo funciona si FAVERVIEW se instaló con `git clone` y hay internet; cualquier fallo se ignora en silencio."""
import json
import os
import subprocess
import threading
import time

from .config import BASE_DIR, DATOS_DIR, load_config

STATE = DATOS_DIR / "actualizaciones.json"
_status: dict = {"disponible": False, "commits": 0, "comprobado": None, "mensaje": "", "plugin_version": None, "plugin_url": None,
                 "version_nueva": None, "novedades": [], "rama": None}
RELEASES_URL = "https://api.github.com/repos/sebastiansantos0311-dev/faverview/releases"
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


def plugin_release() -> tuple[str | None, str | None]:
    """Versión y enlace del último plugin de Illustrator publicado (archivo FAVERVIEW-Illustrator-<versión>.zxp en un Release)."""
    import re
    import urllib.request
    try:
        req = urllib.request.Request(RELEASES_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "FAVERVIEW"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            releases = json.loads(r.read().decode("utf-8"))
        best = None
        for rel in releases:
            for a in rel.get("assets", []):
                m = re.match(r"^FAVERVIEW-Illustrator-(\d+(?:\.\d+)*)\.zxp$", a.get("name", ""))
                if m:
                    v = tuple(int(x) for x in m.group(1).split("."))
                    if best is None or v > best[0]:
                        best = (v, m.group(1), rel.get("html_url") or a.get("browser_download_url"))
        return (best[1], best[2]) if best else (None, None)
    except Exception:
        return None, None


def _remote_version() -> str | None:
    """Versión de `pyproject.toml` en origin/main (sin red: usa la última descarga de `git fetch`)."""
    import re
    m = re.search(r'^version\s*=\s*"([^"]+)"', _git("show", "origin/main:pyproject.toml").stdout, re.M)
    return m.group(1) if m else None


def _remote_news(max_items: int = 8) -> list[str]:
    """Viñetas de la primera sección de CHANGELOG.md en origin/main (las novedades de la versión nueva)."""
    import re
    items, inside = [], False
    for line in _git("show", "origin/main:CHANGELOG.md").stdout.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = True
        elif inside and line.startswith("- "):
            text = re.sub(r"[*`]", "", line[2:]).strip()
            items.append(text if len(text) <= 160 else text[:157] + "…")
        elif inside and items and line.startswith("  ") and not line.strip().startswith("- "):
            continue                                     # continuación de una viñeta larga: ya se resumió
    return items[:max_items]


def _refresh_from_local_refs() -> None:
    """Calcula el estado con las referencias ya descargadas (sirve tras reiniciar sin volver a consultar internet)."""
    n = int(_git("rev-list", "--count", "HEAD..origin/main").stdout.strip() or 0)
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    new_v = _remote_version() if n > 0 else None
    if n > 0:
        msg = (f"Hay una versión nueva{' (' + new_v + ')' if new_v else ''}. Pulsa Actualizar "
               "(o cierra la app y ejecuta «git pull»).")
    else:
        msg = ""
    if branch not in ("main", "HEAD") and n > 0:
        msg += f" Nota: la carpeta está en la rama «{branch}», no en «main»; actualiza a mano."
    _status.update(disponible=n > 0, commits=n, version_nueva=new_v, rama=branch, mensaje=msg,
                   novedades=_remote_news() if n > 0 else [])


def check(force: bool = False) -> dict:
    """Consulta si hay commits nuevos en origin/main. Nunca lanza excepciones.

    Consulta internet como máximo 1 vez al día (salvo `force`); entre medias recalcula el aviso con las referencias ya
    descargadas, así el aviso no se pierde al reiniciar la app."""
    with _lock:
        if not load_config().get("update_check", True) and not force:
            return dict(_status)
        last = _load().get("ultima", 0)
        try:
            if not _is_repo():
                return dict(_status)
            if not force and time.time() - last < DAY:
                _refresh_from_local_refs()
                return dict(_status, comprobado=last)
            r = _git("fetch", "--quiet", "origin", "main", timeout=15 if force else TIMEOUT)
            if r.returncode != 0:  # sin internet / sin permisos: se intenta otro día
                if force:
                    _status.update(error="No se pudo consultar GitHub (¿sin internet?).")
                return dict(_status)
            _status.pop("error", None)
            _refresh_from_local_refs()
            _status.update(comprobado=time.time())
            v, url = plugin_release()
            _status.update(plugin_version=v, plugin_url=url)
            _save({"ultima": time.time(), "commits": _status["commits"]})
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
        branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch != "main":
            return {"ok": False, "mensaje": f"La carpeta de la app está en la rama «{branch}»; cambia a «main» (git switch main) "
                                            "y vuelve a intentarlo."}
        if _git("status", "--porcelain").stdout.strip():
            return {"ok": False, "mensaje": "Hay cambios locales sin guardar en la carpeta de la app; actualiza a mano con git pull."}
        r = _git("pull", "--ff-only", timeout=60)
        if r.returncode != 0:
            return {"ok": False, "mensaje": "No se pudo actualizar: " + (r.stderr or r.stdout).strip()[:300]}
        _status.update(disponible=False, commits=0, mensaje="", novedades=[], version_nueva=None)
        return {"ok": True, "mensaje": "Actualizado. Cierra la ventana negra y vuelve a abrir FAVERVIEW "
                                       "(la primera vez puede tardar un poco más si hay librerías nuevas)."}
    except Exception as e:
        return {"ok": False, "mensaje": f"No se pudo actualizar ({type(e).__name__})."}
