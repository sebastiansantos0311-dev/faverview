"""Empaquetado del plugin (PLUGIN P9): versiones, exclusiones y consistencia."""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(tmp_path, *extra):
    return subprocess.run([sys.executable, str(ROOT / "plugin" / "tools" / "build_zxp.py"), "--sin-firma", "--out", str(tmp_path / "out"), *extra],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def test_paquete_sin_firma_excluye_debug_y_pruebas(tmp_path):
    (ROOT / "plugin" / "cep" / ".debug").write_text("<ExtensionList/>", encoding="utf-8")
    try:
        r = build(tmp_path, "--version", "9.8.7")
    finally:
        (ROOT / "plugin" / "cep" / ".debug").unlink()
    assert r.returncode == 0, r.stdout + r.stderr
    z = zipfile.ZipFile(tmp_path / "out" / "FAVERVIEW-Illustrator-9.8.7.zxp.sin_firmar.zip")
    names = z.namelist()
    assert "CSXS/manifest.xml" in names and "index.html" in names and "host/fv_host.jsx" in names and "js/ui/app.js" in names
    assert not any(n.startswith(".debug") or "/tests/" in n or n.endswith(".map") for n in names)
    man = z.read("CSXS/manifest.xml").decode("utf-8")
    assert 'ExtensionBundleVersion="9.8.7"' in man and re.search(r'<Extension Id="com\.faverview\.illustrator\.panel" Version="9\.8\.7"', man)
    assert 'var PLUGIN_VERSION = "9.8.7";' in z.read("js/ui/settings.js").decode("utf-8")
    # el fuente del repositorio no se modifico
    assert 'ExtensionBundleVersion="9.8.7"' not in (ROOT / "plugin" / "cep" / "CSXS" / "manifest.xml").read_text(encoding="utf-8")


def test_firmar_sin_datos_da_mensaje_claro(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "plugin" / "tools" / "build_zxp.py"), "--out", str(tmp_path / "o")], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={"PATH": "", "SYSTEMROOT": "C:\\Windows"})
    assert r.returncode != 0 and "ZXP_CERT_PASS" in (r.stdout + r.stderr)


def test_version_del_plugin_coincide_con_el_proyecto():
    v = re.search(r'^version = "(\d+\.\d+\.\d+)', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    man = (ROOT / "plugin" / "cep" / "CSXS" / "manifest.xml").read_text(encoding="utf-8")
    assert f'ExtensionBundleVersion="{v}"' in man
    assert f'var PLUGIN_VERSION = "{v}";' in (ROOT / "plugin" / "cep" / "js" / "ui" / "settings.js").read_text(encoding="utf-8")
    assert f'FV.VERSION = "{v}";' in (ROOT / "plugin" / "cep" / "host" / "fv_host.jsx").read_text(encoding="utf-8")


def test_certificados_fuera_de_git():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pat in ("*.p12", "*.pfx", "build/"):
        assert pat in gi
