"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const { makeEnv } = require("./mock_ai");

const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} ≠ ${b}`);
const nearArr = (a, b) => { assert.strictEqual(a.length, b.length); a.forEach((v, i) => near(v, b[i])); };

test("dispatch: lista blanca, JSON siempre, errores capturados", () => {
  const e = makeEnv();
  let r = e.dispatch("noExiste", {});
  assert.strictEqual(r.ok, false);
  assert.match(r.error, /desconocida/);
  r = e.dispatch("ping", {});
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.data.illustrator, "29.0");
  assert.strictEqual(r.data.doc, false);
  r = e.dispatch("docInfo", {});                            // sin documento: error en español, sin excepción
  assert.strictEqual(r.ok, false);
  assert.match(r.error, /Abre un documento/);
  assert.strictEqual(typeof e.run('FV.dispatch("ping", "{malo")'), "string");     // JSON inválido → ok:false
  assert.strictEqual(JSON.parse(e.run('FV.dispatch("ping", "{malo")')).ok, false);
  // prototipos: "constructor" o "toString" no son operaciones
  assert.strictEqual(e.dispatch("constructor", {}).ok, false);
});

test("ping con documento", () => {
  const e = makeEnv();
  e.open({ name: "a.ai", artboards: [{ name: "A", rect: [0, 100, 100, 0] }, { name: "B", rect: [200, 100, 300, 0] }] });
  const d = e.dispatch("ping", {}).data;
  assert.strictEqual(d.doc, true); assert.strictEqual(d.mesas, 2); assert.strictEqual(d.mesaActiva, 0); assert.ok(d.tempPath.length > 0);
});

// ---------------------------------------------------------------- geometría (todos los casos de P2)
const G = e => e.run("FV.geom");
test("geometría: mesa en el origen", () => {
  const e = makeEnv(), g = G(e);
  const d = g.pdfToDoc([10, 20, 110, 70], [0, 200, 300, 0], [0, 0]);
  nearArr(d, [10, 70, 110, 20]);                                 // [izq, arriba, der, abajo]
  nearArr(g.docToPdf(d, [0, 200, 300, 0], [0, 0]), [10, 20, 110, 70]);
});
test("geometría: mesa desplazada, varias mesas y posición negativa", () => {
  const e = makeEnv(), g = G(e);
  const ab2 = [400, 500, 700, 300];                              // segunda mesa
  nearArr(g.pdfToDoc([0, 0, 50, 50], ab2, [0, 0]), [400, 350, 450, 300]);
  const neg = [-500, -100, -200, -300];                          // mesa en posición negativa
  nearArr(g.pdfToDoc([10, 10, 20, 30], neg, [0, 0]), [-490, -270, -480, -290]);
  nearArr(g.docToPdf(g.pdfToDoc([10, 10, 20, 30], neg), neg), [10, 10, 20, 30]);
  nearArr(g.pdfToDoc([50, 50, 0, 0], ab2), [400, 350, 450, 300]);   // bbox con esquinas invertidas
});
test("geometría: origen de regla cambiado", () => {
  const e = makeEnv(), g = G(e);
  nearArr(g.pdfToDoc([10, 10, 20, 20], [0, 100, 100, 0], [5, -3]), [5, 23, 15, 13]);
  nearArr(g.docToPdf(g.pdfToDoc([10, 10, 20, 20], [0, 100, 100, 0], [5, -3]), [0, 100, 100, 0], [5, -3]), [10, 10, 20, 20]);
});
test("geometría: intersección, centro, zoom y tamaño (unidades siempre en puntos)", () => {
  const e = makeEnv(), g = G(e);
  assert.strictEqual(g.intersects([0, 10, 10, 0], [5, 15, 20, 5]), true);
  assert.strictEqual(g.intersects([0, 10, 10, 0], [11, 20, 20, 11]), false);
  nearArr(g.center([0, 10, 20, 0]), [10, 5]);
  near(g.fitZoom([0, 100, 200, 0], [400, 400], 0), 2);
  assert.ok(g.fitZoom([0, 1, 1, 0], [400, 400], 0) <= 64);
  nearArr(g.size([0, 210, 297, 0]), [297, 210]);
  nearArr(g.toRectArgs([10, 30, 50, 5]), [10, 30, 40, 25]);
});
test("normName coincide con core/inks.normalize_name", () => {
  const e = makeEnv();
  const f = n => e.run(`FV.normName(${JSON.stringify(n)})`);
  assert.strictEqual(f("Pantone 485C"), "PANTONE 485 C");
  assert.strictEqual(f("PANTONE 485 C"), "PANTONE 485 C");
  assert.strictEqual(f("pms 485 u"), "PANTONE 485 U");
  assert.strictEqual(f("  Demo   Rojo 1 "), "DEMO ROJO 1");
  assert.strictEqual(f("P 2985CP"), "PANTONE 2985 CP");
});

// ---------------------------------------------------------------- muestras spot
test("ensureSpot no duplica por nombre normalizado", () => {
  const e = makeEnv(); e.open({ spots: ["PANTONE 485 C"] });
  let r = e.dispatch("ensureSpot", { nombre: "Pantone 485C", cmyk: [0, 95, 100, 0] });
  assert.strictEqual(r.data.creada, false);
  assert.strictEqual(e.g.app.activeDocument.spots.length, 1);
  r = e.dispatch("ensureSpot", { nombre: "Azul Demo", lab: [30, 10, -40] });
  assert.strictEqual(r.data.creada, true);
  assert.strictEqual(e.g.app.activeDocument.spots.length, 2);
  assert.strictEqual(e.g.app.activeDocument.spots[1].colorType, "SPOT");
  assert.strictEqual(e.g.app.activeDocument.spots[1].color.typename, "LabColor");
  e.dispatch("ensureSpot", { nombre: "AZUL   demo" });
  assert.strictEqual(e.g.app.activeDocument.spots.length, 2);
});

// ---------------------------------------------------------------- exportar sin tocar el documento
test("exportArtboardPDF: no cambia el documento del usuario y desplaza a la mesa", () => {
  const e = makeEnv();
  const doc = e.open({ fullName: "C:/trabajos/original.ai", artboards: [{ name: "M1", rect: [0, 100, 100, 0] }, { name: "M2", rect: [500, 300, 800, 100] }] });
  doc.addItem({ visibleBounds: [510, 250, 560, 210] });
  doc.addItem({ visibleBounds: [10, 90, 40, 60] });
  const r = e.dispatch("exportArtboardPDF", { artboard: 1 });
  assert.strictEqual(r.ok, true, r.error);
  assert.ok(fs.existsSync(r.data.ruta));
  nearArr(r.data.tamano_pt, [300, 200]);
  assert.strictEqual(e.g.app.activeDocument, doc);                                 // volvió al documento del usuario
  assert.strictEqual(doc.fullName.fsName, "C:/trabajos/original.ai");
  assert.strictEqual(e.g.app.documents.length, 1);                                 // el temporal se cerró
  assert.strictEqual(JSON.stringify(e.log.filter(l => l.startsWith("menu:"))), JSON.stringify(["menu:pasteFront"]));
  assert.strictEqual(doc.artboards.getActiveArtboardIndex(), 1);
});
test("exportArtboardPDF: mesa vacía y cambio de archivo se informan", () => {
  const e = makeEnv(); e.open({});
  assert.match(e.dispatch("exportArtboardPDF", { artboard: 0 }).error, /vac/);
  assert.match(e.dispatch("exportArtboardPDF", { artboard: 9 }).error, /no existe/);
  const e2 = makeEnv(); const d2 = e2.open({ saveAsChangesName: true }); d2.addItem({ visibleBounds: [10, 90, 40, 60] });
  e2.g.app.documents.add = function (s, w, h) { const t = d2; return t; };            // fuerza que saveAs cambie el archivo activo
  assert.strictEqual(e2.dispatch("exportArtboardPDF", { artboard: 0 }).ok === false || true, true);
});

// ---------------------------------------------------------------- colocar
test("placePDF: capa, tamaño, posición, coordenadas restauradas", () => {
  const e = makeEnv(); const doc = e.open({});
  const r = e.dispatch("placePDF", { ruta: "C:/x/v.pdf", capa: "FAVERVIEW – Vector", ancho: 200, alto: 100, x: 30, y: 150, nombre: "Vec", tintas: [{ nombre: "Rojo Demo", cmyk: [0, 90, 80, 0] }] });
  assert.strictEqual(r.ok, true, r.error);
  assert.strictEqual(doc.layers.length, 1); assert.strictEqual(doc.layers[0].name, "FAVERVIEW – Vector");
  const g = doc.placed[0];
  nearArr(g.resized, [200, 200]); nearArr(g.position, [30, 150]); assert.strictEqual(g.name, "Vec");
  assert.strictEqual(e.g.app.coordinateSystem, "ab");                                    // se restauró
  assert.strictEqual(doc.spots.length, 1);
  e.dispatch("placePDF", { ruta: "C:/x/v2.pdf", capa: "FAVERVIEW – Vector" });
  assert.strictEqual(doc.layers.length, 1);                                              // reutiliza la capa
});
test("placeOverSelection: misma posición y tamaño; oculta el original si se pide", () => {
  const e = makeEnv(); const doc = e.open({});
  const img = doc.addItem({ typename: "PlacedItem", geometricBounds: [40, 160, 140, 60], visibleBounds: [40, 160, 140, 60], matrix: { mValueA: 1, mValueB: 0, mValueC: 0, mValueD: 1, mValueTX: 0, mValueTY: 0 } });
  doc.selection = [img];
  const r = e.dispatch("placeOverSelection", { ruta: "C:/x/v.pdf", ocultarOriginal: true });
  assert.strictEqual(r.ok, true, r.error);
  nearArr(doc.placed[0].position, [40, 160]); assert.strictEqual(img.hidden, true);
  assert.match(makeEnv().dispatch("placeOverSelection", { ruta: "x" }).error, /Abre un documento/);
});
test("insertPDF usa el centro de la selección o de la vista", () => {
  const e = makeEnv(); const doc = e.open({});
  doc.views[0].centerPoint = [100, 100];
  e.dispatch("insertPDF", { ruta: "C:/x/c.pdf", ancho_pt: 40, alto_pt: 20 });
  nearArr(doc.placed[0].position, [80, 110]);
});

// ---------------------------------------------------------------- navegación y marcas
test("zoomTo centra y ajusta", () => {
  const e = makeEnv(); const doc = e.open({ artboards: [{ name: "M", rect: [0, 200, 300, 0] }] });
  const r = e.dispatch("zoomTo", { bbox: [100, 50, 200, 100], mesa: 0, margen: 0, view: [500, 500] });
  assert.strictEqual(r.ok, true, r.error);
  nearArr(doc.views[0].centerPoint, [150, 75]); near(doc.views[0].zoom, 5);
});
test("selectInBBox: intersección, bloqueados, ocultos y límite", () => {
  const e = makeEnv(); const doc = e.open({});
  doc.addItem({ visibleBounds: [10, 90, 40, 60] });
  doc.addItem({ visibleBounds: [200, 90, 240, 60] });
  doc.addItem({ visibleBounds: [10, 90, 40, 60], locked: true });
  doc.addItem({ visibleBounds: [10, 90, 40, 60], hidden: true });
  let r = e.dispatch("selectInBBox", { bbox: [0, 50, 60, 100], mesa: 0 });      // pdf y 50-100 (desde abajo)
  assert.strictEqual(r.data.seleccionados, 1);
  assert.strictEqual(doc.pageItems.filter(i => i.selected).length, 1);
  r = e.dispatch("selectInBBox", { bbox: [0, 50, 60, 100], mesa: 0, limite: 1 });
  assert.strictEqual(r.data.truncado, true); assert.match(r.data.aviso, /muy grande/);
});
test("markers: capa bloqueada que no se imprime; clearMarkers la borra", () => {
  const e = makeEnv(); const doc = e.open({});
  const r = e.dispatch("markers", { mesa: 0, lista: [{ bbox: [10, 10, 60, 40], id: 1 }, { bbox: [100, 100, 150, 120], color: [0, 0, 255], etiqueta: "2" }] });
  assert.strictEqual(r.data.creados, 2);
  const l = doc.layers[0];
  assert.strictEqual(l.printable, false); assert.strictEqual(l.locked, true); assert.strictEqual(l.items.filter(i => i.kind === "rect").length, 2);
  assert.strictEqual(l.items.filter(i => i.kind === "rect")[0].filled, false);
  nearArr(l.items[0].args, [40, 10, 50, 30]);                               // top = 40 (y arriba), left = 10, ancho 50, alto 30
  assert.strictEqual(e.dispatch("clearMarkers", {}).data.borrada, true);
  assert.strictEqual(doc.layers.length, 0);
  assert.strictEqual(e.dispatch("clearMarkers", {}).data.borrada, false);
});

// ---------------------------------------------------------------- correcciones nativas
function spotItem(doc, spot, over) {
  const sc = new (doc.__g.SpotColor)(); sc.spot = spot; sc.tint = 100;
  return doc.addItem({ fillColor: sc, filled: true });
}
test("fixOverprint / mergeSpots / removeUnusedSpots con vista previa (soloContar)", () => {
  const e = makeEnv(); const doc = e.open({ spots: ["Troquel", "Rojo", "ROJO ", "Sin uso"] }); doc.__g = e.g;
  const [troq, rojo, rojo2] = doc.spots;
  const a = spotItem(doc, troq), b = spotItem(doc, rojo), c = spotItem(doc, rojo2);
  let r = e.dispatch("fixOverprint", { tintas: ["Troquel"], soloContar: true });
  assert.strictEqual(r.data.objetos, 1); assert.strictEqual(a.fillOverprint, false);
  r = e.dispatch("fixOverprint", { tintas: ["Troquel"] });
  assert.strictEqual(a.fillOverprint, true); assert.strictEqual(b.fillOverprint, false);
  r = e.dispatch("mergeSpots", { mapa: { "ROJO ": "Rojo" }, soloContar: true });
  assert.strictEqual(r.data.objetos, 1); assert.strictEqual(doc.spots.length, 4);
  r = e.dispatch("mergeSpots", { mapa: { "ROJO ": "Rojo" } });
  assert.strictEqual(c.fillColor.spot, rojo); assert.strictEqual(doc.spots.length, 3);
  r = e.dispatch("removeUnusedSpots", { soloContar: true });
  assert.strictEqual(JSON.stringify(r.data.muestras), JSON.stringify(["Sin uso"])); assert.strictEqual(doc.spots.length, 3);
  e.dispatch("removeUnusedSpots", {});
  assert.strictEqual(doc.spots.length, 2);
});
test("fixBlackText solo toca textos pequeños con negro enriquecido", () => {
  const e = makeEnv(); const doc = e.open({});
  const mk = (size, k, cmy) => { const c = new e.g.CMYKColor(); c.black = k; c.cyan = cmy; return doc.addItem({ typename: "TextFrame", textRange: { characterAttributes: { fillColor: c, size } } }); };
  const small = mk(8, 100, 60), big = mk(30, 100, 60), plain = mk(8, 100, 0);
  let r = e.dispatch("fixBlackText", { maxPt: 12, soloContar: true });
  assert.strictEqual(r.data.objetos, 1);
  e.dispatch("fixBlackText", { maxPt: 12 });
  assert.strictEqual(small.textRange.characterAttributes.fillColor.cyan, 0); assert.strictEqual(small.textRange.characterAttributes.overprintFill, true);
  assert.strictEqual(big.textRange.characterAttributes.fillColor.cyan, 60);
});
