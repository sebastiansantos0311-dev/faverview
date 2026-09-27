"""El panel completo cargado desde file:// en Edge (origen «null», como CEP) con CEP e Illustrator simulados y un servidor FAVERVIEW real.

Ejecuta de verdad las pestañas (JS, CORS con token, subida, trabajos, descargas) y comprueba las llamadas al host de Illustrator."""
import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
pytestmark = pytest.mark.skipif(not Path(EDGE).exists(), reason="Edge no está instalado")

FAKE = r"""
(function () {
  const FILES = %FILES%, PLUGIN = %PLUGIN%, TEMP = "C:/fake/tmp";
  const log = window.__hostLog = [];
  const written = window.__written = {};
  function resp(o) { return JSON.stringify({ ok: true, data: o }); }
  const H = {
    ping: () => ({ illustrator: "29.0", doc: true, tempPath: TEMP, mesas: 1, mesaActiva: 0, nombreDoc: "prueba.ai" }),
    docInfo: () => ({ nombre: "prueba.ai", mesas: [{ index: 0, name: "M1", rect: [0, 283.5, 283.5, 0], size: [283.5, 283.5] }], rulerOrigin: [0, 0], muestras: ["Demo Rojo", "Sin uso"] }),
    listSpots: () => ["Demo Rojo", "Sin uso"],
    exportArtboardPDF: (a) => ({ ruta: "C:/fake/" + (window.__mesa || "mesa.pdf"), tamano_pt: [283.5, 283.5], artboardRect: [0, 283.5, 283.5, 0], rulerOrigin: [0, 0], mesa: 0, nombreMesa: "M1" }),
    exportSelectionPNG: () => ({ tipo: "vinculada", ruta: "C:/fake/logo.png", bounds: [50, 200, 250, 100], matriz: null, rotacion: 0 }),
    zoomTo: () => ({ zoom: 2 }), selectInBBox: () => ({ seleccionados: 1, truncado: false, aviso: null }), markers: (a) => ({ creados: a.lista.length }),
    clearMarkers: () => ({ borrada: true }), placeOverSelection: () => ({ nombre: "x" }), placePDF: () => ({ nombre: "x" }), insertPDF: () => ({ nombre: "x" }),
    fixOverprint: (a) => ({ objetos: 3, aplicado: !a.soloContar }), fixBlackText: (a) => ({ objetos: 2, aplicado: !a.soloContar }),
    mergeSpots: (a) => ({ objetos: 1, aplicado: !a.soloContar }), removeUnusedSpots: (a) => ({ muestras: ["Sin uso"], aplicado: !a.soloContar })
  };
  window.__adobe_cep__ = {
    evalScript(script, cb) {
      const m = /^FV\.dispatch\((".*?"),(".*")\)$/s.exec(script);
      const name = JSON.parse(m[1]), args = JSON.parse(JSON.parse(m[2]));
      log.push({ name, args });
      setTimeout(() => cb(H[name] ? resp(H[name](args)) : JSON.stringify({ ok: false, error: "no simulado: " + name })), 0);
    },
    getHostEnvironment() { return JSON.stringify({ appSkinInfo: { panelBackgroundColor: { color: { red: 50, green: 50, blue: 50 } } } }); },
    getSystemPath() { return "C:/fakeuser"; }, addEventListener() {}, removeEventListener() {}, getExtensionId() { return "x"; }, closeExtension() {}
  };
  window.cep = {
    encoding: { Base64: "Base64", UTF8: "UTF-8" },
    util: { openURLInDefaultBrowser(u) { log.push({ name: "openURL", args: u }); } },
    fs: {
      readFile(p, e) {
        if (p.endsWith("FAVERVIEW/plugin.json")) return { err: 0, data: PLUGIN };
        const f = FILES[p.split("/").pop()];
        if (f) return { err: 0, data: f };
        if (written[p]) return { err: 0, data: written[p] };
        return { err: 2 };
      },
      writeFile(p, d) { written[p] = d; return { err: 0 }; },
      stat(p) { const f = FILES[p.split("/").pop()] || written[p]; return f ? { err: 0, data: { size: f.length * 0.75, mtime: new Date() } } : { err: 2 }; },
      readdir() { return { err: 0, data: [] }; }, deleteFile() { return { err: 0 }; },
      showOpenDialogEx() { return { err: 0, data: ["C:/fake/arte.png"] }; }, showSaveDialogEx() { return { err: 0, data: "C:/fake/placas.zip" }; }
    }
  };
})();
"""


class Page:
    def __init__(self, port):
        self.prof = tempfile.mkdtemp(prefix="fv_edge_")
        self.proc = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={port}", "--window-size=400,900", f"--user-data-dir={self.prof}", "about:blank"])
        for _ in range(40):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1))
                self.url = [t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.25)
        self.n = 0
        self.errors = []

    async def __aenter__(self):
        import websockets
        self.ws = await websockets.connect(self.url, max_size=80_000_000)
        self._pending = {}
        self._reader = asyncio.create_task(self._read())
        await self.call("Page.enable")
        await self.call("Runtime.enable")
        return self

    async def __aexit__(self, *a):
        self._reader.cancel()
        await self.ws.close()
        self.proc.terminate()

    async def _read(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if "id" in m and m["id"] in self._pending:
                self._pending.pop(m["id"]).set_result(m.get("result", {}))
            elif m.get("method") == "Runtime.exceptionThrown":
                d = m["params"]["exceptionDetails"]
                self.errors.append((d.get("exception", {}) or {}).get("description") or d.get("text", ""))

    async def call(self, method, **params):
        self.n += 1
        fut = asyncio.get_event_loop().create_future()
        self._pending[self.n] = fut
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        return await fut

    async def js(self, code):
        r = await self.call("Runtime.evaluate", expression=code, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            return "EXC: " + str(r["exceptionDetails"])
        return r.get("result", {}).get("value")

    async def until(self, cond, timeout=40):
        end = time.time() + timeout
        while time.time() < end:
            v = await self.js(cond)
            if v and not (isinstance(v, str) and v.startswith("EXC")):
                return v
            await asyncio.sleep(0.3)
        raise AssertionError("no se cumplió: " + cond + " → " + str(await self.js(cond)))


def b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def touching_pdf(path):
    from bench.synth_separations import Builder
    b = Builder(283.5, 283.5)
    b.separation("CS0", "Amarillo Demo", (0, 0, 1, 0))
    b.separation("CS1", "Azul Demo", (1, 0.5, 0, 0))
    b.rect(20, 20, 100, 100, "/CS0 cs 1 scn")
    b.rect(120, 20, 100, 100, "/CS1 cs 1 scn")
    return b.build(path)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_panel_completo_en_edge(tmp_path):
    port = free_port()
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
        assert pj.exists()
        # archivos simulados
        doc = pymupdf.open()
        pg = doc.new_page(width=283.5, height=283.5)
        pg.add_text_annot((50, 50), "nota")
        doc.save(str(tmp_path / "mesa.pdf"))
        touching_pdf(tmp_path / "touch.pdf")
        img = np.full((200, 300, 3), 255, np.uint8)
        cv2.circle(img, (100, 100), 60, (30, 30, 220), -1)
        cv2.rectangle(img, (170, 60), (270, 150), (30, 150, 60), -1)
        cv2.imwrite(str(tmp_path / "logo.png"), img)
        cv2.imwrite(str(tmp_path / "arte.png"), img)
        files = {"mesa.pdf": b64(tmp_path / "mesa.pdf"), "touch.pdf": b64(tmp_path / "touch.pdf"), "logo.png": b64(tmp_path / "logo.png"), "arte.png": b64(tmp_path / "arte.png")}
        fake = FAKE.replace("%FILES%", json.dumps(files)).replace("%PLUGIN%", json.dumps(pj.read_text(encoding="utf-8")))
        index = (ROOT / "plugin" / "cep" / "index.html").as_uri()

        async def scenario():
            async with Page(free_port()) as p:
                await p.call("Page.addScriptToEvaluateOnNewDocument", source=fake)
                await p.call("Page.navigate", url=index)
                await p.until("document.querySelectorAll('#tabs .tab').length === 7")
                # conexión (origen null + token)
                await p.until("document.getElementById('estado').classList.contains('verde')")
                assert "Conectado a FAVERVIEW" in await p.js("document.getElementById('estado').innerText")
                # ---- Preflight
                await p.js("document.getElementById('tab-preflight').click()")
                await p.until("document.querySelectorAll('#pane-preflight select option').length >= 5")
                await p.js("document.querySelector('#pane-preflight select').value = 'basico'")
                await p.js("[...document.querySelectorAll('#pane-preflight button')].find(b => b.textContent === 'Revisar mesa actual').click()")
                await p.until("document.querySelectorAll('#pane-preflight .hallazgo').length > 0")
                await p.js("document.querySelector('#pane-preflight .hallazgo').click()")
                await p.until("window.__hostLog.some(x => x.name === 'zoomTo')")
                await p.js("[...document.querySelectorAll('#pane-preflight button')].find(b => b.textContent === 'Marcar todos en el documento').click()")
                await p.until("window.__hostLog.some(x => x.name === 'markers' && x.args.lista.length > 0)")
                # correcciones nativas: ver (soloContar) y aplicar
                await p.js("document.querySelectorAll('#pane-preflight .fix button')[0].click()")
                await p.until("window.__hostLog.some(x => x.name === 'fixOverprint' && x.args.soloContar === true)")
                # ---- Vectorizar
                await p.js("document.getElementById('tab-vectorizar').click()")
                await p.js("[...document.querySelectorAll('#pane-vectorizar button')].find(b => b.textContent === 'Vectorizar').click()")
                await p.until("[...document.querySelectorAll('#pane-vectorizar .hint')].some(e => /trazados/.test(e.textContent))", 60)
                await p.until("![...document.querySelectorAll('#pane-vectorizar button')].find(b => b.textContent === 'Colocar sobre la imagen').disabled")
                await p.js("[...document.querySelectorAll('#pane-vectorizar button')].find(b => b.textContent === 'Colocar sobre la imagen').click()")
                await p.until("window.__hostLog.some(x => x.name === 'placeOverSelection' && /vector\\.pdf$/.test(x.args.ruta))")
                assert await p.js("Object.keys(window.__written).some(k => /vector\\.pdf$/.test(k))")           # el PDF se descargó a temporales
                # ---- Códigos
                await p.js("document.getElementById('tab-codigos').click()")
                await p.until("!!document.querySelector('#pane-codigos .vista-svg svg')")
                await p.js("[...document.querySelectorAll('#pane-codigos button')].find(b => b.textContent === 'Insertar').click()")
                await p.until("window.__hostLog.some(x => x.name === 'insertPDF' && x.args.ancho_pt > 90)")
                # ---- Trap con arte plano
                await p.js("window.__mesa = 'touch.pdf'")
                await p.js("document.getElementById('tab-trap').click()")
                await p.until("document.querySelectorAll('#pane-trap select option').length >= 6")
                await p.js("[...document.querySelectorAll('#pane-trap button')].find(b => b.textContent === 'Analizar registro').click()")
                await p.until("/filetes/.test(document.querySelector('#pane-trap .info').textContent)", 90)
                assert "\u2718" in await p.js("document.querySelector('#pane-trap .info').textContent")
                await p.until("window.__hostLog.some(x => x.name === 'markers' && x.args.lista.length > 0)")
                await p.js("[...document.querySelectorAll('#pane-trap button')].find(b => b.textContent === 'Crear traps vectoriales').click()")
                await p.until("window.__hostLog.some(x => x.name === 'placePDF' && x.args.capa && /Traps/.test(x.args.capa))", 120)
                # ---- Ajustes
                await p.js("document.getElementById('tab-ajustes').click()")
                await p.until("/Versi.n del panel/.test(document.querySelector('#pane-ajustes').innerText)")
                errors = list(p.errors)
                return errors

        errors = asyncio.run(scenario())
        assert not errors, errors
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
