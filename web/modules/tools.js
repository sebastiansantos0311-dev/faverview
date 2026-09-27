"use strict";
(function () {
/* Módulo Herramientas (S7): trapping, step & repeat, flexo, braille, gama extendida y prueba en pantalla. */
const { h, toast } = FV;
const root = document.getElementById("vista-herramientas");
const q = s => root.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let job = null, pdfInks = [];
const base = () => `/api/herramientas/${job}`;
const num = id => (q(id).value === "" ? null : +q(id).value);
const need = () => { if (!job) { toast("Primero sube el PDF del trabajo.", "warn"); return false; } return true; };
const fail = e => toast(e.message, "error", 8000);
const save = (blob, name) => { const a = h("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove(); };

/* pestañas */
root.querySelectorAll("#tl-tabs button").forEach(b => b.onclick = () => {
  root.querySelectorAll("#tl-tabs button").forEach(x => x.classList.toggle("active", x === b));
  root.querySelectorAll(".tl-pane").forEach(p => p.classList.toggle("hidden", p.dataset.t !== b.dataset.t));
  q("#tl-filebar").classList.toggle("hidden", ["braille", "cal"].includes(b.dataset.t));
  if (b.dataset.t === "gamut" || b.dataset.t === "cal") loadInks();
});

FVDrop.bind(q("#tl-drop"), q("#tl-drop input"), async f => {
  try {
    FV.setLoading(true);
    const r = await FVApi.postForm("/api/herramientas/pdf", { file: f });
    job = r.job_id; pdfInks = r.tintas;
    q("#tl-dropmsg").textContent = r.nombre;
    q("#tl-inks").textContent = "Tintas: " + r.tintas.map(t => t.nombre).join(", ");
    const sel = q("#tr-ink"); sel.innerHTML = ""; r.tintas.forEach(t => sel.append(h("option", {}, t.nombre)));
    ["Cyan", "Magenta", "Yellow", "Black"].forEach(n => { if (![...sel.options].some(o => o.text === n)) sel.append(h("option", {}, n)); });
  } catch (e) { fail(e); } finally { FV.setLoading(false); }
}, m => toast(m, "error"));

/* trapping */
q("#tr-go").onclick = async () => {
  if (!need()) return;
  try {
    FV.setLoading(true);
    const { job_id } = await FVApi.postJSON(`${base()}/trapping`, { proceso: q("#tr-proc").value, ancho_mm: num("#tr-w"), porcentaje: num("#tr-pct") || 100,
      tac_max: num("#tr-tac"), dpi: num("#tr-dpi") || 600, prensa: q("#tr-press").value || null, tolerancia_mm: q("#tr-press").value || num("#tr-tol") !== null ? num("#tr-tol") : null });
    const r = await FVApi.pollJob(job_id);
    const t = "?t=" + Date.now();
    const d = r.despues, tolt = Array.isArray(r.tolerancia_mm) ? r.tolerancia_mm.join("×") : r.tolerancia_mm;
    q("#tr-out").innerHTML = `<p><b style="color:${d.ok ? "#22c55e" : "#ef4444"}">${d.ok ? "✔ Sin filetes" : "✘ " + d.filetes_mm2 + " mm² de filetes"} con ±${tolt} mm</b> (sin trap: ${r.antes.filetes_mm2} mm²) · perfil ${esc(r.perfil)}</p>
      <p><b>${r.traps.length}</b> traps: ${r.traps.map(x => `${esc(x.de)} bajo ${esc(x.bajo)} (${x.regla || ""} ${x.ancho_mm} mm)`).join(" · ") || "ninguno"}</p><p class="hint">${r.avisos.map(esc).join(" ")}</p>
      <div class="bc-prev"><img style="max-width:100%" src="${base()}/trapping/mapa.png${t}" alt="Mapa de traps"></div>`;
  } catch (e) { fail(e); } finally { FV.setLoading(false); }
};
q("#tr-mis").onclick = () => {
  if (!need()) return;
  const ink = encodeURIComponent(q("#tr-ink").value), dx = num("#tr-dx") || 100, t = Date.now();
  q("#tr-out").innerHTML = `<div class="tl-two"><figure><figcaption>Sin trap (mal registro ${dx} µm)</figcaption><img src="${base()}/trapping/registro.png?tinta=${ink}&dx_um=${dx}&con_trap=false&t=${t}"></figure>
    <figure><figcaption>Con trap</figcaption><img src="${base()}/trapping/registro.png?tinta=${ink}&dx_um=${dx}&con_trap=true&t=${t}"></figure></div>`;
};
q("#tr-test").onclick = () => {
  if (!need()) return;
  q("#tr-out").innerHTML = `<figure><figcaption>Filetes (magenta) sin trap | con trap</figcaption><img style="max-width:100%;background:#fff" src="${base()}/trapping/prueba.png?t=${Date.now()}"></figure>`;
};
FVApi.getJSON("/api/prensas").then(r => { r.perfiles.forEach(p => q("#tr-press").append(h("option", { value: p.id }, `${p.nombre} (${Array.isArray(p.tolerancia_mm) ? p.tolerancia_mm.join("×") : p.tolerancia_mm} mm)`))); }).catch(() => {});
q("#tr-press").onchange = () => { const v = q("#tr-press").value; if (!v) return; FVApi.getJSON("/api/prensas/" + v).then(p => { q("#tr-tol").value = Array.isArray(p.tolerancia_mm) ? p.tolerancia_mm[0] : p.tolerancia_mm; }); };
q("#tr-exp").onclick = async () => {
  if (!need()) return;
  try { FV.setLoading(true); save(await (await FVApi.api(`${base()}/trapping/exportar`, { method: "POST" })).blob(), "trapping.zip"); } catch (e) { fail(e); } finally { FV.setLoading(false); }
};

/* step & repeat */
q("#st-go").onclick = async () => {
  if (!need()) return;
  try {
    FV.setLoading(true);
    const r = await FVApi.postJSON(`${base()}/imponer`, { hoja_ancho: num("#st-w"), hoja_alto: num("#st-h"), columnas: num("#st-c"), filas: num("#st-r"),
      gap_x: num("#st-gx") ?? 3, gap_y: num("#st-gy") ?? 3, margen: q("#st-m").value.split(",").map(Number), rot_filas: q("#st-rf").value.split(",").map(Number),
      desfase_fila_mm: num("#st-sf") || 0, marcas: { registro: q("#st-reg").checked, corte: q("#st-cut").checked, barra_color: q("#st-bar").checked, texto: q("#st-txt").checked, microdots: q("#st-mic").checked } });
    q("#st-out").innerHTML = `<p>${r.repeticiones} repeticiones (${r.columnas} × ${r.filas}) · etiqueta ${r.etiqueta_mm.join(" × ")} mm · aprovechamiento ${r.aprovechamiento_pct} %</p>
      <div class="bc-prev"><img style="max-width:100%" src="${base()}/imposicion.png?dpi=90&t=${Date.now()}" alt="Imposición"></div>`;
    q("#st-dl").href = `${base()}/imposicion.pdf`; q("#st-dl").classList.remove("hidden");
  } catch (e) { fail(e); } finally { FV.setLoading(false); }
};

/* flexo */
q("#fx-calc").onclick = async () => {
  try { const r = await FVApi.getJSON(`/api/herramientas/flexo/calcular?k=${num("#fx-k")}&repeticion=${num("#fx-r")}`); q("#fx-d").value = r.distorsion_pct; q("#fx-out").textContent = `D = ${r.distorsion_pct} %. ${r.nota}`; } catch (e) { fail(e); }
};
q("#fx-go").onclick = async () => {
  if (!need()) return;
  try {
    FV.setLoading(true);
    const r = await FVApi.postJSON(`${base()}/flexo`, { distorsion_pct: num("#fx-d"), k: num("#fx-k"), repeticion: num("#fx-r"), direccion: q("#fx-dir").value });
    q("#fx-out").innerHTML = `Distorsión ${r.distorsion_pct} % (${r.direccion}).<br>${r.paginas.map(p => `Pág. ${p.pagina}: ${p.antes_mm.join(" × ")} → ${p.despues_mm.join(" × ")} mm`).join("<br>")}<br><small>${esc(r.nota)}</small>`;
    q("#fx-dl").href = `${base()}/flexo.pdf`; q("#fx-dl").classList.remove("hidden");
  } catch (e) { fail(e); } finally { FV.setLoading(false); }
};

/* braille */
let brT = null;
async function brPreview() {
  try {
    const r = await FVApi.postJSON("/api/herramientas/braille", { texto: q("#br-txt").value, ancho_mm: num("#br-w") || 60 });
    q("#br-prev").innerHTML = r.svg;
    const svg = q("#br-prev svg"); if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); svg.style.width = Math.min(r.ancho_mm * 5, 520) + "px"; }
    q("#br-info").innerHTML = `${r.celdas} celdas · ${r.lineas} línea(s) · ${r.ancho_mm} × ${r.alto_mm} mm<br><span style="font-size:22px">${esc(r.unicode).replace(/\n/g, "<br>")}</span><br><small>${r.avisos.map(esc).join(" ")}</small>`;
  } catch (e) { q("#br-prev").innerHTML = ""; q("#br-info").textContent = e.message; }
}
["#br-txt", "#br-w"].forEach(s => q(s).oninput = () => { clearTimeout(brT); brT = setTimeout(brPreview, 300); });
const brDl = async (fmt, name) => { try { save(await (await FVApi.api("/api/herramientas/braille", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto: q("#br-txt").value, ancho_mm: num("#br-w") || 60, formato: fmt }) })).blob(), name); } catch (e) { fail(e); } };
q("#br-pdf").onclick = () => brDl("pdf", "braille.pdf");
q("#br-svg").onclick = () => brDl("svg", "braille.svg");
brPreview();

/* gama extendida */
let fixed = [];
async function loadInks() {
  if (fixed.length) return;
  const box = q("#gm-inks"); box.innerHTML = "";
  const box2 = q("#cl-inks"); box2.innerHTML = "";
  const libs = await FVApi.getJSON("/api/tintas");
  for (const l of libs) {
    const lib = await FVApi.getJSON("/api/tintas/" + encodeURIComponent(l.nombre));
    lib.inks.filter(i => i.lab && (i.kind === "process" || i.kind === "spot")).forEach(i => {
      const cb = h("input", { type: "checkbox", checked: i.kind === "process" });
      fixed.push({ ink: i, cb });
      box.append(h("label", { class: "si-ink" }, cb, h("span", { class: "sp-sw", style: { background: i.swatch || "#999" } }), " " + i.name));
      const cb2 = h("input", { type: "checkbox", checked: i.kind === "process" }); fixed[fixed.length - 1].cb2 = cb2;
      box2.append(h("label", { class: "si-ink" }, cb2, h("span", { class: "sp-sw", style: { background: i.swatch || "#999" } }), " " + i.name));
    });
  }
  if (!fixed.length) box.textContent = "No hay tintas con Lab en tus bibliotecas (pantalla Tintas).";
}
q("#gm-go").onclick = async () => {
  if (!need()) return;
  const sel = fixed.filter(f => f.cb.checked).map(f => ({ name: f.ink.name, lab: f.ink.lab }));
  if (sel.length < 3) return toast("Marca al menos 3 tintas para el juego fijo.", "warn");
  try {
    FV.setLoading(true);
    const { job_id } = await FVApi.postJSON(`${base()}/gamut`, { fijas: sel, max_tintas: +q("#gm-max").value });
    const r = await FVApi.pollJob(job_id);
    const col = { verde: "#22c55e", amarillo: "#eab308", rojo: "#ef4444" };
    q("#gm-out").innerHTML = `<table class="tb"><tr><th>Directa</th><th>Receta</th><th>ΔE</th><th></th></tr>${r.tabla.map(t =>
      `<tr><td>${esc(t.nombre)}</td><td>${Object.entries(t.receta).map(([k, v]) => `${esc(k)} ${v} %`).join(" + ")}</td><td>${t.de}</td><td style="color:${col[t.semaforo]}">● ${t.semaforo}${t.reproducible ? "" : " (no reproducible con este juego)"}</td></tr>`).join("")}</table><p class="hint">${esc(r.nota)}</p>`;
  } catch (e) { fail(e); } finally { FV.setLoading(false); }
};
q("#gm-apply").onclick = async () => {
  if (!need()) return;
  try {
    const r = await FVApi.api(`${base()}/gamut/aplicar?solo_reproducibles=true`, { method: "POST" }).then(x => x.json());
    toast(`Convertidas: ${r.convertidas.length}. Omitidas: ${r.omitidas.length}.`, "ok", 7000);
    q("#gm-dl").href = `${base()}/gamut.pdf`; q("#gm-dl").classList.remove("hidden");
  } catch (e) { fail(e); }
};

/* calibración */
const calInks = () => fixed.filter(f => f.cb2 && f.cb2.checked).map(f => ({ name: f.ink.name, lab: f.ink.lab }));
async function calPost(url, name) {
  const t = calInks(); if (t.length < 1) return toast("Marca las tintas del gráfico.", "warn");
  try { save(await (await FVApi.api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tintas: t }) })).blob(), name); } catch (e) { fail(e); }
}
q("#cl-chart").onclick = () => calPost("/api/herramientas/calibracion/grafico", "grafico_calibracion.pdf");
q("#cl-tpl").onclick = () => calPost("/api/herramientas/calibracion/plantilla", "plantilla_medidas.csv");
FVDrop.bind(q("#cl-drop"), q("#cl-drop input"), async f => {
  const t = calInks(); if (!t.length) return toast("Marca las tintas del gráfico.", "warn");
  try {
    const fd = new FormData(); fd.append("file", f);
    const r = await (await FVApi.api(`/api/herramientas/calibracion/ajustar?tintas=${encodeURIComponent(JSON.stringify(t))}&nombre=${encodeURIComponent(q("#cl-name").value)}`, { method: "POST", body: fd })).json();
    q("#cl-out").innerHTML = `Perfil guardado. Factor n = ${r.n} · error medio ΔE = ${r.error_medio_de}<br>` + Object.entries(r.tintas).map(([k, v]) => `${esc(k)}: ganancia en el 50 % ${(v.g50 * 100).toFixed(1)} %`).join("<br>");
  } catch (e) { fail(e); }
}, m => toast(m, "error"));

/* prueba en pantalla */
FVApi.getJSON("/api/herramientas/sustratos").then(s => Object.keys(s).forEach(k => q("#pr-sub").append(h("option", {}, k))));
q("#pr-go").onclick = () => {
  if (!need()) return;
  FV.setLoading(true);
  const im = q("#pr-img");
  im.onload = im.onerror = () => FV.setLoading(false);
  im.src = `${base()}/prueba.png?sustrato=${encodeURIComponent(q("#pr-sub").value)}&textura=${q("#pr-tex").value}&ganancia=${num("#pr-g") || 0}&sin_blanco=${q("#pr-nw").checked}&t=${Date.now()}`;
};
})();
