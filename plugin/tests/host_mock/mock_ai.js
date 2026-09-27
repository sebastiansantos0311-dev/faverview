"use strict";
/* Simulación mínima de la API de Illustrator (ExtendScript) para probar fv_host.jsx en Node. SOLO para pruebas: no va al panel. */
const fs = require("fs");
const os = require("os");
const path = require("path");
const vm = require("vm");

function makeEnv(opts = {}) {
  const log = [];
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "fvmock-"));
  const g = { Math, JSON, String, Number, Object, Array, RegExp, isFinite, SyntaxError, Date, eval };
  g.$log = log;

  class FolderC { constructor(p) { this.fsName = p; } get exists() { return fs.existsSync(this.fsName); } create() { fs.mkdirSync(this.fsName, { recursive: true }); return true; } }
  FolderC.temp = new FolderC(tempRoot);
  class FileC { constructor(p) { this.fsName = p; } get exists() { return fs.existsSync(this.fsName); } remove() { fs.rmSync(this.fsName, { force: true }); } }
  g.Folder = FolderC; g.File = FileC;
  g.CoordinateSystem = { DOCUMENTCOORDINATESYSTEM: "doc", ARTBOARDCOORDINATESYSTEM: "ab" };
  g.ColorModel = { SPOT: "SPOT", PROCESS: "PROCESS" };
  g.SaveOptions = { DONOTSAVECHANGES: "no" };
  g.ExportType = { PNG24: "png" };
  g.Transformation = { TOPLEFT: "tl", CENTER: "c" };
  g.PDFSaveOptions = function () { this.kind = "pdfopts"; };
  g.ExportOptionsPNG24 = function () { this.kind = "pngopts"; };
  g.CMYKColor = function () { this.typename = "CMYKColor"; this.cyan = 0; this.magenta = 0; this.yellow = 0; this.black = 0; };
  g.RGBColor = function () { this.typename = "RGBColor"; this.red = 0; this.green = 0; this.blue = 0; };
  g.LabColor = function () { this.typename = "LabColor"; this.l = 0; this.a = 0; this.b = 0; };
  g.SpotColor = function () { this.typename = "SpotColor"; this.spot = null; this.tint = 100; };

  function listWithApi(arr, extra) { Object.assign(arr, extra); return arr; }

  function makeItem(o) {
    return Object.assign({ typename: "PathItem", locked: false, hidden: false, selected: false, filled: true, stroked: false, layer: null,
      visibleBounds: [0, 0, 0, 0], geometricBounds: [0, 0, 0, 0], fillOverprint: false, strokeOverprint: false,
      translate(dx, dy) { const b = this.visibleBounds; this.visibleBounds = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]; this.translated = [dx, dy]; } }, o);
  }

  function makeLayer(doc, name) {
    const layer = { name, locked: false, visible: true, printable: true, items: [], removed: false,
      remove() { this.removed = true; doc.layers.splice(doc.layers.indexOf(this), 1); },
      pathItems: { rectangle(top, left, w, h) { const it = makeItem({ kind: "rect", args: [top, left, w, h], visibleBounds: [left, top, left + w, top - h], layer }); layer.items.push(it); return it; } },
      textFrames: { add() { const t = makeItem({ typename: "TextFrame", kind: "text", textRange: { characterAttributes: {} }, layer }); layer.items.push(t); return t; } },
      groupItems: { createFromFile(f) { const gi = makeItem({ typename: "GroupItem", kind: "group", file: f.fsName, width: 100, height: 50, geometricBounds: [0, 50, 100, 0],
        position: [0, 0], resize(sx, sy) { this.resized = [sx, sy]; this.width = this.width * sx / 100; this.height = this.height * sy / 100; this.geometricBounds = [0, this.height, this.width, 0]; },
        rotate(a) { this.rotated = a; }, layer }); layer.items.push(gi); doc.placed.push(gi); return gi; } } };
    const layer2 = layer; // referencia para los items
    return layer2;
  }

  function makeDoc(spec = {}) {
    const doc = { name: spec.name || "prueba.ai", fullName: { fsName: spec.fullName || "C:/trabajos/prueba.ai" }, documentColorSpace: "CMYK", rulerUnits: "Millimeters",
      rulerOrigin: spec.rulerOrigin || [0, 0], selection: null, closed: false, saved: [], placed: [], exported: [] };
    const abs = (spec.artboards || [{ name: "Mesa 1", rect: [0, 200, 300, 0] }]).map(a => ({ name: a.name, artboardRect: a.rect }));
    let active = 0;
    doc.artboards = listWithApi(abs, { getActiveArtboardIndex: () => active, setActiveArtboardIndex: i => { active = i; } });
    doc.layers = listWithApi([], { add() { const l = makeLayer(doc, "Capa"); doc.layers.push(l); return l; } });
    doc.spots = listWithApi((spec.spots || []).map(n => ({ name: n, typename: "Spot", remove() { doc.spots.splice(doc.spots.indexOf(this), 1); } })), {
      add() { const s = { name: "", typename: "Spot", remove() { doc.spots.splice(doc.spots.indexOf(this), 1); } }; doc.spots.push(s); return s; } });
    doc.pageItems = []; doc.pathItems = []; doc.compoundPathItems = []; doc.textFrames = [];
    doc.views = [{ centerPoint: [0, 0], zoom: 1 }];
    doc.selectObjectsOnActiveArtboard = function () {
      const r = doc.artboards[active].artboardRect;
      doc.selection = doc.pageItems.filter(it => it.visibleBounds[0] >= r[0] - 1e-9 && it.visibleBounds[2] <= r[2] + 1e-9);
    };
    doc.saveAs = function (f, o) { fs.writeFileSync(f.fsName, "%PDF-mock"); doc.saved.push(f.fsName); if (spec.saveAsChangesName) doc.fullName = { fsName: f.fsName }; };
    doc.exportFile = function (f, t, o) { fs.writeFileSync(f.fsName, "PNG"); doc.exported.push([f.fsName, o.horizontalScale]); };
    doc.close = function () { doc.closed = true; if (g.app.documents.indexOf(doc) >= 0) g.app.documents.splice(g.app.documents.indexOf(doc), 1); };
    doc.addItem = function (o) { const it = makeItem(o); doc.pageItems.push(it); if (it.typename === "TextFrame") doc.textFrames.push(it); else doc.pathItems.push(it); return it; };
    return doc;
  }

  const docs = [];
  g.app = { version: opts.version || "29.0", documents: docs, coordinateSystem: "ab", clipboard: null,
    get activeDocument() { return this._active; }, set activeDocument(d) { this._active = d; },
    copy() { this.clipboard = this.activeDocument.selection ? this.activeDocument.selection.slice() : []; log.push("copy"); },
    executeMenuCommand(c) { log.push("menu:" + c); const d = this.activeDocument; if (c === "pasteFront") { d.selection = (this.clipboard || []).map(it => makeItem({ ...it, visibleBounds: it.visibleBounds.slice() })); } },
    documentsAdd(spec) { const d = makeDoc(spec); docs.push(d); this._active = d; return d; } };
  g.app.documents.add = function (space, w, h) { const d = makeDoc({ name: "Sin título", fullName: null, artboards: [{ name: "Mesa 1", rect: [0, h, w, 0] }] }); d.fullName = { fsName: "" }; docs.push(d); g.app._active = d; d.isTemp = true; return d; };
  g.Object.defineProperty ? 0 : 0;

  function open(spec) { const d = makeDoc(spec); docs.push(d); g.app._active = d; return d; }

  const ctx = vm.createContext(g);
  const hostDir = path.join(__dirname, "..", "..", "cep", "host");
  function load(file) { const src = fs.readFileSync(path.join(hostDir, file), "utf8").split("\n").filter(l => !/^#include/.test(l)).join("\n"); vm.runInContext(src, ctx, { filename: file }); }
  load("fv_geom.jsx");
  load("fv_host.jsx");
  return { ctx, g, open, tempRoot, log, dispatch: (n, a) => JSON.parse(vm.runInContext(`FV.dispatch(${JSON.stringify(n)}, ${JSON.stringify(a === undefined ? "" : JSON.stringify(a))})`, ctx)), run: code => vm.runInContext(code, ctx) };
}

module.exports = { makeEnv };
