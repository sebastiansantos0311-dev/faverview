"use strict";
/* Carga los módulos core del panel en un contexto de Node con CEP simulado (cep.fs, CSInterface → mock de Illustrator). Solo pruebas. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { makeEnv } = require("../host_mock/mock_ai");

const CEP = path.join(__dirname, "..", "..", "cep");

function load(opts = {}) {
  const ai = makeEnv();
  if (opts.doc !== false) ai.open({ spots: opts.spots || [] });
  const g = { console, setTimeout, clearTimeout, atob, btoa, Blob, FormData, URL, Promise, JSON, Math, Date, Uint8Array, String, Array, Object, Error, fetch: opts.fetch || fetch, navigator: { platform: "Win32" } };
  g.window = g; g.globalThis = g;
  const store = { writes: {} };
  g.cep = {
    encoding: { Base64: "Base64", UTF8: "UTF-8" },
    fs: {
      readFile(p, e) { try { const b = fs.readFileSync(p); return { err: 0, data: e === "Base64" ? b.toString("base64") : b.toString("utf8") }; } catch (x) { return { err: 2 }; } },
      writeFile(p, d, e) { try { fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, e === "Base64" ? Buffer.from(d, "base64") : d); store.writes[p] = true; return { err: 0 }; } catch (x) { return { err: 3 }; } },
      stat(p) { try { const s = fs.statSync(p); return { err: 0, data: { size: s.size, mtime: s.mtime } }; } catch (x) { return { err: 2 }; } },
      readdir(p) { try { return { err: 0, data: fs.readdirSync(p) }; } catch (x) { return { err: 2 }; } },
      deleteFile(p) { fs.rmSync(p, { force: true }); return { err: 0 }; },
      showOpenDialogEx() { return { err: 0, data: opts.openPath ? [opts.openPath] : [] }; },
      showSaveDialogEx() { return { err: 0, data: opts.savePath || "" }; }
    }
  };
  g.__adobe_cep__ = {
    evalScript(script, cb) { const r = ai.run(script); setTimeout(() => cb(r), 0); },
    getHostEnvironment() { return JSON.stringify({ appSkinInfo: { panelBackgroundColor: { color: { red: 50, green: 50, blue: 50 } } } }); },
    getSystemPath() { return encodeURI(opts.userData || path.dirname(opts.pluginJsonDir || "")); },
    addEventListener() {}, removeEventListener() {}
  };
  const ctx = vm.createContext(g);
  const files = ["lib/CSInterface.js", "core/i18n.js", "core/host.js", "core/files.js", "core/api.js", "core/theme.js"].concat(opts.extra || []);
  for (const f of files) vm.runInContext(fs.readFileSync(path.join(CEP, "js", f), "utf8"), ctx, { filename: f });
  return { g, ai, FVP: g.FVP, store };
}

module.exports = { load, CEP };
