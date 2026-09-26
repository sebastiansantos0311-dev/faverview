"use strict";
/* Arranque de la suite: estado de las herramientas, aviso de actualización, versión y primera ruta. */

(async function () {
  const { $, h } = FV;
  let status = null;
  try {
    status = await FVApi.getJSON("/api/status");
    FVRouter.status = status;
    FVRouter.version = status.version;
    $("#version").textContent = "FAVERVIEW v" + status.version;
    // pestaña desactivada (con aviso) si falta una herramienta que ese módulo necesita
    const map = { comparar: "comparar", separar: "separar", vectorizar: "vectorizar", preflight: "preflight",
                  codigos: "codigos", herramientas: "herramientas", automatizar: "automatizar" };
    for (const [k, m] of Object.entries(status.modulos)) {
      const a = document.querySelector(`.maintabs a[data-mod="${map[k] || k}"]`);
      if (a && !m.habilitado) { a.classList.add("warn"); a.title = m.aviso; }
    }
  } catch { /* la app funciona igual; solo se pierde el aviso */ }

  window.fvModuleWarning = name => (status && status.modulos[name] && !status.modulos[name].habilitado) ? status.modulos[name].aviso : null;

  try {
    const u = await FVApi.getJSON("/api/update");
    if (u.disponible) {
      const b = $("#update");
      b.classList.remove("hidden");
      b.replaceChildren(u.mensaje + " ", h("button", { class: "primary", onclick: async () => {
        const r = await (await fetch("/api/update/apply", { method: "POST" })).json();
        b.textContent = r.mensaje;
      } }, "Actualizar"));
    }
  } catch {}

  FVRouter.go();
})();
