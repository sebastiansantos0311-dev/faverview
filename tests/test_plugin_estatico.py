"""Pruebas estáticas del panel del plugin (PLUGIN §13): sin Node, sin eval, APIs de CEP solo en el HostAdapter, textos por i18n."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugin" / "cep"
JS = sorted((PLUGIN / "js").rglob("*.js"))
PANEL_JS = [f for f in JS if f.name != "CSInterface.js"]


def text(f):
    return f.read_text(encoding="utf-8")


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(^|[^:\"'])//[^\n]*", r"\1", src)


def test_sin_node_ni_eval():
    for f in JS:
        src = strip_comments(text(f))
        assert "require(" not in src, f.name
        assert not re.search(r"\beval\s*\(", src), f.name
        assert "new Function(" not in src, f.name
        assert "process.env" not in src and "child_process" not in src, f.name


def test_apis_de_cep_solo_en_host_y_files():
    """Para migrar a UXP solo deben cambiar host.js y files.js (y CSInterface.js)."""
    permitidos = {"host.js": ("CSInterface", "__adobe_cep__"), "files.js": ("cep.fs", "cep.encoding", "window.cep", "g.cep"), "CSInterface.js": ("__adobe_cep__", "CSInterface", "cep.util", "window.cep")}
    for f in JS:
        src = strip_comments(text(f))
        for token in ("__adobe_cep__", "CSInterface", "cep.fs", "cep.encoding", "cep.util", "g.cep", "window.cep"):
            if token in src:
                assert token in permitidos.get(f.name, ()), f"{f.name} usa {token} fuera del HostAdapter"


def test_ni_node_en_manifest():
    xml = (PLUGIN / "CSXS" / "manifest.xml").read_text(encoding="utf-8")
    assert "--enable-nodejs" not in xml and "--mixed-context" not in xml
    root = ET.fromstring(xml)                                              # XML bien formado
    assert root.get("ExtensionBundleId") == "com.faverview.illustrator"
    host = root.find(".//Host")
    assert host.get("Name") == "ILST" and host.get("Version") == "[28.0,99.9]"
    assert root.find(".//RequiredRuntime").get("Name") == "CSXS"
    for icon in root.iter("Icon"):
        assert (PLUGIN / icon.text).exists(), icon.text
    assert (PLUGIN / root.find(".//MainPath").text).exists() and (PLUGIN / root.find(".//ScriptPath").text).exists()


def test_scripts_del_index_existen_y_en_orden():
    html = text(PLUGIN / "index.html")
    srcs = re.findall(r'<script src="([^"]+)"', html)
    assert all((PLUGIN / s).exists() for s in srcs)
    assert srcs.index("js/core/i18n.js") < srcs.index("js/ui/common.js") < srcs.index("js/ui/app.js")
    assert set(s for s in srcs) >= {f.relative_to(PLUGIN).as_posix() for f in JS}


def i18n_keys():
    src = text(PLUGIN / "js" / "core" / "i18n.js")
    return set(re.findall(r'"([a-z]+\.[\w.]+)":', src))


def test_todas_las_claves_de_texto_existen():
    keys = i18n_keys()
    usadas = set()
    for f in PANEL_JS:
        usadas |= set(re.findall(r'\bt\("([a-z]+\.[\w.]+)"', text(f)))
        usadas |= set(re.findall(r'FVP\.t\("([a-z]+\.[\w.]+)"', text(f)))
        usadas |= set(re.findall(r'texto: "([a-z]+\.[\w.]+)"', text(f)))
    assert usadas, "no se encontraron usos de t()"
    faltan = sorted(k for k in usadas if k not in keys and not k.startswith("tab."))
    assert not faltan, faltan
    assert {"tab.vectorizar", "tab.trap", "tab.ajustes"} <= keys


LITERAL_PERMITIDO = re.compile(r"^(Paracetamol 500 mg|Estimaci.n orientativa|EAN|UPC|ITF|GS1|Code |Data ?Matrix|QR|Logo|L.nea|Ilustraci.n|Escaneo|Foto posterizada|Ver$|Mesa)")


def test_textos_visibles_pasan_por_i18n():
    """Ninguna cadena visible en español dentro de las pestañas (los nombres de tipos de código son datos)."""
    malos = []
    for f in (PLUGIN / "js" / "ui").glob("*.js"):
        src = strip_comments(text(f))
        for m in re.finditer(r'(?:textContent\s*=|createTextNode\()\s*"([^"]{4,})"', src):
            malos.append((f.name, m.group(1)))
        for m in re.finditer(r'\bel\("(?:button|span|div|h2|h3|b|option|label|p|a)"[^;]*?,\s*"([A-ZÁÉÍÓÚ¿][^"]{3,})"\s*[,)]', src):
            if not LITERAL_PERMITIDO.match(m.group(1)):
                malos.append((f.name, m.group(1)))
    assert not malos, malos
