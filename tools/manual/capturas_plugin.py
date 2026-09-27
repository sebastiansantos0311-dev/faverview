"""Capturas del panel de Illustrator para el manual (desarrollo). Reutiliza el CEP simulado de tests/test_plugin_panel_edge.py.

Uso: uv run python tools/manual/capturas_plugin.py   (arranca su propio servidor FAVERVIEW y Edge; escribe en tools/manual/img/)"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import test_plugin_panel_edge as T  # noqa: E402

IMG = Path(__file__).with_name("img")


async def shot(p, name):
    r = await p.call("Page.captureScreenshot", format="png")
    (IMG / f"{name}.png").write_bytes(base64.b64decode(r["data"]))
    print("captura", name)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="fvplug_"))
    port = T.free_port()
    pj = tmp / "plugin.json"
    env = {**os.environ, "FAVERVIEW_PLUGIN_JSON": str(pj), "FAVERVIEW_PORT": str(port), "FAVERVIEW_DATOS": str(tmp / "datos")}
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=1)
                if pj.exists():
                    break
            except Exception:
                time.sleep(0.25)
        doc = pymupdf.open()
        doc.new_page(width=283.5, height=283.5).add_text_annot((50, 50), "nota")
        doc.save(str(tmp / "mesa.pdf"))
        T.touching_pdf(tmp / "touch.pdf")
        img = np.full((200, 300, 3), 255, np.uint8)
        cv2.circle(img, (100, 100), 60, (30, 30, 220), -1)
        cv2.rectangle(img, (170, 60), (270, 150), (30, 150, 60), -1)
        cv2.imwrite(str(tmp / "logo.png"), img)
        files = {n: T.b64(tmp / n) for n in ("mesa.pdf", "touch.pdf", "logo.png")}
        fake = T.FAKE.replace("%FILES%", json.dumps(files)).replace("%PLUGIN%", json.dumps(pj.read_text(encoding="utf-8")))
        index = (ROOT / "plugin" / "cep" / "index.html").as_uri()

        async def run():
            async with T.Page(T.free_port()) as p:
                await p.call("Emulation.setDeviceMetricsOverride", width=360, height=720, deviceScaleFactor=1.5, mobile=False)
                await p.call("Page.addScriptToEvaluateOnNewDocument", source=fake)
                await p.call("Page.navigate", url=index)
                await p.until("document.getElementById('estado').classList.contains('verde')")
                await p.until("document.querySelectorAll('#pane-vectorizar select option').length >= 5")
                await asyncio.sleep(0.5)
                await p.js("[...document.querySelectorAll('#pane-vectorizar button')].find(b => b.textContent === 'Vectorizar').click()")
                await p.until("[...document.querySelectorAll('#pane-vectorizar .hint')].some(e => /trazados/.test(e.textContent))", 60)
                await asyncio.sleep(0.8)
                await shot(p, "p01_vectorizar")
                await p.js("document.getElementById('tab-preflight').click()")
                await p.until("document.querySelectorAll('#pane-preflight select option').length >= 5")
                await p.js("document.querySelector('#pane-preflight select').value = 'basico'")
                await p.js("[...document.querySelectorAll('#pane-preflight button')].find(b => b.textContent === 'Revisar mesa actual').click()")
                await p.until("document.querySelectorAll('#pane-preflight .hallazgo').length > 0")
                await asyncio.sleep(0.5)
                await shot(p, "p02_preflight")
                await p.js("document.getElementById('tab-codigos').click()")
                await p.until("!!document.querySelector('#pane-codigos .vista-svg svg')")
                await asyncio.sleep(0.5)
                await shot(p, "p03_codigos")
                await p.js("window.__mesa = 'touch.pdf'; document.getElementById('tab-trap').click()")
                await p.until("document.querySelectorAll('#pane-trap select option').length >= 6")
                await p.js("[...document.querySelectorAll('#pane-trap button')].find(b => b.textContent === 'Analizar registro').click()")
                await p.until("/filetes/.test(document.querySelector('#pane-trap .info').textContent)", 90)
                await asyncio.sleep(0.5)
                await shot(p, "p04_trap")
                await p.js("document.getElementById('tab-ajustes').click()")
                await asyncio.sleep(0.6)
                await shot(p, "p05_ajustes")

        asyncio.run(run())
    finally:
        srv.terminate()


if __name__ == "__main__":
    IMG.mkdir(exist_ok=True)
    main()
