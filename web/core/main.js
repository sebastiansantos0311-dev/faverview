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

  /* aviso de actualización: versión nueva, novedades y botón Actualizar */
  function showUpdate(u) {
    const b = $("#update");
    if (!u.disponible) { b.classList.add("hidden"); return; }
    b.classList.remove("hidden");
    const kids = [u.mensaje + " ", h("button", { class: "primary", onclick: async () => {
      const r = await (await fetch("/api/update/apply", { method: "POST" })).json();
      b.textContent = r.mensaje;
    } }, "Actualizar")];
    if (u.novedades && u.novedades.length) {
      kids.push(h("details", {}, h("summary", {}, "Novedades" + (u.version_nueva ? ` de la versión ${u.version_nueva}` : "")),
        h("ul", {}, ...u.novedades.map(t => h("li", {}, t)))));
    }
    b.replaceChildren(...kids);
  }
  try { showUpdate(await FVApi.getJSON("/api/update")); } catch {}

  $("#check-updates").addEventListener("click", async () => {
    const msg = $("#check-updates-msg");
    msg.textContent = "Buscando…";
    try {
      const u = await (await fetch("/api/update/check", { method: "POST" })).json();
      showUpdate(u);
      msg.textContent = u.error ? u.error : (u.disponible ? "Hay una versión nueva (arriba)." : `Tienes la última versión (${u.version}).`);
    } catch { msg.textContent = "No se pudo comprobar."; }
  });

  /* «Enviar a…» */
  const send = $("#send-to");
  window.addEventListener("fv:file", e => {
    const f = e.detail;
    send.innerHTML = "";
    send.append(h("option", { value: "" }, "Enviar a…"));
    FVRouter.targets(f).filter(([m]) => m !== FVRouter.current_name()).forEach(([m, t]) => send.append(h("option", { value: m }, t)));
    send.classList.remove("hidden");
  });
  send.addEventListener("change", () => { if (send.value && FVDrop.last) FVRouter.send(send.value, FVDrop.last.file); send.value = ""; });
  /* cancelar el trabajo en curso */
  $("#loading-cancel").addEventListener("click", async () => { if (FVApi.currentJob) { try { await fetch(`/api/jobs/${FVApi.currentJob}/cancel`, { method: "POST" }); } catch {} } });

  FVRouter.go();
})();
