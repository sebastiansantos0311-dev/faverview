"""Guardas de seguridad estáticas: fallan si un cambio futuro reintroduce un riesgo conocido.

Repositorio público: nada que permita conectarse desde otro dispositivo, ejecutar código o filtrar secretos."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tracked() -> list[str]:
    return subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()


def _py(folder: str):
    return [p for p in (ROOT / folder).rglob("*.py") if "__pycache__" not in p.parts]


def test_servidor_solo_escucha_en_local():
    src = (ROOT / "app" / "launcher.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in src
    for p in _py("app"):
        assert "0.0.0.0" not in p.read_text(encoding="utf-8"), f"{p}: nunca escuchar en todas las interfaces"


def test_sin_funciones_peligrosas_en_el_servidor():
    bad = re.compile(r"shell\s*=\s*True|os\.system\(|os\.popen\(|\beval\(|\bexec\(|pickle\.loads?\(|yaml\.load\(|marshal\.loads\(")
    hits = [f"{p.relative_to(ROOT)}:{i}" for p in _py("app")
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if bad.search(line)]
    assert not hits, hits


def test_xml_sin_entidades_externas():
    src = (ROOT / "app" / "core" / "inks.py").read_text(encoding="utf-8")
    assert "resolve_entities=False" in src and "no_network=True" in src


def test_ghostscript_siempre_con_safer():
    assert "-dSAFER" in (ROOT / "app" / "core" / "ghostscript.py").read_text(encoding="utf-8")


def test_no_se_versionan_secretos_ni_datos_locales():
    patterns = re.compile(r"(^|/)(data|datos_locales|build|\.venv)/|\.(p12|pfx|pem|key|zxp|token)$|(^|/)(plugin\.json|\.env[^/]*|\.coverage)$")
    allowed = {"data/.gitkeep"}
    bad = [f for f in _tracked() if patterns.search(f) and f not in allowed]
    assert not bad, bad


def test_sin_tokens_ni_claves_en_archivos_versionados():
    secret = re.compile(r"(ghp_|gho_|github_pat_)[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]{32,}")
    hits = []
    for f in _tracked():
        p = ROOT / f
        if p.suffix.lower() in {".py", ".js", ".jsx", ".md", ".json", ".yml", ".yaml", ".toml", ".txt", ".html", ".css", ".xml"} and p.is_file():
            if secret.search(p.read_text(encoding="utf-8", errors="ignore")):
                hits.append(f)
    assert not hits, hits


def test_avisos_del_servidor_se_escapan_en_la_interfaz():
    """Los avisos y nombres que vienen del servidor (pueden incluir nombres de tintas de archivos ajenos) no se insertan como HTML crudo."""
    hits = []
    for folder in ("web", "plugin/cep/js"):
        for p in (ROOT / folder).rglob("*.js"):
            if "lib" in p.parts:
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                for stmt in line.split(";"):              # textContent en la misma línea es seguro: se mira cada instrucción
                    if "innerHTML" in stmt and re.search(r"avisos\.join\(", stmt):
                        hits.append(f"{p.relative_to(ROOT)}:{i}")
    assert not hits, "usar avisos.map(esc).join(...): " + ", ".join(hits)


def test_panel_de_illustrator_sin_node_y_con_lista_blanca():
    manifest = (ROOT / "plugin" / "cep" / "CSXS" / "manifest.xml").read_text(encoding="utf-8")
    assert "--enable-nodejs" not in manifest and "--mixed-context" not in manifest
    host = (ROOT / "plugin" / "cep" / "host" / "fv_host.jsx").read_text(encoding="utf-8")
    assert "FV.ALLOWED" in host and not re.search(r"\beval\(|app\.system\(|system\.callSystem", host)


def test_workflow_con_permisos_de_solo_lectura():
    wf = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert re.search(r"^permissions:\s*\n\s+contents:\s*read", wf, re.M)
    assert "pull_request_target" not in wf
