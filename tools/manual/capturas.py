"""Capturas de pantalla para el manual (desarrollo). Necesita la app abierta y Edge instalado.

Uso:  uv run python tools/manual/capturas.py [http://127.0.0.1:8000]
Genera los PNG de los módulos de la suite en tools/manual/img/ (con archivos sintéticos del repositorio)."""
import asyncio
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import websockets

ROOT = Path(__file__).resolve().parents[2]
IMG = Path(__file__).with_name("img")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9555
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def make_assets(d: Path) -> dict:
    img = np.full((300, 420, 3), 255, np.uint8)
    cv2.circle(img, (120, 150), 90, (220, 30, 30), -1, cv2.LINE_AA)
    cv2.rectangle(img, (240, 60), (390, 240), (30, 60, 200), -1, cv2.LINE_AA)
    cv2.circle(img, (120, 150), 35, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.putText(img, "LOGO", (262, 165), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.imwrite(str(d / "logo.png"), img)
    return {"logo": d / "logo.png", "completo": ROOT / "tests" / "sinteticos_sep" / "completo.pdf"}


class Edge:
    def __init__(self):
        self.prof = tempfile.mkdtemp(prefix="fv_edge_")
        self.proc = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={PORT}", "--window-size=1440,1000", "--hide-scrollbars",
                                      f"--user-data-dir={self.prof}", "about:blank"])
        time.sleep(4)
        tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
        self.url = [t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"]
        self.n = 0

    async def __aenter__(self):
        self.ws = await websockets.connect(self.url, max_size=80_000_000)
        self._pending = {}
        self._reader = asyncio.create_task(self._read())
        await self.call("Page.enable")
        await self.call("DOM.enable")
        await self.call("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
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

    async def call(self, method, **params):
        self.n += 1
        fut = asyncio.get_event_loop().create_future()
        self._pending[self.n] = fut
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        return await fut

    async def js(self, code):
        r = await self.call("Runtime.evaluate", expression=code, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")

    async def go(self, hash_, wait=2.0):
        await self.call("Page.navigate", url="about:blank")
        await asyncio.sleep(0.5)
        await self.call("Page.navigate", url=f"{BASE}/#/{hash_}")
        await asyncio.sleep(wait)

    async def upload(self, selector: str, path: Path):
        doc = await self.call("DOM.getDocument")
        node = await self.call("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=selector)
        await self.call("DOM.setFileInputFiles", files=[str(path)], nodeId=node["nodeId"])
        await self.js(f"document.querySelector('{selector}').dispatchEvent(new Event('change'))")

    async def shot(self, name: str):
        r = await self.call("Page.captureScreenshot", format="png")
        (IMG / f"{name}.png").write_bytes(base64.b64decode(r["data"]))
        print("captura", name)


async def main():
    IMG.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        a = make_assets(Path(t))
        async with Edge() as b:
            await b.go("comparar", 2.5)
            await b.shot("s01_suite")
            await b.js("document.querySelector('#btn-tintas').click()")
            await asyncio.sleep(1.2)
            await b.shot("s02_tintas")
            await b.go("separar", 2)
            await b.upload("#sp-drop input", a["completo"])
            await asyncio.sleep(9)
            await b.shot("s03_separar_pdf")
            await b.js("document.querySelector('#sp-tac').click()")
            await asyncio.sleep(2)
            await b.shot("s04_separar_tac")
            await b.js("document.querySelector('.sep-tabs [data-sub=img]').click()")
            await b.upload("#si-drop input", a["logo"])
            await asyncio.sleep(6)
            await b.shot("s05_separar_imagen")
            await b.go("vectorizar", 2)
            await b.upload("#vz-drop input", a["logo"])
            await asyncio.sleep(7)
            await b.shot("s06_vectorizar")
            await b.js("document.querySelector('#vz-ver').value='contornos'; document.querySelector('#vz-ver').dispatchEvent(new Event('change'))")
            await asyncio.sleep(2)
            await b.shot("s07_vectorizar_contornos")
            await b.go("preflight", 2)
            await b.upload("#pf-drop input", a["completo"])
            await asyncio.sleep(9)
            await b.shot("s08_preflight")
            await b.go("codigos", 2.5)
            await b.shot("s09_codigos")
            await b.go("herramientas", 2)
            await b.js("document.querySelector('[data-t=braille]').click()")
            await asyncio.sleep(1.5)
            await b.shot("s10_braille")
            await b.js("document.querySelector('[data-t=step]').click()")
            await b.upload("#tl-drop input", a["completo"])
            await asyncio.sleep(2)
            await b.js("document.querySelector('#st-go').click()")
            await asyncio.sleep(4)
            await b.shot("s11_step_repeat")
            await b.js("document.querySelector('[data-t=trap]').click()")
            await b.js("document.querySelector('#tr-dpi').value=300; document.querySelector('#tr-go').click()")
            await asyncio.sleep(9)
            await b.shot("s12_trapping")
            await b.go("automatizar", 3)
            await b.shot("s13_automatizar")


if __name__ == "__main__":
    asyncio.run(main())
