/* HostAdapter: ÚNICA forma de hablar con ExtendScript (CSInterface.evalScript). El resto del panel no toca APIs de CEP.
 * Diseño listo para UXP: al migrar, solo se reemplazan este archivo y files.js. */
(function (g) {
  "use strict";
  var FVP = g.FVP = g.FVP || {};
  var cs = null;

  function getCS() {
    if (FVP.host._cs) { return FVP.host._cs; }
    if (!cs) { cs = new g.CSInterface(); }
    return cs;
  }

  FVP.host = {
    _cs: null,                     // inyectable en pruebas
    timeoutMs: 60000,
    /** await FVP.host.call("exportArtboardPDF", {artboard: 0}) → data (o lanza Error con el mensaje en español) */
    call: function (name, args, timeoutMs) {
      return new Promise(function (resolve, reject) {
        var done = false;
        var timer = setTimeout(function () {
          if (!done) { done = true; reject(new Error("Illustrator no respondió a tiempo (" + name + ").")); }
        }, timeoutMs || FVP.host.timeoutMs);
        var script = "FV.dispatch(" + JSON.stringify(name) + "," + JSON.stringify(JSON.stringify(args || {})) + ")";
        try {
          getCS().evalScript(script, function (raw) {
            if (done) { return; }
            done = true; clearTimeout(timer);
            if (raw === undefined || raw === null || raw === "" || raw === "undefined") { reject(new Error("Illustrator no devolvió respuesta. ¿El panel se cargó bien?")); return; }
            if (raw === "EvalScript error.") { reject(new Error("No se pudo ejecutar la operación en Illustrator.")); return; }
            var res;
            try { res = JSON.parse(raw); } catch (e) { reject(new Error("Respuesta no válida de Illustrator.")); return; }
            if (res.ok) { resolve(res.data); } else { reject(new Error(res.error || "Error en Illustrator.")); }
          });
        } catch (e2) {
          if (!done) { done = true; clearTimeout(timer); reject(e2); }
        }
      });
    },
    hostEnvironment: function () { return getCS().getHostEnvironment(); },
    systemPath: function (which) { return getCS().getSystemPath(which); },
    addEventListener: function (type, fn) { getCS().addEventListener(type, fn); },
    openURL: function (url) { getCS().openURLInDefaultBrowser(url); }
  };
}(typeof window !== "undefined" ? window : globalThis));
