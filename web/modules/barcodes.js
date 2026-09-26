"use strict";
(function () {
/* Módulo Códigos de barras (S6): generar, verificar y lote. */
const { h, toast } = FV;
const root = document.getElementById("vista-codigos");
const q = s => root.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let inks = [], timer = null;

root.querySelectorAll(".sep-tabs button").forEach(b => b.onclick = () => {
  root.querySelectorAll(".sep-tabs button").forEach(x => x.classList.toggle("active", x === b));
  ["gen", "ver", "lote"].forEach(k => q("#bc-" + k).classList.toggle("hidden", k !== b.dataset.sub));
});

async function init() {
  const tipos = await FVApi.getJSON("/api/codigos/tipos");
  const sel = q("#bc-tipo"); tipos.forEach(t => sel.append(h("option", { value: t.id }, t.nombre)));
  try {
    const libs = await FVApi.getJSON("/api/tintas");
    for (const l of libs) {
      const lib = await FVApi.getJSON("/api/tintas/" + encodeURIComponent(l.nombre));
      lib.inks.filter(i => i.lab && i.kind !== "white" && i.kind !== "varnish").forEach(i => { inks.push(i); q("#bc-ink").append(h("option", { value: inks.length - 1 }, `${i.name} (${l.nombre})`)); });
    }
  } catch {}
  ["#bc-tipo", "#bc-datos", "#bc-mag", "#bc-x", "#bc-alt", "#bc-bwr", "#bc-txt", "#bc-ink"].forEach(s => q(s).oninput = () => { clearTimeout(timer); timer = setTimeout(preview, 300); });
  q("#bc-datos").value = "590123412345";
  preview();
}
function body(formato) {
  const ink = q("#bc-ink").value === "" ? null : inks[+q("#bc-ink").value];
  const v = id => q(id).value === "" ? null : +q(id).value;
  return { tipo: q("#bc-tipo").value, datos: q("#bc-datos").value, magnificacion: (v("#bc-mag") || 100) / 100, x_mm: v("#bc-x"), altura_mm: v("#bc-alt"),
    bwr_um: v("#bc-bwr") || 0, texto_legible: q("#bc-txt").checked, tinta: ink ? { name: ink.name, lab: ink.lab } : null, formato };
}
async function preview() {
  try {
    const r = await FVApi.postJSON("/api/codigos/generar", body("vista"));
    q("#bc-prev").innerHTML = r.svg;
    const svg = q("#bc-prev svg"); if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); svg.style.width = Math.min(r.ancho_mm * 6, 520) + "px"; }
    q("#bc-warn").innerHTML = `${r.ancho_mm} × ${r.alto_mm} mm · módulo X ${r.x_mm} mm` + (r.avisos.length ? "<br>" + r.avisos.map(esc).join("<br>") : "");
    q("#bc-warn").classList.remove("errtxt");
  } catch (e) { q("#bc-prev").innerHTML = ""; q("#bc-warn").textContent = e.message; q("#bc-warn").classList.add("errtxt"); }
}
async function download(fmt, name) {
  try {
    const r = await FVApi.api("/api/codigos/generar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body(fmt)) });
    save(await r.blob(), name);
  } catch (e) { toast(e.message, "error", 7000); }
}
function save(blob, name) { const a = h("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove(); }
q("#bc-pdf").onclick = () => download("pdf", "codigo.pdf");
q("#bc-svg").onclick = () => download("svg", "codigo.svg");
q("#bc-eps").onclick = () => download("eps", "codigo.eps");

FVDrop.bind(q("#bc-drop"), q("#bc-drop input"), async f => {
  try {
    FV.setLoading(true);
    const r = await FVApi.postForm("/api/codigos/verificar", { file: f, dpi: q("#bc-vdpi").value, direccion: q("#bc-dir").value });
    const box = q("#bc-res"); box.innerHTML = "";
    box.append(h("p", {}, r.mensaje), h("p", { class: "hint" }, r.nota));
    r.codigos.forEach(c => box.append(h("div", { class: "sp-issue " + (c.avisos.some(a => a.severidad === "error") ? "error" : "") },
      h("b", {}, `${c.formato}: ${c.contenido}`), h("br"),
      `Grado estimado: ${c.grado.letra} (${Object.entries(c.grado.parciales).map(([k, v]) => k + " " + v).join(", ")})`, h("br"),
      c.x_mm ? `Módulo X ${c.x_mm} mm` + (c.magnificacion_pct ? ` · magnificación ${c.magnificacion_pct} %` : "") : "",
      c.silencio_modulos ? ` · silencio ${c.silencio_modulos.izq}/${c.silencio_modulos.der} módulos` : "",
      c.contraste_luz_roja_pct != null ? ` · contraste en luz roja ${c.contraste_luz_roja_pct} %` : "",
      ...c.avisos.map(a => h("div", {}, (a.severidad === "error" ? "✖ " : "⚠ ") + a.mensaje)))));
  } catch (e) { toast(e.message, "error", 8000); } finally { FV.setLoading(false); }
}, m => toast(m, "error"));

FVDrop.bind(q("#bc-ldrop"), q("#bc-ldrop input"), async f => {
  try {
    FV.setLoading(true);
    const fd = new FormData(); fd.append("file", f); fd.append("hoja", q("#bc-hoja").checked);
    const r = await FVApi.api("/api/codigos/lote", { method: "POST", body: fd });
    const n = r.headers.get("X-Errores");
    save(await r.blob(), "codigos.zip");
    q("#bc-lmsg").textContent = n && n !== "0" ? `Listo. ${n} fila(s) con error: mira errores.txt dentro del ZIP.` : "Listo: se descargó codigos.zip.";
  } catch (e) { toast(e.message, "error", 8000); } finally { FV.setLoading(false); }
}, m => toast(m, "error"));
init();
})();
