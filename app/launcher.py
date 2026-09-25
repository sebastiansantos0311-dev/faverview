"""Punto de entrada: `uv run faverview` (o `uv run faverview --acceso-directo`)."""
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .config import BASE_DIR, find_tesseract, load_config


def free_port(start=8000):
    for port in range(start, start + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


ICON = BASE_DIR / "assets" / "faverview.ico"
MARKER = BASE_DIR / "data" / ".acceso_directo_creado"


def create_shortcut(quiet: bool = False) -> bool:
    """Crea 'FAVERVIEW' (con el logo) en el Escritorio y en la carpeta de la app, apuntando a `uv run faverview`."""
    uv = shutil.which("uv")
    if not uv:
        if not quiet:
            print("No se encontró 'uv'. Instálalo con: winget install astral-sh.uv")
        return False
    ps = (
        "function Nuevo($ruta){"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($ruta);"
        "$s.TargetPath=$env:FV_UV;"
        "$s.Arguments='run faverview';"
        "$s.WorkingDirectory=$env:FV_DIR;"
        "$s.Description='FAVERVIEW - comparador de diseños';"
        "if (Test-Path $env:FV_ICON) { $s.IconLocation=$env:FV_ICON };"
        "$s.Save()};"
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$l=Join-Path $d 'FAVERVIEW.lnk';"
        "Nuevo $l;"
        "Nuevo (Join-Path $env:FV_DIR 'FAVERVIEW.lnk');"
        "Write-Output $l"
    )
    env = {"FV_UV": uv, "FV_DIR": str(BASE_DIR), "FV_ICON": str(ICON)}
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True, text=True,
                           env={**os.environ, **env}, timeout=30)
    except Exception:
        if not quiet:
            print("No se pudo crear el acceso directo en el Escritorio.")
        return False
    try:
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text("ok", encoding="utf-8")
    except OSError:
        pass
    if not quiet:
        print(f"Acceso directo creado: {r.stdout.strip()}")
    return True


def ensure_shortcut() -> None:
    """Primer arranque: crea el acceso directo del Escritorio una sola vez (si lo borras, no se vuelve a crear;
    para recrearlo usa `uv run faverview --acceso-directo`)."""
    if sys.platform != "win32":
        return
    if MARKER.exists() and (BASE_DIR / "FAVERVIEW.lnk").exists():
        return
    if create_shortcut(quiet=True):
        print("Se creó el acceso directo «FAVERVIEW» en tu Escritorio y en la carpeta de la app.")


def main() -> None:
    if "--acceso-directo" in sys.argv:
        sys.exit(0 if create_shortcut() else 1)
    ensure_shortcut()

    if not find_tesseract(load_config()):
        print("AVISO: no se encontró Tesseract; la comparación de texto no funcionará.")
        print("       Instálalo con: winget install UB-Mannheim.TesseractOCR")

    import uvicorn

    port = free_port()
    threading.Thread(target=lambda: (time.sleep(2.5), webbrowser.open(f"http://127.0.0.1:{port}")),
                     daemon=True).start()
    print(f"FAVERVIEW en http://127.0.0.1:{port}  (cierra esta ventana para salir)")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
