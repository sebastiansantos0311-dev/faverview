/* Pestaña Trap (P7): prueba de movimiento de la mesa, marcadores de filetes y creación de traps vectoriales (arte plano). */
(function (g) {
  "use strict";
  var FVP = g.FVP, el = FVP.ui.el, t = FVP.t;

  FVP.ui.trap = {
    id: "trap",
    mount: function (root) {
      var perfil = el("select", {}), tol = el("input", { type: "number", step: 0.05, min: 0, max: 5, class: "num" });
      var busy = el("div", {}), msg = el("div", { class: "info" }), detalle = el("div", { class: "hint" }), lim = el("div", { class: "hint error" });
      var presses = [];

      FVP.api.get("/api/plugin/prensas").then(function (ps) {
        presses = ps;
        ps.forEach(function (p) { perfil.appendChild(el("option", { value: p.id }, p.nombre + " (" + (Array.isArray(p.tolerancia_mm) ? p.tolerancia_mm.join("×") : p.tolerancia_mm) + " mm)")); });
        perfil.value = "serigrafia_textil_automatica";
        actualizarTol();
      }).catch(function () {});
      function actualizarTol() { var p = presses.filter(function (x) { return x.id === perfil.value; })[0]; if (p) { tol.value = Array.isArray(p.tolerancia_mm) ? p.tolerancia_mm[0] : p.tolerancia_mm; } }
      perfil.addEventListener("change", actualizarTol);

      function ejecutar(crear) {
        lim.textContent = "";
        FVP.ui.mesas(false).then(function (m) {
          var mesa = m[0];
          return FVP.ui.exportMesa(mesa).then(function (exp) {
            return FVP.ui.run(busy, function (progreso, ctl) {
              return FVP.api.uploadFile("/api/plugin/trap", "file", exp.ruta, { perfil: perfil.value, tolerancia_mm: tol.value === "" ? null : +tol.value, crear_vectorial: crear, dpi: 600 }, "application/pdf")
                .then(function (r) { return FVP.api.pollJob(r.job_id, progreso, ctl); });
            }).then(function (res) { return { res: res, exp: exp, mesa: mesa }; });
          });
        }).then(function (o) {
          var r = o.res, tl = Array.isArray(r.tolerancia_mm) ? r.tolerancia_mm[0] : r.tolerancia_mm;
          msg.textContent = r.ok ? t("trap.ok", { tol: tl }) : t("trap.mal", { mm2: r.registro.filetes_mm2, tol: tl });
          msg.className = "info " + (r.ok ? "ok" : "error");
          detalle.textContent = t("trap.estimacion") + " " + t("trap.ayuda");
          var marcar = FVP.host.call("clearMarkers", {}).then(function () {
            return r.filetes.length ? FVP.host.call("markers", { mesa: o.mesa, lista: r.filetes.map(function (f, i) { return { bbox: f.bbox_pt, id: i + 1, etiqueta: String(i + 1), color: [255, 0, 200] }; }) }) : null;
          });
          if (crear && !r.arte_plano) { lim.textContent = t("trap.limite"); return marcar; }
          if (crear && r.vectorial.archivos) {
            return marcar.then(function () { return FVP.ui.bajarArchivo(r.vectorial.archivos[0].url, "traps.pdf"); }).then(function (ruta) {
              var rect = o.exp.artboardRect;
              return FVP.host.call("placePDF", { ruta: ruta, capa: "FAVERVIEW – Traps", nombre: "FAVERVIEW Traps", x: rect[0], y: rect[1], ancho: o.exp.tamano_pt[0], alto: o.exp.tamano_pt[1] });
            }).then(function () { FVP.ui.toast(t("comun.listo") + " " + t("trap.ayuda"), "ok"); });
          }
          return marcar;
        }).catch(function (e) { if (!/cancel/i.test(e.message)) { FVP.ui.toast(e.message, "error"); } });
      }

      root.appendChild(el("div", { class: "seccion" }, el("h2", {}, t("trap.titulo")),
        el("label", { class: "fila" }, el("span", {}, t("trap.perfil")), perfil), el("label", { class: "fila" }, el("span", {}, t("trap.tol")), tol),
        el("div", { class: "botones" }, el("button", { onclick: function () { ejecutar(false); } }, t("trap.analizar")),
          el("button", { class: "sec", onclick: function () { ejecutar(true); } }, t("trap.crear"))),
        busy, msg, lim, detalle));
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
