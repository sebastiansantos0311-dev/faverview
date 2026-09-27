"""Pruebas del plugin con Node: capa host con mock de Illustrator, núcleo del panel contra un servidor FAVERVIEW real, JSON de ExtendScript y
paridad de normalize_name con Python. Se omiten si no hay Node."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js no está instalado")


def run_node(*args, env=None, timeout=300):
    e = {**os.environ, **(env or {})}
    return subprocess.run([NODE, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=e, encoding="utf-8", errors="replace")


def test_host_con_mock_de_illustrator():
    r = run_node("--test", "plugin/tests/host_mock/host.test.js")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]


def test_json_de_extendscript_sin_json_nativo():
    code = r"""
const vm = require('vm'), fs = require('fs');
const ctx = vm.createContext({ SyntaxError, eval: undefined });
vm.runInContext('var JSON;', ctx);                                   // sin JSON nativo, como ExtendScript
ctx.eval = (s) => vm.runInContext(s, ctx);
vm.runInContext(fs.readFileSync('plugin/cep/host/json2.js','utf8'), ctx);
const out = vm.runInContext(`
  var o = {a: 1, b: [true, null, "x\\ny \\"q\\" ñ – \\u0001"], c: {d: 1.5}};
  var s = JSON.stringify(o); var back = JSON.parse(s);
  var bad = 0; try { JSON.parse('{"a": alert(1)}'); } catch (e) { bad = 1; }
  JSON.stringify({s: s, ok: back.b[2] === o.b[2] && back.c.d === 1.5, bad: bad});`, ctx);
console.log(out);
"""
    r = run_node("-e", code)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout.strip().splitlines()[-1])
    assert d["ok"] is True and d["bad"] == 1


def test_paridad_normalize_name_con_python():
    from app.core.inks import normalize_name
    nombres = ["Pantone 485C", "PANTONE 485 C", "pms 485 u", "  Demo   Rojo 1 ", "P 2985CP", "Pantone® 300 U", "Azul marino", "PMS-186 M", "Cyan", "HKS 43 K", "485", "Pantone 7621UP"]
    code = f"""
const {{ makeEnv }} = require('./plugin/tests/host_mock/mock_ai');
const e = makeEnv();
console.log(JSON.stringify({json.dumps(nombres, ensure_ascii=False)}.map(n => e.run('FV.normName(' + JSON.stringify(n) + ')'))));
"""
    r = run_node("-e", code)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1]) == [normalize_name(n) for n in nombres]


def test_host_solo_ascii():
    """ExtendScript lee los .jsx con la codificación del sistema: los acentos van como \\uXXXX."""
    for f in list((ROOT / "plugin" / "cep" / "host").glob("*.jsx")) + [ROOT / "plugin" / "cep" / "host" / "json2.js"]:
        raw = f.read_bytes()
        assert all(b < 128 for b in raw), f.name


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_nucleo_del_panel_contra_servidor_real(tmp_path):
    port = _free_port()
    pj = tmp_path / "plugin.json"
    env = {**os.environ, "FAVERVIEW_PLUGIN_JSON": str(pj), "FAVERVIEW_PORT": str(port), "FAVERVIEW_DATOS": str(tmp_path / "datos")}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=1)
                if pj.exists():
                    break
            except Exception:
                time.sleep(0.25)
        assert pj.exists(), "el servidor no escribió plugin.json"
        assert json.loads(pj.read_text(encoding="utf-8"))["puerto"] == port
        r = run_node("--test", "plugin/tests/panel/core.test.js", env={"FV_PLUGIN_JSON": str(pj)})
        assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-1500:]
        assert "skipped 0" in r.stdout or "ℹ skipped 0" in r.stdout
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
