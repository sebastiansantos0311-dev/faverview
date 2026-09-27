/* FAVERVIEW - capa host de Illustrator (ExtendScript ES3).
 *
 * Hace SOLO lo que exige la API de Illustrator (exportar, colocar, seleccionar, crear muestras, zoom, marcar). Toda la logica
 * de imagen, color, vectorizacion, preflight, separacion y trapping vive en el servidor de FAVERVIEW.
 *
 * Contrato: cada funcion FV.handlers.<nombre>(args) recibe un objeto y devuelve datos; FV.dispatch(nombre, json) las llama con
 * try/catch y responde SIEMPRE una cadena JSON {"ok":true,"data":...} o {"ok":false,"error":"mensaje en espanol"}.
 * Las funciones son cortas: Illustrator se bloquea mientras corre ExtendScript. Cada llamada es una sola operacion (un Ctrl+Z). */
#include "json2.js"
#include "fv_geom.jsx"

var FV = (typeof FV === "undefined") ? {} : FV;
FV.VERSION = "3.2.1";
FV.LAYER_REVIEW = "FAVERVIEW \u2013 Revisi\u00f3n";
FV.LAYER_VECTOR = "FAVERVIEW \u2013 Vector";
FV.LAYER_TRAPS = "FAVERVIEW \u2013 Traps";
FV.MAX_ITEMS = 20000;

FV.ok = function (data) { return JSON.stringify({ ok: true, data: data === undefined ? null : data }); };
FV.fail = function (msg) { return JSON.stringify({ ok: false, error: String(msg) }); };

FV.uuid = function () {
  var s = "", i;
  for (i = 0; i < 16; i++) { s += Math.floor(Math.random() * 16).toString(16); }
  return s;
};

FV.tempDir = function () {
  var d = new Folder(Folder.temp.fsName + "/FAVERVIEW");
  if (!d.exists) { d.create(); }
  return d;
};

FV.needDoc = function () {
  if (app.documents.length === 0) { throw "Abre un documento en Illustrator."; }
  return app.activeDocument;
};

FV.artboard = function (doc, idx) {
  var i = (idx === undefined || idx === null) ? doc.artboards.getActiveArtboardIndex() : idx;
  if (i < 0 || i >= doc.artboards.length) { throw "Esa mesa de trabajo no existe."; }
  return { index: i, ab: doc.artboards[i], rect: doc.artboards[i].artboardRect };
};

FV.origin = function (doc) {
  try { var o = doc.rulerOrigin; return [o[0], o[1]]; } catch (e) { return [0, 0]; }
};

/** ejecuta `fn` con el sistema de coordenadas de documento y lo restaura al terminar */
FV.withDocCoords = function (fn) {
  var prev = null;
  try { prev = app.coordinateSystem; app.coordinateSystem = CoordinateSystem.DOCUMENTCOORDINATESYSTEM; } catch (e) {}
  try { return fn(); } finally { try { if (prev !== null) { app.coordinateSystem = prev; } } catch (e2) {} }
};

FV.layer = function (doc, name, create) {
  var i;
  for (i = 0; i < doc.layers.length; i++) { if (doc.layers[i].name === name) { return doc.layers[i]; } }
  if (!create) { return null; }
  var l = doc.layers.add();
  l.name = name;
  return l;
};

FV.spotByNorm = function (doc, name) {
  var target = FV.normName(name), i;
  for (i = 0; i < doc.spots.length; i++) { if (FV.normName(doc.spots[i].name) === target) { return doc.spots[i]; } }
  return null;
};

FV.spotByExact = function (doc, name) {
  var i;
  for (i = 0; i < doc.spots.length; i++) { if (doc.spots[i].name === name) { return doc.spots[i]; } }
  return null;
};

FV.cmykColor = function (c) {
  var k = new CMYKColor();
  k.cyan = c[0]; k.magenta = c[1]; k.yellow = c[2]; k.black = c[3];
  return k;
};

FV.handlers = {};
var H = FV.handlers;

/* ------------------------------------------------------------------ informacion */
H.ping = function () {
  var has = app.documents.length > 0, doc = has ? app.activeDocument : null, out = {
    illustrator: app.version, doc: has, tempPath: FV.tempDir().fsName, hostVersion: FV.VERSION
  };
  if (has) {
    out.nombreDoc = doc.name;
    out.mesas = doc.artboards.length;
    out.mesaActiva = doc.artboards.getActiveArtboardIndex();
    try { out.unidades = String(doc.rulerUnits); } catch (e) { out.unidades = ""; }
  }
  return out;
};

H.docInfo = function () {
  var doc = FV.needDoc(), list = [], i, spots = [];
  for (i = 0; i < doc.artboards.length; i++) {
    list.push({ index: i, name: doc.artboards[i].name, rect: doc.artboards[i].artboardRect, size: FV.geom.size(doc.artboards[i].artboardRect) });
  }
  for (i = 0; i < doc.spots.length; i++) {
    var s = doc.spots[i];
    if (s.name !== "[Registration]" && s.name !== "[None]") { spots.push(s.name); }
  }
  return { nombre: doc.name, mesas: list, rulerOrigin: FV.origin(doc), muestras: spots };
};

H.listSpots = function () {
  var doc = FV.needDoc(), out = [], i;
  for (i = 0; i < doc.spots.length; i++) { out.push(doc.spots[i].name); }
  return out;
};

/* ------------------------------------------------------------------ exportar */
/** copia el contenido de la mesa a un documento temporal y lo guarda como PDF; el documento del usuario no se toca */
H.exportArtboardPDF = function (a) {
  var doc = FV.needDoc(), info = FV.artboard(doc, a.artboard), size = FV.geom.size(info.rect);
  var file = new File(FV.tempDir().fsName + "/" + FV.uuid() + ".pdf");
  var fullBefore = "";
  try { fullBefore = doc.fullName.fsName; } catch (e) { fullBefore = ""; }
  doc.artboards.setActiveArtboardIndex(info.index);
  var prevSel = doc.selection;
  doc.selectObjectsOnActiveArtboard();
  if (!doc.selection || doc.selection.length === 0) { throw "La mesa de trabajo est\u00e1 vac\u00eda."; }
  app.copy();
  var tmp = app.documents.add(doc.documentColorSpace, size[0], size[1]);
  try {
    app.executeMenuCommand("pasteFront");
    var dx = -info.rect[0], dy = -Math.min(info.rect[1], info.rect[3]), i, sel = tmp.selection;
    for (i = 0; i < sel.length; i++) { sel[i].translate(dx, dy); }
    var opts = new PDFSaveOptions();
    try { opts.pDFPreset = a.preset || "[PDF/X-4:2008]"; } catch (e1) { opts.pDFPreset = "[Press Quality]"; }
    opts.viewAfterSaving = false;
    tmp.saveAs(file, opts);
  } finally {
    tmp.close(SaveOptions.DONOTSAVECHANGES);
    app.activeDocument = doc;
  }
  var fullAfter = "";
  try { fullAfter = doc.fullName.fsName; } catch (e2) { fullAfter = ""; }
  if (fullBefore !== fullAfter) { throw "El documento activo cambi\u00f3 de archivo durante la exportaci\u00f3n."; }
  try { doc.selection = prevSel; } catch (e3) {}
  return { ruta: file.fsName, tamano_pt: size, artboardRect: info.rect, rulerOrigin: FV.origin(doc), mesa: info.index, nombreMesa: info.ab.name };
};

H.exportSelectionPNG = function (a) {
  var doc = FV.needDoc(), sel = doc.selection;
  if (!sel || sel.length === 0) { throw "Selecciona una imagen."; }
  var it = sel[0];
  if (it.typename === "PlacedItem" && it.file && !a.forzarExportar) {          // vinculada: el original tiene mejor calidad
    return { tipo: "vinculada", ruta: it.file.fsName, bounds: it.geometricBounds, matriz: FV.matrixOf(it), rotacion: FV.rotationOf(it) };
  }
  var ppi = a.ppi || 300, file = new File(FV.tempDir().fsName + "/" + FV.uuid() + ".png");
  var tmp = app.documents.add(doc.documentColorSpace, Math.abs(it.width), Math.abs(it.height));
  try {
    app.activeDocument = doc; app.copy(); app.activeDocument = tmp; app.executeMenuCommand("pasteFront");
    var o = new ExportOptionsPNG24();
    o.transparency = true; o.antiAliasing = true; o.horizontalScale = ppi / 72 * 100; o.verticalScale = ppi / 72 * 100;
    tmp.exportFile(file, ExportType.PNG24, o);
  } finally { tmp.close(SaveOptions.DONOTSAVECHANGES); app.activeDocument = doc; }
  return { tipo: "incrustada", ruta: file.fsName, bounds: it.geometricBounds, matriz: FV.matrixOf(it), rotacion: FV.rotationOf(it), ppi: ppi };
};

H.exportSelectionPDF = function () {
  var doc = FV.needDoc(), sel = doc.selection;
  if (!sel || sel.length === 0) { throw "Selecciona uno o m\u00e1s objetos."; }
  var b = FV.selectionBounds(sel), w = b[2] - b[0], h = b[1] - b[3];
  var file = new File(FV.tempDir().fsName + "/" + FV.uuid() + ".pdf");
  app.copy();
  var tmp = app.documents.add(doc.documentColorSpace, w, h);
  try {
    app.executeMenuCommand("pasteFront");
    var i, s2 = tmp.selection;
    for (i = 0; i < s2.length; i++) { s2[i].translate(-b[0], -b[3]); }
    var opts = new PDFSaveOptions();
    try { opts.pDFPreset = "[PDF/X-4:2008]"; } catch (e) { opts.pDFPreset = "[Press Quality]"; }
    opts.viewAfterSaving = false;
    tmp.saveAs(file, opts);
  } finally { tmp.close(SaveOptions.DONOTSAVECHANGES); app.activeDocument = doc; }
  return { ruta: file.fsName, tamano_pt: [w, h], bounds: b };
};

FV.selectionBounds = function (sel) {
  var i, l = 1e9, t = -1e9, r = -1e9, b = 1e9, v;
  for (i = 0; i < sel.length; i++) {
    v = sel[i].visibleBounds;
    l = Math.min(l, v[0]); t = Math.max(t, v[1]); r = Math.max(r, v[2]); b = Math.min(b, v[3]);
  }
  return [l, t, r, b];
};

FV.matrixOf = function (it) {
  try { var m = it.matrix; return [m.mValueA, m.mValueB, m.mValueC, m.mValueD, m.mValueTX, m.mValueTY]; } catch (e) { return null; }
};

FV.rotationOf = function (it) {
  var m = FV.matrixOf(it);
  if (!m) { return 0; }
  return Math.atan2(m[1], m[0]) * 180 / Math.PI;
};

/* ------------------------------------------------------------------ traer a Illustrator */
/** crea o reutiliza una muestra spot por nombre normalizado (sin duplicar) */
H.ensureSpot = function (a) {
  var doc = FV.needDoc(), found = FV.spotByNorm(doc, a.nombre);
  if (found) { return { nombre: found.name, creada: false }; }
  var spot = doc.spots.add();
  spot.name = a.nombre;
  spot.colorType = ColorModel.SPOT;
  if (a.lab) {
    var lab = new LabColor();
    lab.l = a.lab[0]; lab.a = a.lab[1]; lab.b = a.lab[2];
    spot.color = lab;
  } else {
    spot.color = FV.cmykColor(a.cmyk || [0, 0, 0, 100]);
  }
  return { nombre: spot.name, creada: true };
};

/** coloca un PDF como grupo de vectores en coordenadas de documento; recrea como spot las tintas que llegaron como proceso */
H.placePDF = function (a) {
  var doc = FV.needDoc();
  return FV.withDocCoords(function () {
    var layer = FV.layer(doc, a.capa || FV.LAYER_VECTOR, true), i;
    layer.locked = false;
    var g = layer.groupItems.createFromFile(new File(a.ruta));
    var b = g.geometricBounds, w = b[2] - b[0], h = b[1] - b[3];
    if (a.ancho && a.alto && w > 0 && h > 0) {
      g.resize(a.ancho / w * 100, a.alto / h * 100, true, true, true, true, 100, Transformation.TOPLEFT);
    }
    if (a.rotacion) { g.rotate(-a.rotacion, true, true, true, true, Transformation.CENTER); }
    if (a.x !== undefined && a.y !== undefined) { g.position = [a.x, a.y]; }
    g.name = a.nombre || "FAVERVIEW";
    var spots = [];
    if (a.tintas) { for (i = 0; i < a.tintas.length; i++) { spots.push(H.ensureSpot(a.tintas[i])); } }
    return { nombre: g.name, bounds: g.geometricBounds, capa: layer.name, muestras: spots };
  });
};

/** coloca un PDF exactamente encima del objeto seleccionado (misma posicion, tamano y rotacion) */
H.placeOverSelection = function (a) {
  var doc = FV.needDoc(), sel = doc.selection;
  if (!sel || sel.length === 0) { throw "Selecciona la imagen sobre la que colocar el vector."; }
  var it = sel[0], b = it.geometricBounds, rot = FV.rotationOf(it);
  var res = H.placePDF({ ruta: a.ruta, capa: a.capa || FV.LAYER_VECTOR, nombre: a.nombre, tintas: a.tintas,
                          ancho: Math.abs(b[2] - b[0]), alto: Math.abs(b[1] - b[3]), x: b[0], y: b[1] });
  if (a.ocultarOriginal) { it.hidden = true; }
  return res;
};

/** inserta un PDF (codigo de barras, braille) en el centro de la vista o de la seleccion */
H.insertPDF = function (a) {
  var doc = FV.needDoc(), c, sel = doc.selection;
  if (sel && sel.length > 0) { c = FV.geom.center(FV.selectionBounds(sel)); } else { c = doc.views[0].centerPoint; }
  var ancho = a.ancho_pt, alto = a.alto_pt;
  return H.placePDF({ ruta: a.ruta, capa: a.capa || "FAVERVIEW", nombre: a.nombre, tintas: a.tintas, ancho: ancho, alto: alto,
                       x: c[0] - (ancho || 0) / 2, y: c[1] + (alto || 0) / 2 });
};

/* ------------------------------------------------------------------ navegacion */
H.zoomTo = function (a) {
  var doc = FV.needDoc(), info = FV.artboard(doc, a.mesa), d = FV.geom.pdfToDoc(a.bbox, info.rect, a.origin || FV.origin(doc));
  var v = doc.views[0], c = FV.geom.center(d);
  v.centerPoint = c;
  var view = a.view || [800, 600];
  v.zoom = FV.geom.fitZoom(d, view, a.margen === undefined ? 30 : a.margen);
  return { centro: c, zoom: v.zoom };
};

H.selectInBBox = function (a) {
  var doc = FV.needDoc(), info = FV.artboard(doc, a.mesa), d = FV.geom.pdfToDoc(a.bbox, info.rect, a.origin || FV.origin(doc));
  var items = doc.pageItems, n = items.length, limit = a.limite || FV.MAX_ITEMS, hits = [], i, it, truncated = false;
  doc.selection = null;
  for (i = 0; i < n; i++) {
    if (i >= limit) { truncated = true; break; }
    it = items[i];
    if (it.locked || it.hidden) { continue; }
    try { if (it.layer && (it.layer.locked || !it.layer.visible)) { continue; } } catch (e) {}
    if (FV.geom.intersects(it.visibleBounds, d)) { hits.push(it); }
  }
  for (i = 0; i < hits.length; i++) { hits[i].selected = true; }
  return { seleccionados: hits.length, recorridos: Math.min(n, limit), truncado: truncated, aviso: truncated ? "Documento muy grande: solo se revisaron " + limit + " objetos." : null };
};

/** marcadores (rectangulos sin relleno y etiqueta numerada) en una capa bloqueada que no se imprime */
H.markers = function (a) {
  var doc = FV.needDoc(), info = FV.artboard(doc, a.mesa);
  return FV.withDocCoords(function () {
    var layer = FV.layer(doc, FV.LAYER_REVIEW, true), list = a.lista || [], i, n = 0, origin = a.origin || FV.origin(doc);
    layer.locked = false; layer.visible = true;
    for (i = 0; i < list.length; i++) {
      var m = list[i], d = FV.geom.pdfToDoc(m.bbox, info.rect, origin), r = FV.geom.toRectArgs(d);
      var p = layer.pathItems.rectangle(r[1], r[0], r[2], r[3]);
      p.filled = false; p.stroked = true; p.strokeWidth = m.grosor || 1.5;
      var c = new RGBColor(); c.red = (m.color || [230, 30, 30])[0]; c.green = (m.color || [230, 30, 30])[1]; c.blue = (m.color || [230, 30, 30])[2];
      p.strokeColor = c;
      p.name = "FV-" + (m.id !== undefined ? m.id : i + 1);
      var t = layer.textFrames.add();
      t.contents = String(m.etiqueta !== undefined ? m.etiqueta : (i + 1));
      t.position = [d[0], d[1] + 12];
      t.textRange.characterAttributes.fillColor = c;
      n++;
    }
    layer.printable = false;
    layer.locked = true;
    return { creados: n, capa: layer.name };
  });
};

H.clearMarkers = function () {
  var doc = FV.needDoc(), layer = FV.layer(doc, FV.LAYER_REVIEW, false);
  if (!layer) { return { borrada: false }; }
  layer.locked = false;
  layer.remove();
  return { borrada: true };
};

H.hideLayer = function (a) {
  var doc = FV.needDoc(), l = FV.layer(doc, a.capa, false);
  if (l) { l.visible = !a.ocultar ? true : false; }
  return { ok: !!l };
};

/* ------------------------------------------------------------------ correcciones nativas (P4) */
FV.eachPaintedItem = function (doc, fn) {
  var i, n = 0, coll = [doc.pathItems, doc.compoundPathItems, doc.textFrames], c, k;
  for (c = 0; c < coll.length; c++) {
    for (k = 0; k < coll[c].length; k++) {
      if (n++ > FV.MAX_ITEMS) { return; }
      fn(coll[c][k]);
    }
  }
};

FV.spotOf = function (color) {
  try { if (color && color.typename === "SpotColor") { return color.spot; } } catch (e) {}
  return null;
};

/** sobreimpresion en objetos que usan tintas tecnicas (lista de nombres) o negro 100 % K. `soloContar`: no modifica */
H.fixOverprint = function (a) {
  var doc = FV.needDoc(), names = {}, i, count = 0;
  for (i = 0; i < (a.tintas || []).length; i++) { names[FV.normName(a.tintas[i])] = true; }
  FV.eachPaintedItem(doc, function (it) {
    var touched = false, sp;
    try {
      if (it.typename === "TextFrame") {
        sp = FV.spotOf(it.textRange.characterAttributes.fillColor);
        if (sp && names[FV.normName(sp.name)]) { if (!a.soloContar) { it.textRange.characterAttributes.overprintFill = true; } touched = true; }
      } else {
        if (it.filled) { sp = FV.spotOf(it.fillColor); if (sp && names[FV.normName(sp.name)]) { if (!a.soloContar) { it.fillOverprint = true; } touched = true; } }
        if (it.stroked) { sp = FV.spotOf(it.strokeColor); if (sp && names[FV.normName(sp.name)]) { if (!a.soloContar) { it.strokeOverprint = true; } touched = true; } }
      }
    } catch (e) {}
    if (touched) { count++; }
  });
  return { objetos: count, aplicado: !a.soloContar };
};

/** texto negro pequeno: de negro enriquecido a K 100 % con sobreimpresion (solo textos menores de `maxPt`) */
H.fixBlackText = function (a) {
  var doc = FV.needDoc(), count = 0, maxPt = a.maxPt || 12, i;
  for (i = 0; i < doc.textFrames.length; i++) {
    var tf = doc.textFrames[i], ca;
    try {
      ca = tf.textRange.characterAttributes;
      var col = ca.fillColor;
      if (col.typename === "CMYKColor" && col.black > 85 && (col.cyan + col.magenta + col.yellow) > 30 && ca.size < maxPt) {
        if (!a.soloContar) {
          var k = new CMYKColor(); k.cyan = 0; k.magenta = 0; k.yellow = 0; k.black = 100;
          ca.fillColor = k; ca.overprintFill = true;
        }
        count++;
      }
    } catch (e) {}
  }
  return { objetos: count, aplicado: !a.soloContar };
};

/** unir muestras spot duplicadas: `mapa` = { "nombre duplicado": "nombre canonico" } */
H.mergeSpots = function (a) {
  var doc = FV.needDoc(), map = a.mapa || {}, count = 0, removed = 0, k, dup, canon;
  for (k in map) {
    if (!Object.prototype.hasOwnProperty.call(map, k)) { continue; }
    dup = FV.spotByExact(doc, k) || FV.spotByNorm(doc, k);            // los duplicados suelen diferir solo en may\u00fasculas o espacios
    canon = FV.spotByExact(doc, map[k]) || FV.spotByNorm(doc, map[k]);
    if (!dup || !canon || dup === canon) { continue; }
    FV.eachPaintedItem(doc, function (it) {
      try {
        if (it.typename === "TextFrame") { return; }
        var sp;
        if (it.filled) { sp = FV.spotOf(it.fillColor); if (sp && sp === dup) { if (!a.soloContar) { var f = new SpotColor(); f.spot = canon; f.tint = it.fillColor.tint; it.fillColor = f; } count++; } }
        if (it.stroked) { sp = FV.spotOf(it.strokeColor); if (sp && sp === dup) { if (!a.soloContar) { var s2 = new SpotColor(); s2.spot = canon; s2.tint = it.strokeColor.tint; it.strokeColor = s2; } count++; } }
      } catch (e) {}
    });
    if (!a.soloContar) { try { dup.remove(); removed++; } catch (e2) {} }
  }
  return { objetos: count, muestrasEliminadas: removed, aplicado: !a.soloContar };
};

/** eliminar muestras spot sin uso (lista `nombres` opcional) */
H.removeUnusedSpots = function (a) {
  var doc = FV.needDoc(), used = {}, i, removed = [], want = null;
  if (a.nombres) { want = {}; for (i = 0; i < a.nombres.length; i++) { want[FV.normName(a.nombres[i])] = true; } }
  FV.eachPaintedItem(doc, function (it) {
    try {
      var sp = (it.typename === "TextFrame") ? FV.spotOf(it.textRange.characterAttributes.fillColor) : (it.filled ? FV.spotOf(it.fillColor) : null);
      if (sp) { used[FV.normName(sp.name)] = true; }
      if (it.typename !== "TextFrame" && it.stroked) { sp = FV.spotOf(it.strokeColor); if (sp) { used[FV.normName(sp.name)] = true; } }
    } catch (e) {}
  });
  for (i = doc.spots.length - 1; i >= 0; i--) {
    var s = doc.spots[i], nn = FV.normName(s.name);
    if (s.name === "[Registration]" || s.name === "[None]" || used[nn]) { continue; }
    if (want && !want[nn]) { continue; }
    removed.push(s.name);
    if (!a.soloContar) { try { s.remove(); } catch (e2) {} }
  }
  return { muestras: removed, aplicado: !a.soloContar };
};

/* ------------------------------------------------------------------ despacho */
FV.ALLOWED = ["ping", "docInfo", "listSpots", "exportArtboardPDF", "exportSelectionPNG", "exportSelectionPDF", "ensureSpot", "placePDF",
              "placeOverSelection", "insertPDF", "zoomTo", "selectInBBox", "markers", "clearMarkers", "hideLayer", "fixOverprint",
              "fixBlackText", "mergeSpots", "removeUnusedSpots"];

FV.dispatch = function (name, argsJson) {
  try {
    var ok = false, i;
    for (i = 0; i < FV.ALLOWED.length; i++) { if (FV.ALLOWED[i] === name) { ok = true; } }
    if (!ok) { return FV.fail("Operaci\u00f3n desconocida: " + name); }
    var args = (argsJson === undefined || argsJson === "" || argsJson === null) ? {} : JSON.parse(argsJson);
    return FV.ok(FV.handlers[name](args));
  } catch (e) {
    return FV.fail((e && e.message) ? e.message : e);
  }
};
