"use strict";
/* Pantalla «Tintas»: ver, importar (CxF/ASE/CSV/JSON), editar y exportar bibliotecas. */
(function () {
  const { h, showError, dialog } = FV;
  const { api, getJSON, postJSON } = FVApi;
  const KINDS = [["process", "proceso"], ["spot", "directa"], ["white", "blanco"], ["varnish", "barniz"], ["technical", "técnica"]];

  async function open() {
    const body = h("div", { class: "tintas" });
    const dlg = dialog("Tintas", body, [{ label: "Cerrar" }], true);
    let libs = [], lib = null;

    async function refresh(select) {
      libs = await getJSON("/api/tintas");
      const name = select || (lib && lib.name) || libs[0].nombre;
      lib = await getJSON("/api/tintas/" + encodeURIComponent(name));
      render();
    }

    function swatch(i) { return h("span", { class: "sw-box", style: { background: i.swatch || "transparent" }, title: i.swatch ? "Vista aproximada en sRGB" : "sin color" }); }

    function render() {
      const ro = lib.readonly;
      const sel = h("select", { onchange: async e => { lib = await getJSON("/api/tintas/" + encodeURIComponent(e.target.value)); render(); } },
        libs.map(l => h("option", { value: l.nombre, selected: l.nombre === lib.name }, `${l.nombre} (${l.tintas})`)));
      const file = h("input", { type: "file", accept: ".ase,.cxf,.xml,.csv,.txt,.json", hidden: true, onchange: async e => {
        const f = e.target.files[0]; if (!f) return;
        const name = prompt("¿Con qué nombre guardar la biblioteca importada?", f.name.replace(/\.[^.]+$/, ""));
        if (!name) return;
        const fd = new FormData(); fd.append("file", f); fd.append("nombre", name);
        try { const r = await (await api("/api/tintas-importar", { method: "POST", body: fd })).json(); await refresh(r.name); FV.toast(`Importadas ${r.inks.length} tintas`, "ok"); }
        catch (er) { showError(er.message); FV.toast(er.message, "error", 6000); }
      } });
      const rows = lib.inks.map((i, n) => h("tr", {},
        h("td", {}, swatch(i)),
        h("td", {}, h("input", { value: i.name, disabled: ro, onchange: e => i.name = e.target.value })),
        h("td", {}, h("select", { disabled: ro, onchange: e => i.kind = e.target.value }, KINDS.map(([v, t]) => h("option", { value: v, selected: v === i.kind }, t)))),
        ...[0, 1, 2].map(k => h("td", {}, h("input", { type: "number", step: "0.1", class: "num", value: i.lab ? i.lab[k] : "", disabled: ro,
          onchange: e => { const v = e.target.value === "" ? null : +e.target.value;
            if (v === null) { i.lab = null; } else { i.lab = i.lab || [50, 0, 0]; i.lab[k] = v; } } }))),
        h("td", {}, h("input", { type: "number", step: "0.1", min: 0, max: 1, class: "num", value: i.opacity, disabled: ro, onchange: e => i.opacity = +e.target.value })),
        h("td", { class: "hint" }, i.source || ""),
        h("td", {}, ro ? "" : h("button", { onclick: () => { lib.inks.splice(n, 1); render(); } }, "✕"))));
      body.replaceChildren(
        h("p", { class: "hint" }, "Las bibliotecas Pantone, HKS, RAL, TOYO y DIC tienen licencia: FAVERVIEW no las incluye. Importa las tuyas (CxF, ASE o CSV). "
          + "Se guardan solo en este equipo (datos_locales/tintas). Las muestras de color son una vista aproximada en sRGB."),
        h("div", { class: "learn-actions" }, sel,
          h("button", { onclick: () => file.click() }, "Importar…"), file,
          h("button", { onclick: () => { const n = prompt("Nombre de la biblioteca nueva:", ro ? lib.name + " (copia)" : ""); if (!n) return;
            lib = { name: n, readonly: false, inks: JSON.parse(JSON.stringify(lib.inks)) }; render(); } }, ro ? "Duplicar para editar" : "Nueva copia…"),
          ro ? "" : h("button", { class: "primary", onclick: async () => {
            try { const r = await postJSON("/api/tintas", { name: lib.name, inks: lib.inks.map(({ swatch, ...x }) => x) }); await refresh(r.name); FV.toast("Biblioteca guardada", "ok"); }
            catch (er) { FV.toast(er.message, "error", 6000); } } }, "Guardar"),
          h("a", { class: "button", href: `/api/tintas/${encodeURIComponent(lib.name)}/exportar?formato=json`, download: "" }, "Exportar JSON"),
          h("a", { class: "button", href: `/api/tintas/${encodeURIComponent(lib.name)}/exportar?formato=csv`, download: "" }, "Exportar CSV"),
          ro ? "" : h("button", { onclick: async () => { if (!confirm("¿Borrar la biblioteca «" + lib.name + "»?")) return;
            await api("/api/tintas/" + encodeURIComponent(lib.name), { method: "DELETE" }); lib = null; await refresh(); } }, "Borrar")),
        ro ? h("div", { class: "hint" }, "Biblioteca incorporada (solo lectura): valores de referencia públicos ISO 12647-2 PC1 (FOGRA51).") : "",
        h("table", { class: "learn-table tintas-table" },
          h("tr", {}, ["", "Nombre", "Tipo", "L*", "a*", "b*", "Opacidad", "Origen", ""].map(t => h("th", {}, t))), rows),
        ro ? "" : h("button", { onclick: () => { lib.inks.push({ name: "Nueva tinta", kind: "spot", lab: [50, 0, 0], opacity: 0, source: "usuario" }); render(); } }, "+ tinta"));
    }
    try { await refresh(); } catch (e) { body.textContent = e.message; }
  }

  window.FVInks = { open };
  const btn = document.getElementById("btn-tintas");
  if (btn) btn.addEventListener("click", open);
})();
