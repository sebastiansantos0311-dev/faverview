"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { load } = require("./harness");

const PLUGIN_JSON = process.env.FV_PLUGIN_JSON;          // lo prepara pytest con un servidor real
const needServer = { skip: PLUGIN_JSON ? false : "sin servidor de pruebas (FV_PLUGIN_JSON)" };

function withUserData(jsonPath) {
  // el panel busca <userData>/FAVERVIEW/plugin.json; se arma esa estructura apuntando al archivo real
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "fvud-"));
  fs.mkdirSync(path.join(base, "FAVERVIEW"));
  if (jsonPath) fs.copyFileSync(jsonPath, path.join(base, "FAVERVIEW", "plugin.json"));
  return base;
}

// ---------------------------------------------------------------- host.js contra el mock de Illustrator
test("HostAdapter: escapa bien comillas, saltos de línea y unicode", async () => {
  const { FVP, ai } = load();
  const r = await FVP.host.call("ensureSpot", { nombre: 'Tinta "rara"\nñ – 100%', cmyk: [0, 0, 0, 100] });
  assert.strictEqual(r.creada, true);
  assert.strictEqual(ai.g.app.activeDocument.spots[0].name, 'Tinta "rara"\nñ – 100%');
});
test("HostAdapter: errores del host llegan como Error en español; timeout", async () => {
  const { FVP } = load({ doc: false });
  await assert.rejects(() => FVP.host.call("docInfo", {}), /Abre un documento/);
  await assert.rejects(() => FVP.host.call("noExiste", {}), /desconocida/);
  FVP.host._cs = { evalScript() { /* nunca responde */ } };
  await assert.rejects(() => FVP.host.call("ping", {}, 30), /no respondió a tiempo/);
  FVP.host._cs = { evalScript(s, cb) { cb("EvalScript error."); } };
  await assert.rejects(() => FVP.host.call("ping", {}), /No se pudo ejecutar/);
  FVP.host._cs = { evalScript(s, cb) { cb(""); } };
  await assert.rejects(() => FVP.host.call("ping", {}), /no devolvió respuesta/);
  FVP.host._cs = { evalScript(s, cb) { cb("no es json"); } };
  await assert.rejects(() => FVP.host.call("ping", {}), /no válida/);
});

// ---------------------------------------------------------------- files.js
test("files: Base64 ida y vuelta, tamaño y limpieza de temporales", () => {
  const { FVP } = load();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fvf-"));
  const p = path.join(dir, "a.bin");
  const data = new Uint8Array(70000).map((_, i) => i % 251);
  FVP.files.writeArrayBuffer(p, data.buffer);
  assert.strictEqual(fs.statSync(p).size, 70000);
  const blob = FVP.files.readBlob(p, "application/pdf");
  assert.strictEqual(blob.size, 70000); assert.strictEqual(blob.type, "application/pdf");
  assert.ok(FVP.files.sizeMB(p) > 0.06 && FVP.files.exists(p) && !FVP.files.exists(p + "x"));
  fs.utimesSync(p, new Date(Date.now() - 48 * 3600e3), new Date(Date.now() - 48 * 3600e3));
  assert.strictEqual(FVP.files.cleanTemp(dir, 24), 1);
  assert.throws(() => FVP.files.readText(path.join(dir, "nada")), /No se pudo leer/);
});

// ---------------------------------------------------------------- tema, i18n, versiones
test("tema: oscuro/claro según el fondo del panel", () => {
  const { FVP } = load();
  assert.strictEqual(FVP.theme.fromSkin({ panelBackgroundColor: { color: { red: 50, green: 50, blue: 50 } } }), "dark");
  assert.strictEqual(FVP.theme.fromSkin({ panelBackgroundColor: { color: { red: 240, green: 240, blue: 240 } } }), "light");
  assert.strictEqual(FVP.theme.fromSkin(null), "dark");
});
test("i18n: claves con parámetros y faltantes", () => {
  const { FVP } = load();
  assert.strictEqual(FVP.t("estado.verde", { version: "3.1.0" }), "Conectado a FAVERVIEW 3.1.0");
  assert.strictEqual(FVP.t("no.existe"), "no.existe");
  assert.ok(FVP.i18nKeys().length > 80);
});
test("cmpVersion", () => {
  const { FVP } = load({ extra: ["ui/common.js", "ui/settings.js"] });
  assert.strictEqual(FVP.cmpVersion("3.1.0", "3.1.1"), -1); assert.strictEqual(FVP.cmpVersion("3.2", "3.1.9"), 1); assert.strictEqual(FVP.cmpVersion("3.1.0", "3.1.0"), 0);
});

// ---------------------------------------------------------------- api.js contra el servidor real
test("conexión: rojo sin plugin.json", async () => {
  const ud = withUserData(null);
  const { FVP } = load({ userData: ud });
  const st = await FVP.api.connect();
  assert.strictEqual(st.estado, "rojo"); assert.match(st.mensaje, /no está abierto/);
});
test("conexión: verde con el servidor real y token", needServer, async () => {
  const { FVP } = load({ userData: withUserData(PLUGIN_JSON) });
  const st = await FVP.api.connect();
  assert.strictEqual(st.estado, "verde", st.mensaje); assert.match(st.mensaje, /Conectado a FAVERVIEW/);
  assert.ok(FVP.api.state.handshake.max_upload_mb > 0);
});
test("conexión: token malo → rojo (401); versión incompatible → amarillo", needServer, async () => {
  const j = JSON.parse(fs.readFileSync(PLUGIN_JSON, "utf8")); j.token = "x".repeat(43);
  const bad = path.join(os.tmpdir(), "fvbad.json"); fs.writeFileSync(bad, JSON.stringify(j));
  let { FVP } = load({ userData: withUserData(bad) });
  assert.strictEqual((await FVP.api.connect()).estado, "rojo");
  ({ FVP } = load({ userData: withUserData(PLUGIN_JSON) }));
  const real = FVP.api._f();
  for (const [v, motivo] of [[2, "plugin"], [0, "servidor"]]) {
    FVP.api._fetch = async (u, i) => { const r = await real(u, i); const b = await r.json(); return new Response(JSON.stringify({ ...b, api_version: v }), { status: 200, headers: { "content-type": "application/json" } }); };
    const st = await FVP.api.connect();
    assert.strictEqual(st.estado, "amarillo"); assert.strictEqual(st.motivo, motivo);
  }
});
test("errores del servidor se muestran en español y el servidor no acepta sin token", needServer, async () => {
  const { FVP } = load({ userData: withUserData(PLUGIN_JSON) });
  await FVP.api.connect();
  await assert.rejects(() => FVP.api.postJSON("/api/plugin/codigo", { tipo: "ean13", datos: "1" }), /dígito|debe tener|EAN/i);
  const token = FVP.api.state.token; FVP.api.state.token = "mal";
  await assert.rejects(() => FVP.api.get("/api/plugin/handshake"), /token/);
  FVP.api.state.token = token;
});
test("subida, trabajo con progreso y descarga (vectorizar)", needServer, async () => {
  const { FVP, store } = load({ userData: withUserData(PLUGIN_JSON) });
  await FVP.api.connect();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fvup-"));
  // PNG mínimo de 60×40 con un cuadrado (generado a mano: cabecera + IDAT sin compresión no es trivial; se usa el PNG de assets)
  const png = fs.readFileSync(path.join(__dirname, "..", "archivos", "logo.png"));
  const ruta = path.join(dir, "logo.png"); fs.writeFileSync(ruta, png);
  const seen = [];
  const r = await FVP.api.uploadFile("/api/plugin/vectorizar", "file", ruta, { parametros: { preset: "logo", dpi: 254 }, tamano_mm: 40 }, "image/png");
  const res = await FVP.api.pollJob(r.job_id, (m, p) => seen.push(p));
  assert.ok(res.estadisticas.colores >= 2 && seen.length >= 1);
  const url = res.archivos.find(a => a.nombre === "vector.pdf").url;
  const dest = path.join(dir, "v.pdf");
  await FVP.api.downloadToFile(url, dest);
  assert.strictEqual(fs.readFileSync(dest).subarray(0, 4).toString(), "%PDF");
});
test("cancelar un trabajo", needServer, async () => {
  const { FVP } = load({ userData: withUserData(PLUGIN_JSON) });
  await FVP.api.connect();
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fvc-"));
  const ruta = path.join(dir, "logo.png"); fs.copyFileSync(path.join(__dirname, "..", "archivos", "logo.png"), ruta);
  const r = await FVP.api.uploadFile("/api/plugin/vectorizar", "file", ruta, { parametros: { preset: "logo" } }, "image/png");
  const ctl = { cancelado: true };
  try { await FVP.api.pollJob(r.job_id, null, ctl); } catch (e) { assert.match(e.message, /cancel/i); return; }
  // si el trabajo terminó antes de que llegara la cancelación también es válido
});
test("archivo demasiado grande se rechaza antes de subir", async () => {
  const { FVP } = load();
  FVP.api.state.handshake = { max_upload_mb: 0.001 };
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fvb-")); const p = path.join(dir, "g.pdf"); fs.writeFileSync(p, Buffer.alloc(5000));
  await assert.rejects(() => FVP.api.uploadFile("/x", "file", p, {}), /supera el máximo/);
});
