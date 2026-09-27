/* Arranque del panel: tema, conexión (verde/amarillo/rojo con reintento cada 5 s), pestañas y limpieza de temporales. */
(function (g) {
  "use strict";
  var FVP = g.FVP, el = FVP.ui.el, t = FVP.t;
  var TABS = ["vectorizar", "preflight", "separar", "comparar", "codigos", "trap", "ajustes"];
  var mounted = {}, retryTimer = null;

  function paintStatus() {
    var st = FVP.api.state, box = g.document.getElementById("estado");
    box.className = "estado " + st.estado;
    box.innerHTML = "";
    box.appendChild(el("span", { class: "punto" }));
    box.appendChild(el("span", {}, st.mensaje));
    if (st.estado === "rojo") {
      box.appendChild(el("div", { class: "hint" }, t("estado.rojo.ayuda")));
      box.appendChild(el("button", { class: "sec", onclick: connect }, t("estado.reintentar")));
    }
    g.document.getElementById("tabs").classList.toggle("bloqueado", st.estado === "rojo");
    g.document.getElementById("contenido").classList.toggle("bloqueado", st.estado === "rojo");
  }

  function connect() {
    clearTimeout(retryTimer);
    return FVP.api.connect().then(function (st) {
      paintStatus();
      if (st.estado === "rojo") { retryTimer = setTimeout(connect, 5000); }
      return st;
    });
  }

  function show(id) {
    TABS.forEach(function (n) {
      var pane = g.document.getElementById("pane-" + n), btn = g.document.getElementById("tab-" + n);
      pane.classList.toggle("hidden", n !== id); btn.classList.toggle("activa", n === id);
    });
    if (!mounted[id]) { mounted[id] = true; FVP.ui[id].mount(g.document.getElementById("pane-" + id)); }
  }

  FVP.app = {
    init: function () {
      FVP.theme.init();
      var tabs = g.document.getElementById("tabs"), cont = g.document.getElementById("contenido");
      TABS.forEach(function (n) {
        tabs.appendChild(el("button", { id: "tab-" + n, class: "tab", onclick: function () { show(n); } }, t("tab." + n)));
        cont.appendChild(el("section", { id: "pane-" + n, class: "pane hidden" }));
      });
      FVP.host.call("ping", {}).then(function (p) {
        FVP.state.tempPath = p.tempPath.replace(/\\/g, "/");
        try { FVP.files.cleanTemp(FVP.state.tempPath, 24); } catch (e) { /* sin carpeta aún */ }
      }).catch(function () {});
      show("vectorizar");
      return connect();
    },
    show: show, connect: connect
  };
  g.addEventListener("load", function () { if (!FVP.app._noAuto) { FVP.app.init(); } });
}(typeof window !== "undefined" ? window : globalThis));
