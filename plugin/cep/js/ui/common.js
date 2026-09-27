/* Utilidades de interfaz compartidas por las pestañas: elementos, avisos, operaciones con progreso y cancelación, flujos comunes. */
(function (g) {
  "use strict";
  var FVP = g.FVP = g.FVP || {};
  FVP.ui = FVP.ui || {};
  var t = function (k, p) { return FVP.t(k, p); };

  /** el("div", {class:"x", onclick: fn}, "texto", [hijos]) */
  FVP.ui.el = function (tag, attrs) {
    var e = g.document.createElement(tag), i, k, kids = Array.prototype.slice.call(arguments, 2);
    for (k in (attrs || {})) {
      if (!attrs.hasOwnProperty(k) || attrs[k] === null || attrs[k] === undefined || attrs[k] === false) { continue; }
      if (k === "class") { e.className = attrs[k]; }
      else if (k.slice(0, 2) === "on") { e.addEventListener(k.slice(2), attrs[k]); }
      else if (k === "value") { e.value = attrs[k]; }
      else if (k === "checked") { e.checked = !!attrs[k]; }
      else { e.setAttribute(k, attrs[k] === true ? "" : attrs[k]); }
    }
    (function add(list) {
      for (i = 0; i < list.length; i++) {
        var c = list[i];
        if (c === null || c === undefined || c === false) { continue; }
        if (Array.isArray(c)) { add(c); } else { e.appendChild(c && c.nodeType ? c : g.document.createTextNode(String(c))); }
      }
    }(kids));
    return e;
  };
  var el = FVP.ui.el;

  FVP.ui.toast = function (msg, kind) {
    var box = g.document.getElementById("avisos");
    if (!box) { return; }
    var n = el("div", { class: "aviso " + (kind || "info") }, msg);
    box.appendChild(n);
    setTimeout(function () { if (n.parentNode) { n.parentNode.removeChild(n); } }, kind === "error" ? 9000 : 4500);
  };

  /** ejecuta `fn(progreso, ctl)` mostrando barra de progreso y botón Cancelar dentro de `box`; devuelve la promesa de fn */
  FVP.ui.run = function (box, fn) {
    var ctl = { cancelado: false };
    var bar = el("div", { class: "barra" }, el("i", {})), msg = el("span", { class: "msg" }, t("comun.procesando"));
    var cancel = el("button", { class: "sec", onclick: function () { ctl.cancelado = true; cancel.disabled = true; } }, t("comun.cancelar"));
    var wrap = el("div", { class: "progreso" }, msg, bar, cancel);
    box.appendChild(wrap);
    function progreso(m, p) { if (m) { msg.textContent = m; } bar.firstChild.style.width = Math.round((p || 0) * 100) + "%"; }
    return Promise.resolve().then(function () { return fn(progreso, ctl); }).then(function (r) {
      if (wrap.parentNode) { wrap.parentNode.removeChild(wrap); }
      return r;
    }, function (e) {
      if (wrap.parentNode) { wrap.parentNode.removeChild(wrap); }
      FVP.ui.toast(ctl.cancelado ? t("comun.cancelado") : t("comun.error", { mensaje: e.message }), ctl.cancelado ? "info" : "error");
      throw e;
    });
  };

  /** exporta una mesa (o la actual) a PDF y devuelve {ruta, tamano_pt, artboardRect, mesa, ...} */
  FVP.ui.exportMesa = function (mesa) {
    return FVP.host.call("exportArtboardPDF", { artboard: mesa, preset: FVP.settings.preset }, 120000);
  };

  /** sube la mesa exportada al endpoint del plugin y espera el trabajo */
  FVP.ui.subirMesa = function (endpoint, campo, exp, campos, progreso, ctl) {
    return FVP.api.uploadFile(endpoint, campo, exp.ruta, campos, "application/pdf").then(function (r) {
      return FVP.api.pollJob(r.job_id, progreso, ctl);
    });
  };

  FVP.ui.tempPath = function (nombre) { return FVP.state.tempPath + "/" + nombre; };

  /** descarga el archivo de un trabajo del plugin a temporales y devuelve la ruta local */
  FVP.ui.bajarArchivo = function (url, nombre) {
    var dest = FVP.ui.tempPath(Date.now() + "_" + nombre);
    return FVP.api.downloadToFile(url, dest).then(function () { return dest; });
  };

  /** lista de mesas para revisar: [actual] o todas */
  FVP.ui.mesas = function (todas) {
    return FVP.host.call("docInfo", {}).then(function (info) {
      if (todas) { return info.mesas.map(function (m) { return m.index; }); }
      return FVP.host.call("ping", {}).then(function (p) { return [p.mesaActiva || 0]; });
    });
  };

  FVP.ui.tabla = function (rows) {
    var tb = el("table", { class: "tabla" });
    rows.forEach(function (r) { tb.appendChild(el("tr", {}, r.map(function (c) { return el("td", {}, c); }))); });
    return tb;
  };

  FVP.settings = { preset: "[PDF/X-4:2008]" };
  FVP.state = FVP.state || { tempPath: "" };
}(typeof window !== "undefined" ? window : globalThis));
