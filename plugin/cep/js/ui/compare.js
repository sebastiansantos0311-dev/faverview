/* Pestaña Comparar (P6): arte del cliente contra la mesa actual; marcadores en las diferencias. */
(function (g) {
  "use strict";
  var FVP = g.FVP, el = FVP.ui.el, t = FVP.t;
  var COLORES = { text: [230, 30, 30], spelling: [230, 190, 0], color: [240, 120, 0], visual: [40, 110, 240], font: [160, 60, 200] };

  FVP.ui.comparar = {
    id: "comparar",
    mount: function (root) {
      var arte = null, busy = el("div", {}), nombre = el("div", { class: "hint" }), resumen = el("div", { class: "info" }), lista = el("div", { class: "lista" });
      var mesaActual = 0, difs = [];

      function elegir() {
        var ruta = FVP.files.openDialog(t("cmp.elegir"), ["jpg", "jpeg", "png", "tif", "tiff", "pdf", "webp", "bmp"]);
        if (!ruta) { return; }
        var ext = (ruta.split(".").pop() || "").toLowerCase();
        arte = { blob: FVP.files.readBlob(ruta, ext === "pdf" ? "application/pdf" : "image/" + (ext === "jpg" ? "jpeg" : ext)), nombre: ruta.split(/[\\/]/).pop() };
        nombre.textContent = arte.nombre;
      }

      g.document.addEventListener("paste", function (ev) {
        var items = (ev.clipboardData && ev.clipboardData.items) || [], i;
        for (i = 0; i < items.length; i++) {
          if (items[i].type.indexOf("image/") === 0) {
            var b = items[i].getAsFile();
            if (b) { arte = { blob: b, nombre: "pegado.png" }; nombre.textContent = t("cmp.pegado"); ev.preventDefault(); }
          }
        }
      });

      function comparar() {
        if (!arte) { FVP.ui.toast(t("cmp.sin_arte"), "info"); return; }
        FVP.ui.mesas(false).then(function (m) {
          mesaActual = m[0];
          return FVP.ui.exportMesa(mesaActual);
        }).then(function (exp) {
          return FVP.ui.run(busy, function (progreso, ctl) {
            return FVP.api.postForm("/api/plugin/comparar", {}, { arte: { blob: arte.blob, nombre: arte.nombre }, mesa: { blob: FVP.files.readBlob(exp.ruta, "application/pdf"), nombre: "mesa.pdf" } })
              .then(function (r) { return FVP.api.pollJob(r.job_id, progreso, ctl); });
          });
        }).then(function (res) {
          difs = res.diferencias;
          resumen.textContent = t("cmp.similitud", { pct: (res.puntajes.total * 100).toFixed(1) }) + " · " + res.estado;
          lista.innerHTML = "";
          if (!difs.length) { lista.appendChild(el("p", { class: "hint" }, t("cmp.sin_dif"))); return null; }
          difs.forEach(function (d, i) {
            lista.appendChild(el("div", { class: "hallazgo " + (d.severidad === "alta" ? "error" : "advertencia"), onclick: function () {
              FVP.host.call("zoomTo", { bbox: d.bbox_pt, mesa: mesaActual, margen: 40 }).then(function () { return FVP.host.call("selectInBBox", { bbox: d.bbox_pt, mesa: mesaActual }); });
            } }, el("b", {}, (i + 1) + ". " + d.categoria), " — " + d.mensaje));
          });
          return FVP.host.call("markers", { mesa: mesaActual, lista: difs.map(function (d, i) { return { bbox: d.bbox_pt, id: i + 1, etiqueta: String(i + 1), color: COLORES[d.categoria] || [230, 30, 30] }; }) });
        }).catch(function (e) { if (!/cancel/i.test(e.message)) { FVP.ui.toast(e.message, "error"); } });
      }

      root.appendChild(el("div", { class: "seccion" }, el("h2", {}, t("cmp.titulo")),
        el("div", { class: "botones" }, el("button", { class: "sec", onclick: elegir }, t("cmp.elegir")), el("span", { class: "hint" }, t("cmp.pegar") + " (Ctrl+V)")),
        nombre, el("div", { class: "botones" }, el("button", { onclick: comparar }, t("cmp.comparar")),
          el("button", { class: "sec", onclick: function () { FVP.host.openURL(FVP.api.state.base + "/#/comparar"); } }, t("cmp.ver"))),
        busy, resumen, lista));
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
