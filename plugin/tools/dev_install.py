"""Instalación de DESARROLLO del panel en Illustrator (PLUGIN P9): copia plugin/cep a la carpeta de extensiones del usuario y activa PlayerDebugMode.

Solo para desarrollo, y lo ejecutas tú: PlayerDebugMode permite cargar extensiones sin firmar (CSXS.11 y CSXS.12). Pide confirmación antes de
tocar el registro de Windows (usa --si para no preguntar). Para instalar de verdad usa el .zxp firmado (ver plugin/README.md).

  uv run python plugin/tools/dev_install.py            # instala (copia + PlayerDebugMode)
  uv run python plugin/tools/dev_install.py --desinstalar
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CEP = ROOT / "plugin" / "cep"
BUNDLE = "com.faverview.illustrator"
KEYS = ("CSXS.11", "CSXS.12")


def ext_dir() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Adobe" / "CEP" / "extensions" / BUNDLE
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Adobe" / "CEP" / "extensions" / BUNDLE
    raise SystemExit("Illustrator solo existe en Windows y macOS.")


def set_debug_mode(on: bool):
    if sys.platform.startswith("win"):
        import winreg
        for k in KEYS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Adobe\{k}") as key:
                if on:
                    winreg.SetValueEx(key, "PlayerDebugMode", 0, winreg.REG_SZ, "1")
                else:
                    try:
                        winreg.DeleteValue(key, "PlayerDebugMode")
                    except FileNotFoundError:
                        pass
    else:
        import subprocess
        for k in ("com.adobe.CSXS.11", "com.adobe.CSXS.12"):
            subprocess.run(["defaults", "write", k, "PlayerDebugMode", "1"] if on else ["defaults", "delete", k, "PlayerDebugMode"], check=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desinstalar", action="store_true")
    ap.add_argument("--si", action="store_true", help="no pedir confirmación")
    ap.add_argument("--sin-debug", action="store_true", help="solo copiar; no tocar PlayerDebugMode")
    a = ap.parse_args(argv)
    dst = ext_dir()
    if a.desinstalar:
        if dst.exists():
            shutil.rmtree(dst)
            print(f"Borrado {dst}")
        if not a.sin_debug:
            set_debug_mode(False)
            print("PlayerDebugMode desactivado (CSXS.11 y CSXS.12).")
        return 0
    if not a.si and not a.sin_debug:
        print(f"Se copiará el panel a:\n  {dst}\ny se pondrá PlayerDebugMode=1 en HKCU\\Software\\Adobe\\CSXS.11 y CSXS.12 (solo para desarrollo).")
        if input("¿Continuar? [s/N] ").strip().lower() not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return 1
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(CEP, dst, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    if not a.sin_debug:
        set_debug_mode(True)
    print(f"Instalado en {dst}. Reinicia Illustrator: Ventana → Extensiones → FAVERVIEW.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
