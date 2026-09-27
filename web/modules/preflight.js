"use strict";
(function () {
/* Módulo Preflight (S6): perfiles, resultados por severidad, zoom a la zona y correcciones seguras. */
const { h, toast } = FV;
const root = document.getElementById("vista-preflight");
const q = s => root.querySelector(s);
let job = null, res = null, pane = null;
const viewer = new FVViewer();
const stage = h("div", { class: "stage" });
const img = h("img", { draggable: "false" });
const overlay = h("div", { class: "sp-ov" });
stage.append(img, overlay);
const base = () => `/api/preflight/${job}`;
const err = m => { const b = q("#pf-err"); b.textContent = m || ""; b.classList.toggle("hidden", !m); };
const SEV = { error: "Errores", advertencia: "Advertencias", info: "Información" };

FVApi.getJSON("/api/preflight/perfiles").then(ps => {
  const sel = q("#pf-prof"); sel.innerHTML = "";
  ps.forEach(p => sel.append(h("option", { value: p.id, title: p.descripcion }, p.nombre)));
});

FVDrop.bind(q("#pf-drop"), q("#pf-drop input"), async f => {
  err("");
  try {
    FV.setLoading(true);
    const r = await FVApi.postForm("/api/preflight", { file: f });
    job = r.job_id; q("#pf-name").textContent = r.nombre;
    const sel = q("#pf-page"); sel.innerHTML = "";
    for (let i = 1; i <= r.paginas; i++) sel.append(h("option", { value: i }, i));
    q("#pf-setup").classList.add("hidden"); q("#pf-main").classList.remove("hidden");
    await run();
  } catch (e) { err(e.message); } finally { FV.setLoading(false); }
}, err);

async function run() {
  try {
    FV.setLoading(true);
    const perfil = q("#pf-prof").value || "offset_hoja";
    const { job_id } = await (await FVApi.api(`${base()}/revisar?perfil=${encodeURIComponent(perfil)}`, { method: "POST" })).json();
    res = await FVApi.pollJob(job_id);
    q("#pf-rep").href = `${base()}/reporte?perfil=${encodeURIComponent(perfil)}`;
    render(); loadPage(true);
  } catch (e) { toast(e.message, "error", 8000); } finally { FV.setLoading(false); }
}

function render() {
  const r = res.resumen;
  q("#pf-sum").textContent = `· ${r.error} errores · ${r.advertencia} advertencias`;
  const box = q("#pf-list"); box.innerHTML = "";
  if (!res.hallazgos.length) box.append(h("p", { class: "hint" }, "Sin problemas con este perfil."));
  for (const sev of Object.keys(SEV)) {
    const items = res.hallazgos.filter(f => f.severidad === sev);
    if (!items.length) continue;
    box.append(h("h4", {}, `${SEV[sev]} (${items.length})`));
    items.forEach(f => box.append(h("div", { class: "sp-issue " + f.severidad, onclick: () => go(f) },
      h("b", {}, f.nombre), ` · pág. ${f.pagina}`, h("br"), f.mensaje)));
  }
  q("#pf-notes").textContent = (res.notas || []).join(" ");
}

function go(f) {
  if (String(f.pagina) !== q("#pf-page").value) { q("#pf-page").value = f.pagina; loadPage(false, () => zoom(f)); } else zoom(f);
}
function zoom(f) { if (f.bbox) viewer.zoomToRect(...f.bbox); }

function loadPage(fit, cb) {
  const p = +q("#pf-page").value;
  img.onload = () => {
    if (fit || !pane) {
      const box = q("#pf-viewer"); box.innerHTML = "";
      const el = h("div", { class: "pane" }); el.append(stage); box.append(el);
      viewer.reset(img.naturalWidth, img.naturalHeight, res.dpi);
      pane = viewer.attach(el, stage);
      stage.style.width = img.naturalWidth + "px"; stage.style.height = img.naturalHeight + "px";
      viewer.fit();
    }
    overlay.innerHTML = "";
    res.hallazgos.filter(f => f.bbox && f.pagina === p).forEach(f => {
      const [x, y, w, hh] = f.bbox;
      overlay.append(h("div", { class: "sp-box " + (f.severidad === "error" ? "error" : ""), style: { left: x + "px", top: y + "px", width: w + "px", height: hh + "px" } }));
    });
    if (cb) cb();
  };
  img.src = `${base()}/pagina.png?pagina=${p}&t=${Date.now()}`;
}
q("#pf-page").onchange = () => loadPage(true);
q("#pf-run").onclick = run;
q("#pf-prof").onchange = run;
q("#pf-new").onclick = () => { q("#pf-main").classList.add("hidden"); q("#pf-setup").classList.remove("hidden"); pane = null; job = null; };

q("#pf-fix").onclick = async () => {
  const av = await FVApi.getJSON("/api/preflight/correcciones");
  const checks = {};
  const body = h("div", {}, h("p", {}, "Las correcciones se aplican a una copia; tu archivo original no se toca. No se pueden incrustar fuentes que faltan."),
    Object.entries(av).map(([k, t]) => h("label", { class: "si-ink" }, checks[k] = h("input", { type: "checkbox" }), " " + t)));
  const bleed = h("input", { type: "number", value: 3, min: 0, step: 0.5, class: "num" });
  body.append(h("label", {}, "Sangrado (mm) para las cajas ", bleed));
  FV.dialog("Correcciones seguras", body, [{ label: "Cancelar" }, { label: "Aplicar", primary: true, onclick: async close => {
    close();
    const c = {};
    for (const [k, el] of Object.entries(checks)) if (el.checked) c[k] = k === "cajas" ? { sangrado_mm: +bleed.value } : true;
    if (!Object.keys(c).length) return toast("Elige al menos una corrección.", "warn");
    try {
      FV.setLoading(true);
      const r = await FVApi.postJSON(`${base()}/corregir`, { correcciones: c, perfil: q("#pf-prof").value || "offset_hoja" });
      toast(`Listo. Antes: ${r.antes.error} errores / ${r.antes.advertencia} avisos. Después: ${r.despues.error} / ${r.despues.advertencia}. Parecido visual: ${(r.similitud_visual * 100).toFixed(1)} %.`, "ok", 9000);
      q("#pf-dl").href = `${base()}/descargar`; q("#pf-dl").classList.remove("hidden"); q("#pf-undo").classList.remove("hidden");
      await run();
    } catch (e) { toast(e.message, "error", 8000); } finally { FV.setLoading(false); }
  } }]);
};
q("#pf-undo").onclick = async () => { await FVApi.postJSON(`${base()}/deshacer`, {}); q("#pf-dl").classList.add("hidden"); q("#pf-undo").classList.add("hidden"); run(); };
FVViewer.bindShortcuts(() => (q("#pf-viewer") && q("#pf-viewer").offsetParent ? viewer : null));
})();
