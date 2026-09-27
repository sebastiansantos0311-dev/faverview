"""Empaqueta y firma el plugin de Illustrator (PLUGIN P9).

Uso:
  uv run python plugin/tools/build_zxp.py --sin-firma                       # solo empaqueta (CI y pruebas)
  uv run python plugin/tools/build_zxp.py --cert cert.p12 --zxpsigncmd C:\\ruta\\ZXPSignCmd.exe [--tsa https://timestamp.example]
  uv run python plugin/tools/build_zxp.py --crear-certificado cert.p12 --zxpsigncmd ... --pais CO --provincia Antioquia --organizacion "Mi taller" --nombre "FAVERVIEW"

La clave del certificado se lee de la variable de entorno ZXP_CERT_PASS (nunca se pasa por línea de comandos ni se guarda).
El certificado (.p12) y su clave NO deben subirse a git. ZXPSignCmd es una herramienta oficial de Adobe (Adobe-CEP/CEP-Resources):
descárgala tú; no se incluye en el repositorio."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CEP = ROOT / "plugin" / "cep"
EXCLUDE_DIRS = {"tests", "__pycache__", "node_modules"}
EXCLUDE_NAMES = {".debug", ".DS_Store", "Thumbs.db"}
EXCLUDE_SUFFIX = {".map", ".log"}


def project_version() -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit("No se encontró la versión en pyproject.toml.")
    v = re.match(r"^\d+(?:\.\d+){1,2}", m.group(1))
    return v.group(0) if v else m.group(1)


def copy_tree(dst: Path, version: str) -> Path:
    """Copia plugin/cep a `dst` sin .debug, pruebas ni mapas, y escribe la versión en el manifest y en el panel."""
    if dst.exists():
        shutil.rmtree(dst)
    for src in CEP.rglob("*"):
        rel = src.relative_to(CEP)
        if any(p in EXCLUDE_DIRS for p in rel.parts) or src.name in EXCLUDE_NAMES or src.suffix in EXCLUDE_SUFFIX:
            continue
        if src.is_dir():
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
    man = dst / "CSXS" / "manifest.xml"
    t = man.read_text(encoding="utf-8")
    t = re.sub(r'ExtensionBundleVersion="[^"]*"', f'ExtensionBundleVersion="{version}"', t)
    t = re.sub(r'(<Extension Id="com\.faverview\.illustrator\.panel" Version=")[^"]*(")', rf"\g<1>{version}\g<2>", t)
    man.write_text(t, encoding="utf-8")
    st = dst / "js" / "ui" / "settings.js"
    s = st.read_text(encoding="utf-8")
    st.write_text(re.sub(r'var PLUGIN_VERSION = "[^"]*";', f'var PLUGIN_VERSION = "{version}";', s), encoding="utf-8")
    return dst


def zip_unsigned(folder: Path, out: Path) -> Path:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        # el manifest y el mimetype primero, como esperan los instaladores de extensiones
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(folder).as_posix())
    return out


def run(cmd, secret: str | None = None):
    shown = " ".join(str(c) if c != secret else "******" for c in cmd)
    print("> " + shown)
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout + r.stderr).strip())
    if r.returncode != 0:
        raise SystemExit(f"Falló: {shown.split()[0]} (código {r.returncode}).")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="versión del plugin (por defecto la de pyproject.toml)")
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "zxp", help="carpeta de salida")
    ap.add_argument("--sin-firma", action="store_true", help="empaqueta sin firmar (para CI y pruebas; NO sirve para instalar con UPIA)")
    ap.add_argument("--cert", type=Path, help="certificado .p12")
    ap.add_argument("--zxpsigncmd", help="ruta de ZXPSignCmd")
    ap.add_argument("--tsa", default="https://timestamp.digicert.com", help="servidor de sello de tiempo (TSA)")
    ap.add_argument("--crear-certificado", type=Path, metavar="CERT.p12", help="crea un certificado propio y termina")
    ap.add_argument("--pais", default="CO"); ap.add_argument("--provincia", default="Antioquia")
    ap.add_argument("--organizacion", default="FAVERVIEW"); ap.add_argument("--nombre", default="FAVERVIEW")
    a = ap.parse_args(argv)
    signcmd = a.zxpsigncmd or os.environ.get("ZXPSIGNCMD") or shutil.which("ZXPSignCmd")
    password = os.environ.get("ZXP_CERT_PASS")

    if a.crear_certificado:
        if not signcmd or not password:
            raise SystemExit("Hace falta --zxpsigncmd (o ZXPSIGNCMD) y la variable de entorno ZXP_CERT_PASS.")
        run([signcmd, "-selfSignedCert", a.pais, a.provincia, a.organizacion, a.nombre, password, a.crear_certificado], password)
        print(f"Certificado creado: {a.crear_certificado}. Guárdalo FUERA del repositorio.")
        return 0

    version = a.version or project_version()
    folder = copy_tree(a.out.parent / "zxp_contenido", version)
    a.out.mkdir(parents=True, exist_ok=True)
    name = f"FAVERVIEW-Illustrator-{version}.zxp"
    target = a.out / name
    if a.sin_firma:
        zip_unsigned(folder, a.out / (name + ".sin_firmar.zip"))
        print(f"Empaquetado SIN firmar: {a.out / (name + '.sin_firmar.zip')}")
        return 0
    if not (signcmd and a.cert and password):
        raise SystemExit("Para firmar hace falta --zxpsigncmd, --cert y la variable de entorno ZXP_CERT_PASS (o usa --sin-firma).")
    if target.exists():
        target.unlink()
    run([signcmd, "-sign", folder, target, a.cert, password, "-tsa", a.tsa], password)
    run([signcmd, "-verify", target, "-certinfo"])
    print(f"Listo: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
