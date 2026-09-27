/* Pestaña Códigos (P8): generar e insertar códigos de barras y braille, y verificar los del documento. */
(function (g) {
  "use strict";
  var FVP = g.FVP, el = FVP.ui.el, t = FVP.t;
  var TIPOS = [["ean13", "EAN-13"], ["ean8", "EAN-8"], ["upca", "UPC-A"], ["upce", "UPC-E"], ["itf14", "ITF-14"], ["code128", "Code 128"], ["gs1_128", "GS1-128"],
               ["code39", "Code 39"], ["databar", "GS1 DataBar"], ["datamatrix", "Data Matrix"], ["gs1_datamatrix", "GS1 DataMatrix"], ["qr", "QR"]];

  FVP.ui.codigos = {
    id: "codigos",
    mount: function (root) {
      var tipo = el("select", {}, TIPOS.map(function (x) { return el("option", { value: x[0] }, x[1]); }));
      var datos = el("input", { type: "text", value: "590123412345" });
      var mag = el("input", { type: "number", value: 100, min: 50, max: 400 });
      var bwr = el("input", { type: "number", value: 0, min: 0, step: 5 });
      var tinta = el("select", {}, el("option", { value: "" }, t("cod.negro")));
      var prev = el("div", { class: "vista-svg" }), aviso = el("div", { class: "hint" }), busy = el("div", {}), res = el("div", { class: "lista" });
      var tintas = [], timer = null, lastDims = null;
      var bt = el("textarea", { rows: 2 }, "Paracetamol 500 mg"), prevB = el("div", { class: "vista-svg" }), avB = el("div", { class: "hint" });

      FVP.api.get("/api/tintas").then(function (libs) {
        return Promise.all(libs.map(function (l) { return FVP.api.get("/api/tintas/" + encodeURIComponent(l.nombre)); }));
      }).then(function (all) {
        all.forEach(function (lib) { lib.inks.forEach(function (i) { if (i.lab && i.kind !== "white" && i.kind !== "varnish") { tintas.push(i); tinta.appendChild(el("option", { value: tintas.length - 1 }, i.name)); } }); });
      }).catch(function () {});

      function cuerpo(vista) {
        var ink = tinta.value === "" ? null : tintas[+tinta.value];
        return { tipo: tipo.value, datos: datos.value, magnificacion: (+mag.value || 100) / 100, bwr_um: +bwr.value || 0, tinta: ink ? { name: ink.name.replace(/ /g, "_"), lab: ink.lab } : null, vista: !!vista };
      }
      function preview() {
        clearTimeout(timer);
        timer = setTimeout(function () {                                   // validación en vivo
          FVP.api.postJSON("/api/plugin/codigo", cuerpo(true)).then(function (r) {
            prev.innerHTML = r.svg; lastDims = [r.ancho_mm, r.alto_mm]; aviso.textContent = r.ancho_mm + " × " + r.alto_mm + " mm" + (r.avisos.length ? " · " + r.avisos.join(" ") : "");
            aviso.className = "hint";
          }, function (e) { prev.innerHTML = ""; aviso.textContent = e.message; aviso.className = "hint error"; });
        }, 300);
      }
      [tipo, datos, mag, bwr, tinta].forEach(function (c) { c.addEventListener("input", preview); c.addEventListener("change", preview); });

      function insertar(endpoint, body, nombre, tintasHost) {
        FVP.api.request(endpoint, { json: body }).then(function (r) {
          var ancho = parseFloat(r.headers.get("X-Ancho-mm")), alto = parseFloat(r.headers.get("X-Alto-mm"));
          return r.arrayBuffer().then(function (ab) {
            var ruta = FVP.ui.tempPath(Date.now() + "_" + nombre + ".pdf");
            FVP.files.writeArrayBuffer(ruta, ab);
            return FVP.host.call("insertPDF", { ruta: ruta, ancho_pt: ancho / 25.4 * 72, alto_pt: alto / 25.4 * 72, capa: nombre === "braille" ? "FAVERVIEW – Braille" : "FAVERVIEW – Códigos", nombre: nombre, tintas: tintasHost });
          });
        }).then(function () { FVP.ui.toast(t("comun.listo"), "ok"); }).catch(function (e) { FVP.ui.toast(e.message, "error"); });
      }

      function verificar() {
        FVP.ui.mesas(false).then(function (m) {
          return FVP.ui.exportMesa(m[0]).then(function (exp) {
            return FVP.ui.run(busy, function () {
              return FVP.api.uploadFile("/api/plugin/codigos/verificar", "file", exp.ruta, { dpi: 600 }, "application/pdf");
            }).then(function (r) { return { r: r, mesa: m[0] }; });
          });
        }).then(function (o) {
          res.innerHTML = "";
          if (!o.r.codigos.length) { res.appendChild(el("p", { class: "hint" }, t("cod.sin_codigos"))); return; }
          o.r.codigos.forEach(function (c) {
            res.appendChild(el("div", { class: "hallazgo " + (c.avisos.some(function (a) { return a.severidad === "error"; }) ? "error" : "info"), onclick: function () {
              FVP.host.call("zoomTo", { bbox: c.bbox_pt, mesa: o.mesa, margen: 30 });
            } }, el("b", {}, c.contenido), " · " + t("cod.grado", { g: c.grado.letra }), c.avisos.map(function (a) { return el("div", {}, a.mensaje); })));
          });
        }).catch(function (e) { FVP.ui.toast(e.message, "error"); });
      }

      function previewBraille() {
        FVP.api.postJSON("/api/plugin/braille", { texto: bt.value, ancho_mm: 80, vista: true }).then(function (r) { prevB.innerHTML = r.svg; avB.textContent = r.unicode + " · " + r.avisos.join(" "); avB.className = "hint"; },
          function (e) { prevB.innerHTML = ""; avB.textContent = e.message; avB.className = "hint error"; });
      }
      bt.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(previewBraille, 300); });

      root.appendChild(el("div", { class: "seccion" }, el("h2", {}, t("cod.titulo")),
        el("label", { class: "fila" }, el("span", {}, t("cod.tipo")), tipo), el("label", { class: "fila" }, el("span", {}, t("cod.datos")), datos),
        el("label", { class: "fila" }, el("span", {}, t("cod.mag")), mag), el("label", { class: "fila" }, el("span", {}, t("cod.bwr")), bwr),
        el("label", { class: "fila" }, el("span", {}, t("cod.tinta")), tinta), prev, aviso,
        el("div", { class: "botones" }, el("button", { onclick: function () {
          var b = cuerpo(false); insertar("/api/plugin/codigo", b, "codigo", b.tinta ? [{ nombre: b.tinta.name, lab: b.tinta.lab }] : null); } }, t("cod.insertar")),
          el("button", { class: "sec", onclick: verificar }, t("cod.verificar"))),
        busy, res,
        el("h2", {}, t("cod.braille")), el("label", { class: "fila" }, el("span", {}, t("cod.texto")), bt), prevB, avB,
        el("div", { class: "botones" }, el("button", { onclick: function () { insertar("/api/plugin/braille", { texto: bt.value, ancho_mm: 80 }, "braille", [{ nombre: "Braille", cmyk: [0, 0, 0, 100] }]); } }, t("cod.insertar")))));
      preview(); previewBraille();
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
