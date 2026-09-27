/* Pestaña Ajustes: preajuste de PDF, versión, actualización del plugin y limpieza de temporales. */
(function (g) {
  "use strict";
  var FVP = g.FVP, el = FVP.ui.el, t = FVP.t;
  var PLUGIN_VERSION = "3.2.1";

  /** compara versiones «3.1.0» → -1, 0, 1 */
  FVP.cmpVersion = function (a, b) {
    var x = String(a).split(/[.\-]/).map(Number), y = String(b).split(/[.\-]/).map(Number), i;
    for (i = 0; i < Math.max(x.length, y.length); i++) {
      var p = x[i] || 0, q = y[i] || 0;
      if (p !== q) { return p < q ? -1 : 1; }
    }
    return 0;
  };
  FVP.PLUGIN_VERSION = PLUGIN_VERSION;

  FVP.ui.ajustes = {
    id: "ajustes",
    mount: function (root) {
      var preset = el("input", { type: "text", value: FVP.settings.preset });
      preset.addEventListener("change", function () { FVP.settings.preset = preset.value; try { g.localStorage.setItem("fv_preset", preset.value); } catch (e) { /* sin almacenamiento */ } });
      try { var s = g.localStorage.getItem("fv_preset"); if (s) { FVP.settings.preset = s; preset.value = s; } } catch (e2) { /* nada */ }
      var upd = el("div", { class: "info" }), srv = el("div", { class: "hint" });
      srv.textContent = t("aj.servidor", { url: FVP.api.state.base || "—" });

      FVP.api.get("/api/update").then(function (u) {
        var nueva = u.plugin_version && FVP.cmpVersion(PLUGIN_VERSION, u.plugin_version) < 0;
        if (nueva) { upd.appendChild(el("span", {}, t("aj.actualizacion", { v: u.plugin_version }) + " ")); upd.appendChild(el("button", { class: "sec", onclick: function () { FVP.host.openURL(u.plugin_url || u.url); } }, t("aj.descargar"))); }
      }).catch(function () {});

      root.appendChild(el("div", { class: "seccion" }, el("h2", {}, t("aj.titulo")),
        el("label", { class: "fila" }, el("span", {}, t("aj.preset")), preset),
        el("div", { class: "hint" }, t("aj.version", { v: PLUGIN_VERSION })), srv, upd,
        el("div", { class: "botones" }, el("button", { class: "sec", onclick: function () {
          try { FVP.ui.toast(FVP.files.cleanTemp(FVP.state.tempPath, 0) + " archivo(s)", "ok"); } catch (e) { FVP.ui.toast(e.message, "error"); } } }, t("aj.limpiar")))));
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
