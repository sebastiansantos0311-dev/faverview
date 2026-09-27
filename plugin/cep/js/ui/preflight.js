/* Pestaña Preflight (P4): revisar mesas, clic → zoom y selección, marcadores y correcciones nativas en Illustrator. */
(function (g) {
  "use strict";
  var FVP = g.FVP, el = FVP.ui.el, t = FVP.t;
  var SEV = [["error", "pf.errores"], ["advertencia", "pf.advertencias"], ["info", "pf.info"]];

  FVP.ui.preflight = {
    id: "preflight",
    mount: function (root) {
      var perfil = el("select", {}), busy = el("div", {}), lista = el("div", { class: "lista" }), fixes = el("div", { class: "seccion" });
      var hallazgos = [];     // [{..., mesa}]

      FVP.api.get("/api/preflight/perfiles").then(function (ps) {
        ps.forEach(function (p) { perfil.appendChild(el("option", { value: p.id }, p.nombre)); });
      }).catch(function () {});

      function revisar(todas) {
        FVP.ui.mesas(todas).then(function (mesas) {
          hallazgos = [];
          return mesas.reduce(function (prev, mesa) {
            return prev.then(function () {
              return FVP.ui.run(busy, function (progreso, ctl) {
                return FVP.ui.exportMesa(mesa).then(function (exp) {
                  return FVP.ui.subirMesa("/api/plugin/preflight", "file", exp, { perfil: perfil.value || "offset_hoja" }, progreso, ctl);
                });
              }).then(function (res) { res.hallazgos.forEach(function (h) { h.mesa = mesa; hallazgos.push(h); }); });
            });
          }, Promise.resolve());
        }).then(pintar).catch(function (e) { if (!/cancel/i.test(e.message)) { FVP.ui.toast(e.message, "error"); } });
      }

      function irA(h) {
        if (!h.bbox_pt) { return; }
        FVP.host.call("zoomTo", { bbox: h.bbox_pt, mesa: h.mesa, margen: 40 })
          .then(function () { return FVP.host.call("selectInBBox", { bbox: h.bbox_pt, mesa: h.mesa }); })
          .then(function (r) { if (r.aviso) { FVP.ui.toast(r.aviso, "info"); } })
          .catch(function (e) { FVP.ui.toast(e.message, "error"); });
      }

      function pintar() {
        lista.innerHTML = "";
        if (!hallazgos.length) { lista.appendChild(el("p", { class: "hint" }, t("pf.sin_problemas"))); return; }
        SEV.forEach(function (s) {
          var items = hallazgos.filter(function (h) { return h.severidad === s[0]; });
          if (!items.length) { return; }
          lista.appendChild(el("h3", {}, t(s[1]) + " (" + items.length + ")"));
          items.forEach(function (h) {
            lista.appendChild(el("div", { class: "hallazgo " + s[0], onclick: function () { irA(h); } },
              el("b", {}, h.nombre), " · " + t("comun.mesa") + " " + (h.mesa + 1), el("br"), h.mensaje));
          });
        });
      }

      function marcar() {
        var por = {};
        hallazgos.forEach(function (h) { if (h.bbox_pt) { (por[h.mesa] = por[h.mesa] || []).push({ bbox: h.bbox_pt, id: 0, etiqueta: String(hallazgos.indexOf(h) + 1), color: h.severidad === "error" ? [230, 30, 30] : [240, 160, 0] }); } });
        var mesas = Object.keys(por);
        (function next(i) {
          if (i >= mesas.length) { FVP.ui.toast(t("comun.listo"), "ok"); return; }
          FVP.host.call("markers", { mesa: +mesas[i], lista: por[mesas[i]] }).then(function () { next(i + 1); }).catch(function (e) { FVP.ui.toast(e.message, "error"); });
        }(0));
      }

      /* ---- correcciones nativas ---- */
      function nombresSpot() { return FVP.host.call("listSpots", {}); }
      function clasificar(nombres) { return FVP.api.postJSON("/api/plugin/tintas/clasificar", { nombres: nombres }); }
      var FIXES = [
        { id: "sobreimpresion", texto: "pf.fix.sobreimpresion", args: function () {
            return nombresSpot().then(clasificar_).then(function (c) { return { op: "fixOverprint", a: { tintas: Object.keys(c).filter(function (n) { return c[n].tipo === "technical" || c[n].tipo === "varnish"; }) } }; });
        } },
        { id: "negro", texto: "pf.fix.negro", args: function () { return Promise.resolve({ op: "fixBlackText", a: { maxPt: 12 } }); } },
        { id: "unir", texto: "pf.fix.unir", args: function () {
            return nombresSpot().then(clasificar_).then(function (c) {
              var canon = {}, mapa = {};
              Object.keys(c).forEach(function (n) { var k = c[n].norm; if (canon[k] === undefined) { canon[k] = n; } else { mapa[n] = canon[k]; } });
              return { op: "mergeSpots", a: { mapa: mapa } };
            });
        } },
        { id: "sin_uso", texto: "pf.fix.sin_uso", args: function () { return Promise.resolve({ op: "removeUnusedSpots", a: {} }); } },
        { id: "rgb", texto: "pf.fix.rgb", soloReporta: true }
      ];
      function clasificar_(n) { return n.length ? clasificar(n) : Promise.resolve({}); }

      FIXES.forEach(function (f) {
        var out = el("span", { class: "hint" });
        var fila = el("div", { class: "fila fix" }, el("span", {}, t(f.texto)));
        if (f.soloReporta) { fila.appendChild(el("span", { class: "hint" }, t("pf.solo_reporta"))); fixes.appendChild(fila); return; }
        var bAplicar = el("button", { disabled: true }, t("pf.aplicar")), bVer = el("button", { class: "sec" }, "Ver");
        var pend = null;
        bVer.onclick = function () {
          f.args().then(function (p) { pend = p; var a = JSON.parse(JSON.stringify(p.a)); a.soloContar = true; return FVP.host.call(p.op, a); })
            .then(function (r) { out.textContent = t("pf.afectados", { n: r.objetos !== undefined ? r.objetos : (r.muestras ? r.muestras.length : 0) }); bAplicar.disabled = false; })
            .catch(function (e) { FVP.ui.toast(e.message, "error"); });
        };
        bAplicar.onclick = function () {
          if (!pend) { return; }
          var n = out.textContent;
          if (!g.confirm(t("pf.confirmar", { nombre: t(f.texto), n: (n.match(/\d+/) || ["0"])[0] }))) { return; }
          FVP.host.call(pend.op, pend.a).then(function () { FVP.ui.toast(t("comun.listo"), "ok"); bAplicar.disabled = true; revisar(false); })
            .catch(function (e) { FVP.ui.toast(e.message, "error"); });
        };
        fila.appendChild(bVer); fila.appendChild(bAplicar); fila.appendChild(out);
        fixes.appendChild(fila);
      });

      root.appendChild(el("div", { class: "seccion" },
        el("h2", {}, t("pf.titulo")),
        el("label", { class: "fila" }, el("span", {}, t("pf.perfil")), perfil),
        el("div", { class: "botones" }, el("button", { onclick: function () { revisar(false); } }, t("pf.revisar_mesa")),
          el("button", { class: "sec", onclick: function () { revisar(true); } }, t("pf.revisar_todas"))),
        el("div", { class: "botones" }, el("button", { class: "sec", onclick: marcar }, t("pf.marcar")),
          el("button", { class: "sec", onclick: function () { FVP.host.call("clearMarkers", {}); } }, t("pf.quitar"))),
        busy, lista, el("h3", {}, t("pf.corregir")), fixes));
      FVP.ui.preflight._irA = irA;
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
