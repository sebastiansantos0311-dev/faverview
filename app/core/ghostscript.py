"""Ghostscript: localizarlo y ejecutarlo siempre con -dSAFER, sin shell y con tiempo límite."""
import glob
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from app.config import load_config
from app.core.errors import UserError

INSTALL_HINT = ("Ghostscript no está instalado. Instálalo siguiendo la sección «Instalar Ghostscript» del README "
                "(no está en winget; se descarga el instalador oficial firmado de Artifex).")
BASE_ARGS = ["-dSAFER", "-dBATCH", "-dNOPAUSE", "-dQUIET"]
_cache: dict = {}


def _version_key(p: str):
    m = re.search(r"gs(\d+)\.(\d+)\.?(\d*)", p.replace("\\", "/"))
    return tuple(int(x or 0) for x in m.groups()) if m else (0, 0, 0)


def find_gs() -> str | None:
    """`ghostscript_cmd` de config.json → PATH → C:\\Program Files\\gs\\gs*\\bin (la versión más alta)."""
    cfg = load_config().get("ghostscript_cmd") or ""
    if cfg and Path(cfg).exists():
        return cfg
    for name in ("gswin64c", "gswin64c.exe", "gs"):
        found = shutil.which(name)
        if found:
            return found
    cands = []
    for root in (r"C:\Program Files\gs", r"C:\Program Files (x86)\gs"):
        cands += glob.glob(root + r"\gs*\bin\gswin64c.exe") + glob.glob(root + r"\gs*\bin\gswin32c.exe")
    return sorted(cands, key=_version_key)[-1] if cands else None


def gs_version(cmd: str | None = None) -> str | None:
    cmd = cmd or find_gs()
    if not cmd:
        return None
    if cmd in _cache:
        return _cache[cmd]
    try:
        r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=15)
        _cache[cmd] = r.stdout.strip() or None
    except Exception:
        _cache[cmd] = None
    return _cache[cmd]


def available() -> bool:
    return find_gs() is not None


_ERRORS = [
    (r"Password|encrypted|/invalidfileaccess", "El PDF está protegido con contraseña o restringido."),
    (r"Error: /syntaxerror", "El archivo tiene errores de sintaxis y Ghostscript no pudo leerlo."),
    (r"Couldn't initialise file", "Ghostscript no pudo abrir el archivo (¿no es un PDF válido o está dañado?)."),
    (r"Can't find|Could not open|no such file", "Ghostscript no encontró el archivo indicado."),
    (r"memory|VMerror|limitcheck", "Ghostscript se quedó sin memoria. Baja la resolución o el tamaño de la página."),
    (r"Unrecoverable error|Error: /undefined", "Ghostscript no pudo interpretar el archivo (¿PDF dañado o no estándar?)."),
]


def translate_error(text: str) -> str:
    for pat, msg in _ERRORS:
        if re.search(pat, text or "", re.I):
            return msg
    return "Ghostscript no pudo procesar el archivo."


class Cancelled(Exception):
    """La operación fue cancelada por el usuario."""


def run_gs(args: list, timeout: float = 120, cancel: threading.Event | None = None) -> subprocess.CompletedProcess:
    """Ejecuta Ghostscript. Siempre antepone -dSAFER -dBATCH -dNOPAUSE -dQUIET; nunca usa shell.
    Si `cancel` se activa, mata el proceso. Los errores se traducen a UserError en español."""
    cmd = find_gs()
    if not cmd:
        raise UserError(INSTALL_HINT)
    proc = subprocess.Popen([cmd, *BASE_ARGS, *[str(a) for a in args]], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    t0 = time.time()
    try:
        while True:
            try:
                out, err = proc.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    proc.kill()
                    proc.communicate()
                    raise Cancelled()
                if time.time() - t0 > timeout:
                    proc.kill()
                    proc.communicate()
                    raise UserError(f"Ghostscript tardó más de {timeout:g} s y se canceló. Prueba con una resolución menor.")
    except (UserError, Cancelled):
        raise
    text = (err or "") + (out or "")
    # Ghostscript devuelve 0 aunque no pueda abrir el archivo: los fallos graves se detectan por su mensaje
    if proc.returncode != 0 or re.search(r"Couldn't initialise file|Unrecoverable error|Can't find \(or can't open\)", text):
        raise UserError(translate_error(text))
    return subprocess.CompletedProcess([cmd, *args], proc.returncode, out, err)
