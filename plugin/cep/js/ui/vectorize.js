/* Pestaña Vectorizar (P3): imagen seleccionada → vista previa → colocar exactamente encima. */
(function (g) {
  "use strict";
  var FVP = g.FVP, el = FVP.ui.el, t = FVP.t;
  var PRESETS = [["logo", "Logo"], ["linea", "Línea (B/N)"], ["ilustracion", "Ilustración"], ["escaneo", "Escaneo"], ["foto", "Foto posterizada"]];

  FVP.ui.vectorizar = {
    id: "vectorizar",
    mount: function (root) {
      var last = null, sel = null;
      var preset = el("select", {}, PRESETS.map(function (p) { return el("option", { value: p[0] }, p[1]); }));
      var colores = el("input", { type: "number", value: 6, min: 2, max: 12 });
      var detalle = el("input", { type: "number", value: 0.15, step: 0.05, min: 0 });
      var limpia = el("input", { type: "checkbox" });
      var biblio = el("select", {}, el("option", { value: "" }, "—"));
      var trap = el("input", { type: "checkbox" });
      var prensa = el("select", {});
      var tam = el("input", { type: "number", min: 1, step: 1, placeholder: "auto" });
      var ocultar = el("input", { type: "checkbox", checked: true });
      var info = el("div", { class: "info" }), vista = el("img", { class: "vista hidden", alt: "" }), stats = el("div", { class: "hint" });
      var busy = el("div", {});
      var bColocar = el("button", { disabled: true, onclick: colocar }, t("vec.colocar"));

      FVP.api.get("/api/plugin/prensas").then(function (ps) { ps.forEach(function (p) { prensa.appendChild(el("option", { value: p.id }, p.nombre)); }); }).catch(function () {});
      FVP.api.get("/api/tintas").then(function (libs) { libs.forEach(function (l) { biblio.appendChild(el("option", { value: l.nombre }, l.nombre)); }); }).catch(function () {});

      function params(libInks) {
        var p = { preset: preset.value, k_max: +colores.value, detalle_min_mm: +detalle.value, geometria_limpia: limpia.checked };
        if (trap.checked) { p.trap_prensa = prensa.value; }
        if (libInks) { p.tintas = libInks; }
        return p;
      }

      function vectorizar() {
        FVP.host.call("exportSelectionPNG", { ppi: 300 }).then(function (s) {
          sel = s;
          var b = s.bounds, anchoPt = Math.abs(b[2] - b[0]);
          var mm = +tam.value || anchoPt / 72 * 25.4;
          return (biblio.value ? FVP.api.get("/api/tintas/" + encodeURIComponent(biblio.value)).then(function (l) {
            return l.inks.filter(function (i) { return i.lab; }).map(function (i) { return { name: i.name, lab: i.lab }; });
          }) : Promise.resolve(null)).then(function (libInks) {
            return FVP.ui.run(busy, function (progreso, ctl) {
              return FVP.api.uploadFile("/api/plugin/vectorizar", "file", s.ruta, { parametros: params(libInks), tamano_mm: mm }, "image/png").then(function (r) {
                return FVP.api.pollJob(r.job_id, progreso, ctl);
              });
            }).then(function (res) { return { res: res, mm: mm }; });
          });
        }).then(function (o) {
          last = o.res;
          var st = o.res.estadisticas;
          stats.textContent = t("vec.estadisticas", { trazados: st.trazados, nodos: st.nodos, colores: st.colores, segundos: st.segundos });
          var v = o.res.archivos.filter(function (a) { return a.nombre === "vista.png"; })[0];
          if (v) { FVP.api.downloadBlob(v.url).then(function (b) { vista.src = g.URL.createObjectURL(b); vista.classList.remove("hidden"); }); }
          bColocar.disabled = false;
        }).catch(function (e) { if (!/cancel/i.test(e.message)) { FVP.ui.toast(e.message, "error"); } });
      }

      function colocar() {
        if (!last || !sel) { return; }
        var pdfUrl = last.archivos.filter(function (a) { return a.nombre === "vector.pdf"; })[0].url;
        FVP.ui.bajarArchivo(pdfUrl, "vector.pdf").then(function (ruta) {
          return FVP.host.call("placeOverSelection", { ruta: ruta, capa: "FAVERVIEW – Vector", nombre: "FAVERVIEW vector", ocultarOriginal: ocultar.checked,
            tintas: last.colores.map(function (c) { return { nombre: c.nombre.replace(/ /g, "_"), lab: c.lab }; }) });
        }).then(function () { FVP.ui.toast(t("comun.listo"), "ok"); }).catch(function (e) { FVP.ui.toast(e.message, "error"); });
      }

      function row(label, input) { return el("label", { class: "fila" }, el("span", {}, label), input); }
      root.appendChild(el("div", { class: "seccion" },
        el("h2", {}, t("vec.titulo")), el("p", { class: "hint" }, t("vec.selecciona")),
        row(t("vec.preajuste"), preset), row(t("vec.colores"), colores), row(t("vec.detalle"), detalle), row(t("vec.tamano"), tam),
        row(t("vec.limpia"), limpia), row(t("vec.biblioteca"), biblio), row(t("vec.trap"), trap), row(t("trap.perfil"), prensa), row(t("vec.ocultar"), ocultar),
        el("div", { class: "botones" }, el("button", { onclick: vectorizar }, t("vec.vectorizar")), bColocar),
        busy, info, stats, vista));
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
