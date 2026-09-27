/* Pestaña Separar (P5): tintas del PDF frente a las muestras del documento, cobertura, TAC, placas y exportación. */
(function (g) {
  "use strict";
  var FVP = g.FVP, el = FVP.ui.el, t = FVP.t;

  FVP.ui.separar = {
    id: "separar",
    mount: function (root) {
      var busy = el("div", {}), tintas = el("div", { class: "lista" }), hall = el("div", { class: "lista" }), tacInfo = el("div", { class: "info" });
      var vista = el("img", { class: "vista hidden", alt: "" }), dens = el("div", { class: "hint" }, t("sep.densitometro"));
      var ctx = null;        // {job, urls, res, mesa, exp}

      function analizar() {
        FVP.ui.mesas(false).then(function (m) {
          var mesa = m[0];
          return FVP.ui.exportMesa(mesa).then(function (exp) {
            return FVP.ui.run(busy, function (progreso, ctl) {
              return FVP.api.uploadFile("/api/plugin/separar", "file", exp.ruta, { dpi: 150 }, "application/pdf").then(function (s) {
                return FVP.api.pollJob(s.analisis_id, progreso, ctl).then(function (res) { return { s: s, res: res }; });
              });
            }).then(function (o) { ctx = { job: o.s.job_id, urls: o.s.urls, res: o.res, mesa: mesa, exp: exp }; return ctx; });
          });
        }).then(pintar).catch(function (e) { if (!/cancel/i.test(e.message)) { FVP.ui.toast(e.message, "error"); } });
      }

      function pintar() {
        return FVP.host.call("listSpots", {}).then(function (spots) {
          var normDoc = {}, pdfNombres = ctx.res.placas.map(function (p) { return p.nombre.replace(/_/g, " "); });
          return FVP.api.postJSON("/api/plugin/tintas/clasificar", { nombres: spots.concat(pdfNombres) }).then(function (c) {
            spots.forEach(function (s) { normDoc[c[s].norm] = s; });
            tintas.innerHTML = "";
            tintas.appendChild(el("h3", {}, t("sep.tintas")));
            ctx.res.placas.forEach(function (p) {
              var n = p.nombre.replace(/_/g, " "), enDoc = !!normDoc[c[n].norm] || p.tipo === "process";
              var fila = el("div", { class: "tinta" }, el("b", {}, p.nombre), " · " + p.tipo + " · " + p.cobertura.toFixed(1) + " %",
                enDoc ? "" : el("span", { class: "alerta" }, " ⚠ " + t("sep.sin_muestra")),
                el("span", {}, " "), el("button", { class: "sec mini", onclick: function () { mostrar(p.nombre, false); } }, t("sep.solo")),
                el("button", { class: "sec mini", onclick: function () { mostrar(p.nombre, true); } }, t("sep.negativo")));
              tintas.appendChild(fila);
            });
            var usadas = {}; ctx.res.placas.forEach(function (p) { usadas[c[p.nombre.replace(/_/g, " ")].norm] = true; });
            spots.forEach(function (s) { if (!usadas[c[s].norm]) { tintas.appendChild(el("div", { class: "tinta alerta" }, "⚠ " + s + " — " + t("sep.muestra_sin_uso"))); } });
          });
        }).then(function () {
          tacInfo.textContent = t("sep.tac", { v: ctx.res.tac.max });
          hall.innerHTML = "";
          if (ctx.res.hallazgos.length) { hall.appendChild(el("h3", {}, t("sep.hallazgos"))); }
          return FVP.api.postJSON("/api/plugin/separar/hallazgos_pt?alto_pt=" + ctx.exp.tamano_pt[1] + "&dpi=" + ctx.res.dpi, ctx.res.hallazgos);
        }).then(function (lista) {
          lista.forEach(function (h) {
            hall.appendChild(el("div", { class: "hallazgo " + (h.severidad === "error" ? "error" : "advertencia"), onclick: function () {
              if (!h.bbox_pt) { return; }
              FVP.host.call("zoomTo", { bbox: h.bbox_pt, mesa: ctx.mesa }).then(function () { return FVP.host.call("selectInBBox", { bbox: h.bbox_pt, mesa: ctx.mesa }); });
            } }, h.mensaje));
          });
          mostrar(null);
        }).catch(function (e) { FVP.ui.toast(e.message, "error"); });
      }

      function mostrar(nombre, neg) {
        var u = nombre ? ctx.urls.placa + encodeURIComponent(nombre) + (neg ? "&negativo=true" : "") : ctx.urls.composicion;
        FVP.api.downloadBlob(u).then(function (b) { vista.src = g.URL.createObjectURL(b); vista.classList.remove("hidden"); });
      }

      vista.addEventListener("click", function (ev) {
        if (!ctx) { return; }
        var r = vista.getBoundingClientRect(), sx = vista.naturalWidth / r.width, sy = vista.naturalHeight / r.height;
        var x = Math.round((ev.clientX - r.left) * sx), y = Math.round((ev.clientY - r.top) * sy);
        FVP.api.get(ctx.urls.sonda + "&x=" + x + "&y=" + y).then(function (d) {
          dens.textContent = t("sep.medida", { tac: d.tac, tintas: Object.keys(d.tintas).filter(function (k) { return d.tintas[k] > 0; }).map(function (k) { return k + " " + d.tintas[k] + " %"; }).join(" · ") });
        });
      });

      function exportar() {
        if (!ctx) { return; }
        var dest = FVP.files.saveDialog(t("sep.exportar"), "placas.zip", ["zip"]);
        if (!dest) { return; }
        FVP.api.request(ctx.urls.exportar, { json: { formato: "tiff8", dpi: 300 } }).then(function (r) { return r.arrayBuffer(); })
          .then(function (ab) { FVP.files.writeArrayBuffer(dest, ab); FVP.ui.toast(t("comun.listo"), "ok"); })
          .catch(function (e) { FVP.ui.toast(e.message, "error"); });
      }
      function abrirEnFaverview() { if (ctx) { FVP.host.openURL(FVP.api.state.base + "/#/separar"); } }

      root.appendChild(el("div", { class: "seccion" }, el("h2", {}, t("sep.titulo")),
        el("div", { class: "botones" }, el("button", { onclick: analizar }, t("sep.analizar")), el("button", { class: "sec", onclick: exportar }, t("sep.exportar")),
          el("button", { class: "sec", onclick: abrirEnFaverview }, t("sep.abrir"))),
        busy, tacInfo, tintas, hall, vista, dens));
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
