"use strict";
(function () {
/* Módulo Automatizar (S8): editor de recetas, ejecución sobre archivo/carpeta y carpetas vigiladas. */
const { h, toast } = FV;
const root = document.getElementById("vista-automatizar");
const q = s => root.querySelector(s);
let catalog = [], profiles = [], recipes = [], current = { id: "", nombre: "Nueva receta", descripcion: "", pasos: [] }, dragFrom = null, watchTimer = null;
const fail = e => toast(e.message, "error", 8000);
const cat = id => catalog.find(c => c.id === id);
const save = (blob, name) => { const a = h("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove(); };
const slug = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "receta";

async function init() {
  catalog = await FVApi.getJSON("/api/automatizar/catalogo");
  try { profiles = await FVApi.getJSON("/api/preflight/perfiles"); } catch {}
  catalog.forEach(c => q("#au-add").append(h("option", { value: c.id }, `${c.id} — ${c.descripcion}`)));
  await loadList();
  const first = recipes[0]; if (first) await open(first.id);
  poll();
}
async function loadList() {
  recipes = await FVApi.getJSON("/api/automatizar/recetas");
  const box = q("#au-list"); box.innerHTML = "";
  recipes.forEach(r => box.append(h("div", { class: "sp-ink" + (r.id === current.id ? " sel" : ""), onclick: () => open(r.id) },
    h("span", { class: "sp-nm", title: r.descripcion }, r.nombre), h("small", {}, `${r.pasos} pasos${r.propia ? " · tuya" : ""}`))));
}
async function open(id) {
  current = { id, ...(await FVApi.getJSON("/api/automatizar/recetas/" + encodeURIComponent(id))) };
  render(); loadList();
}
function render() {
  q("#au-name").value = current.nombre || ""; q("#au-desc").value = current.descripcion || "";
  const box = q("#au-steps"); box.innerHTML = "";
  current.pasos.forEach((p, i) => {
    const key = p.modulo && !p.accion.includes(".") ? `${p.modulo}.${p.accion}` : p.accion;
    const c = cat(key);
    const params = p.parametros || (p.parametros = {});
    const card = h("div", { class: "au-step", draggable: "true",
      ondragstart: () => { dragFrom = i; }, ondragover: e => e.preventDefault(),
      ondrop: () => { if (dragFrom === null || dragFrom === i) return; const [m] = current.pasos.splice(dragFrom, 1); current.pasos.splice(i, 0, m); dragFrom = null; render(); } },
      h("div", { class: "au-head" }, h("b", {}, `${i + 1}. ${key}`), h("span", { class: "hint" }, c ? " — " + c.descripcion : " (acción desconocida)"), h("span", { class: "sp-gap" }),
        h("button", { class: "ghost mini", title: "Subir", onclick: () => move(i, -1) }, "↑"), h("button", { class: "ghost mini", title: "Bajar", onclick: () => move(i, 1) }, "↓"),
        h("button", { class: "ghost mini", title: "Quitar", onclick: () => { current.pasos.splice(i, 1); render(); } }, "✕")),
      h("div", { class: "au-params" }, (c ? c.parametros : []).map(pp => field(pp, params))));
    box.append(card);
  });
  if (!current.pasos.length) box.append(h("p", { class: "hint" }, "Sin pasos: añade uno con el selector de abajo."));
}
function move(i, d) { const j = i + d; if (j < 0 || j >= current.pasos.length) return; [current.pasos[i], current.pasos[j]] = [current.pasos[j], current.pasos[i]]; render(); }
function field(pp, params) {
  const v = params[pp.nombre] !== undefined ? params[pp.nombre] : pp.defecto;
  const set = val => { if (val === "" || val === null || (Array.isArray(val) && !val.length && pp.defecto === null)) delete params[pp.nombre]; else params[pp.nombre] = val; };
  let inp;
  if (pp.tipo === "bool") inp = h("input", { type: "checkbox", checked: !!v, onchange: e => set(e.target.checked) });
  else if (pp.tipo === "numero") inp = h("input", { type: "number", step: "any", class: "num", value: v ?? "", onchange: e => set(e.target.value === "" ? "" : +e.target.value) });
  else if (pp.tipo === "perfil") inp = h("select", { onchange: e => set(e.target.value) }, profiles.map(p => h("option", { value: p.id, selected: p.id === v }, p.nombre)));
  else if (pp.tipo === "lista") inp = h("input", { value: (v || []).join(", "), onchange: e => set(e.target.value.split(",").map(x => x.trim()).filter(Boolean)) });
  else if (pp.tipo === "json") inp = h("textarea", { rows: 2, onchange: e => { try { set(JSON.parse(e.target.value)); e.target.style.borderColor = ""; } catch { e.target.style.borderColor = "#ef4444"; } } }, JSON.stringify(v ?? {}));
  else inp = h("input", { value: v ?? "", onchange: e => set(e.target.value) });
  return h("label", { class: "au-f", title: pp.ayuda }, h("span", {}, pp.nombre), inp);
}
q("#au-addb").onclick = () => { current.pasos.push({ accion: q("#au-add").value, parametros: {} }); render(); };
q("#au-new").onclick = () => { current = { id: "", nombre: "Nueva receta", descripcion: "", pasos: [] }; render(); loadList(); };
q("#au-name").oninput = () => current.nombre = q("#au-name").value;
q("#au-desc").oninput = () => current.descripcion = q("#au-desc").value;
q("#au-save").onclick = async () => {
  try {
    const id = current.id && recipes.find(r => r.id === current.id && r.propia) ? current.id : slug(current.nombre);
    const { id: _, ...rec } = current;
    await FVApi.api(`/api/automatizar/recetas/${encodeURIComponent(id)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ receta: rec }) });
    current.id = id; toast("Receta guardada.", "ok"); loadList();
  } catch (e) { fail(e); }
};
q("#au-del").onclick = async () => {
  try { await FVApi.api(`/api/automatizar/recetas/${encodeURIComponent(current.id)}`, { method: "DELETE" }); toast("Receta borrada.", "ok"); current = { id: "", nombre: "Nueva receta", descripcion: "", pasos: [] }; render(); loadList(); } catch (e) { fail(e); }
};
q("#au-exp").onclick = () => { const { id, ...rec } = current; save(new Blob([JSON.stringify(rec, null, 1)], { type: "application/json" }), slug(current.nombre) + ".json"); };
q("#au-imp").onclick = () => q("#au-impf").click();
q("#au-impf").onchange = async e => {
  try {
    const rec = JSON.parse(await e.target.files[0].text());
    const v = await FVApi.postJSON("/api/automatizar/validar", { receta: rec });
    if (v.errores.length) return toast("La receta importada tiene problemas: " + v.errores.join(" "), "error", 9000);
    current = { id: "", ...rec }; render(); toast("Receta importada: revisa y guárdala.", "ok");
  } catch (er) { fail(er); }
};

/* ejecución */
const log = t => { q("#au-log").textContent = t; };
function recipeBody() { const { id, ...rec } = current; return rec; }
FVDrop.bind(q("#au-drop"), q("#au-drop input"), async f => {
  try {
    FV.setLoading(true); q("#au-dl").classList.add("hidden");
    const fd = new FormData(); fd.append("file", f); fd.append("receta_json", JSON.stringify(recipeBody()));
    const { job_id } = await (await FVApi.api("/api/automatizar/ejecutar", { method: "POST", body: fd })).json();
    const r = await FVApi.pollJob(job_id);
    log(`Estado: ${r.estado}${r.motivo ? " — " + r.motivo : ""}\n\n` + r.log.join("\n"));
    if (r.salidas.length) { q("#au-dl").href = `/api/automatizar/descargar/${job_id}`; q("#au-dl").classList.remove("hidden"); }
  } catch (e) { fail(e); } finally { FV.setLoading(false); }
}, m => toast(m, "error"));
q("#au-folder").onclick = async () => {
  try {
    FV.setLoading(true);
    const { job_id } = await FVApi.postJSON("/api/automatizar/carpeta", { receta: recipeBody(), entrada: q("#au-in").value, salida: q("#au-out").value });
    const r = await FVApi.pollJob(job_id);
    log(`Lote terminado: ${r.ok} correctos, ${r.detenidos} detenidos, ${r.errores} con error de ${r.archivos}.\nResumen: ${r.resumen}\n\n` + r.resultados.map(x => `${x.archivo}: ${x.estado}${x.motivo ? " — " + x.motivo : ""}`).join("\n"));
  } catch (e) { fail(e); } finally { FV.setLoading(false); }
};
q("#au-watch").onclick = async () => {
  try { await FVApi.postJSON("/api/automatizar/vigilar", { id: "w" + Date.now(), receta: recipeBody(), entrada: q("#au-in").value, salida: q("#au-out").value }); toast("Vigilando la carpeta de entrada.", "ok"); poll(); } catch (e) { fail(e); }
};
async function poll() {
  clearTimeout(watchTimer);
  try {
    const w = await FVApi.getJSON("/api/automatizar/vigilar");
    const box = q("#au-watching"); box.innerHTML = "";
    w.forEach(x => box.append(h("div", {}, `Vigilando ${x.entrada} → ${x.salida} (${x.recipe}). Procesados: ${x.procesados.length}` + (x.en_curso ? ` · en curso: ${x.en_curso}` : ""), " ",
      h("button", { class: "ghost mini", onclick: async () => { await FVApi.api("/api/automatizar/vigilar/" + x.id, { method: "DELETE" }); poll(); } }, "Detener"),
      h("div", { class: "hint" }, x.procesados.slice(-5).map(p => `${p.hora} ${p.archivo}: ${p.estado}${p.motivo ? " — " + p.motivo : ""}`).join(" | ")))));
  } catch {}
  if (root.offsetParent !== null || true) watchTimer = setTimeout(poll, 4000);
}
init().catch(fail);
})();
