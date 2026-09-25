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


def create_shortcut() -> None:
    """Crea 'FAVERVIEW' en el Escritorio apuntando a `uv run faverview` en esta carpeta."""
    uv = shutil.which("uv")
    if not uv:
        print("No se encontró 'uv'. Instálalo con: winget install astral-sh.uv")
        sys.exit(1)
    desktop = Path.home() / "Desktop"
    onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
    if not desktop.exists() and onedrive_desktop.exists():
        desktop = onedrive_desktop
    lnk = desktop / "FAVERVIEW.lnk"
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:FV_LNK);"
        "$s.TargetPath=$env:FV_UV;"
        "$s.Arguments='run faverview';"
        "$s.WorkingDirectory=$env:FV_DIR;"
        "$s.Description='FAVERVIEW - comparador de diseños';"
        "$s.Save()"
    )
    env = {"FV_LNK": str(lnk), "FV_UV": uv, "FV_DIR": str(BASE_DIR)}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                   env={**os.environ, **env})
    print(f"Acceso directo creado: {lnk}")


def main() -> None:
    if "--acceso-directo" in sys.argv:
        create_shortcut()
        return

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
