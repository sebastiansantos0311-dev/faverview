/* FAVERVIEW - geometria (ExtendScript ES3, sin dependencias de la API de Illustrator: se prueba fuera de Illustrator).
 *
 * Convenciones:
 *  - "pdf": puntos PDF de la mesa exportada, [x0, y0, x1, y1], origen ABAJO-izquierda.
 *  - "doc": coordenadas de documento de Illustrator en el sistema de scripting, [izq, arriba, der, abajo], el eje Y crece hacia ARRIBA.
 *  - artboardRect de Illustrator: [izq, arriba, der, abajo] en coordenadas de documento (arriba > abajo).
 *  - origin: desplazamiento [ox, oy] del origen de regla respecto del origen de scripting (por defecto [0, 0]). */
var FV = (typeof FV === "undefined") ? {} : FV;

FV.geom = {
  norm: function (r) {   // ordena [x0,y0,x1,y1] de menor a mayor
    return [Math.min(r[0], r[2]), Math.min(r[1], r[3]), Math.max(r[0], r[2]), Math.max(r[1], r[3])];
  },

  /** bbox pdf [x0,y0,x1,y1] -> limites de documento [izq, arriba, der, abajo] */
  pdfToDoc: function (bbox, artboardRect, origin) {
    var b = FV.geom.norm(bbox), ox = origin ? origin[0] : 0, oy = origin ? origin[1] : 0;
    var left = artboardRect[0], bottom = Math.min(artboardRect[1], artboardRect[3]);
    return [left + b[0] - ox, bottom + b[3] - oy, left + b[2] - ox, bottom + b[1] - oy];
  },

  /** limites de documento [izq, arriba, der, abajo] -> bbox pdf [x0,y0,x1,y1] */
  docToPdf: function (docRect, artboardRect, origin) {
    var ox = origin ? origin[0] : 0, oy = origin ? origin[1] : 0;
    var left = artboardRect[0], bottom = Math.min(artboardRect[1], artboardRect[3]);
    return [docRect[0] + ox - left, docRect[3] + oy - bottom, docRect[2] + ox - left, docRect[1] + oy - bottom];
  },

  /** se cruzan dos rectangulos de documento [izq, arriba, der, abajo]? */
  intersects: function (a, b) {
    return !(a[2] < b[0] || b[2] < a[0] || a[1] < b[3] || b[1] < a[3]);
  },

  center: function (docRect) {
    return [(docRect[0] + docRect[2]) / 2, (docRect[1] + docRect[3]) / 2];
  },

  /** zoom (1 = 100 %) para que el rectangulo + margen quepa en una ventana de `view` [ancho, alto] puntos de pantalla */
  fitZoom: function (docRect, view, margin) {
    var m = margin || 0, w = Math.abs(docRect[2] - docRect[0]) + 2 * m, h = Math.abs(docRect[1] - docRect[3]) + 2 * m;
    if (w <= 0 || h <= 0) { return 1; }
    var z = Math.min(view[0] / w, view[1] / h);
    return Math.max(0.01, Math.min(64, z));
  },

  /** rectangulo -> [x, y, ancho, alto] con y de la esquina superior (para `pathItems.rectangle`) */
  toRectArgs: function (docRect) {
    return [docRect[0], docRect[1], Math.abs(docRect[2] - docRect[0]), Math.abs(docRect[1] - docRect[3])];
  },

  /** artboardRect -> tamano [ancho, alto] en puntos */
  size: function (artboardRect) {
    return [Math.abs(artboardRect[2] - artboardRect[0]), Math.abs(artboardRect[1] - artboardRect[3])];
  }
};

/** normaliza el nombre de una tinta igual que core/inks.normalize_name (PANTONE/PMS/P unificados, sufijos C/U/M/CP/UP separados) */
FV.normName = function (name) {
  var n = String(name === undefined || name === null ? "" : name).replace(/\u00ae/g, "").replace(/^\s+|\s+$/g, "").replace(/\s+/g, " ").toUpperCase();
  n = n.replace(/^(?:PANTONE|PMS|P)\s*[-_ ]?(?=\d)/, "PANTONE ");
  n = n.replace(/(\d)\s*(CP|UP|C|U|M)$/, "$1 $2");
  return n.replace(/\s+/g, " ").replace(/^\s+|\s+$/g, "");
};
