"use strict";
(function () {
/* Separar colores → Imagen (S3): asistente de 4 pasos con vista previa en vivo a baja resolución. */
const { h, toast } = FV;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const root = document.getElementById("vista-separar");
const q = s => root.querySelector(s);
const box = q("#sub-img");

box.innerHTML = `
<section id="si-setup" class="setup">
  <div class="drop" id="si-drop"><div class="drop-title">Imagen a separar</div>
    <div class="drop-hint">Arrastra aquí o haz clic<br><small>JPG, PNG, TIFF, BMP o WEBP · logos, ilustraciones o fotos</small></div>
    <input type="file" hidden accept=".jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp"></div>
  <div id="si-err" class="error hidden"></div>
</section>
<section id="si-main" class="hidden">
  <div class="sp-grid si-grid">
    <aside class="sp-side">
      <h3>1 · Imagen y sustrato</h3>
      <div id="si-info" class="hint"></div>
      <label>Sustrato <select id="si-sub"></select></label>
      <h3>2 · Modo y tintas</h3>
      <label>Modo <select id="si-modo">
        <option value="planas">Tintas planas (logos)</option><option value="proceso">Proceso simulado (fotos, pocas tintas)</option>
        <option value="indice">Índice (paleta + difusión)</option><option value="cmyk">CMYK (perfil ICC)</option></select></label>
      <div id="si-libs"></div>
      <h3>3 · Ajustes</h3>
      <div id="si-adj"></div>
      <div id="si-trapbox"><label><input id="si-trap" type="checkbox"> Auto-trap (reventado)</label>
        <label>Perfil de máquina <select id="si-press"></select></label>
        <label>Tolerancia de movimiento (mm) <input id="si-tol" type="number" step="0.05" min="0" max="5" class="num"></label>
        <div id="si-trapmsg" class="hint">Valores orientativos: mide el movimiento real de tu máquina.</div></div>
      <h3>4 · Salida</h3>
      <label>Tramado <select id="si-tr"><option value="">Sin tramado (solo canales)</option><option value="am">AM (puntos)</option><option value="fm">FM (estocástico)</option></select></label>
      <label>lpi <input id="si-lpi" type="number" value="55" min="10" max="200" class="num"></label>
      <label>Salida (dpi) <input id="si-odpi" type="number" value="600" min="150" max="2400" class="num"></label>
      <div class="sp-actions"><button id="si-go" class="ghost">Procesar</button><button id="si-exp" class="ghost">Exportar (ZIP)</button><button id="si-new" class="ghost">Otra imagen</button></div>
    </aside>
    <div class="sp-center">
      <div class="si-view">
        <div class="sp-bar">
          <label>Ver <select id="si-ver"><option value="simulacion">Simulada</option><option value="original">Original</option><option value="dividida">Original | Simulada</option><option value="de">Mapa de error ΔE</option><option value="trap">Mapa de traps</option><option value="prueba">Prueba de movimiento (sin trap | con trap)</option></select></label>
          <label>Canal <select id="si-canal"><option value="">— ninguno —</option></select></label>
          <span id="si-stats" class="hint"></span>
        </div>
        <div class="si-imgs"><img id="si-img" alt=""><img id="si-img2" alt="" class="hidden"></div>
      </div>
    </div>
    <aside class="sp-side"><h3>Tintas</h3><div id="si-inks"></div><h3>Avisos</h3><div id="si-warn" class="hint"></div></aside>
  </div>
</section>`;

const Q = s => box.querySelector(s);
let job = null, info = null, libInks = [], picked = [], timer = null, last = null, presses = [];
const err = m => { const b = Q("#si-err"); b.textContent = m || ""; b.classList.toggle("hidden", !m); };

/* ---- pestañas PDF / Imagen ---- */
root.querySelectorAll(".sep-tabs button").forEach(b => b.onclick = () => {
  root.querySelectorAll(".sep-tabs button").forEach(x => x.classList.toggle("active", x === b));
  q("#sub-pdf").classList.toggle("hidden", b.dataset.sub !== "pdf");
  box.classList.toggle("hidden", b.dataset.sub !== "img");
});

FVDrop.bind(Q("#si-drop"), Q("#si-drop input"), async f => {
  err("");
  try {
    FV.setLoading(true);
    info = await FVApi.postForm("/api/separar/img", { file: f });
    job = info.job_id;
    Q("#si-info").textContent = `${info.nombre} · ${info.ancho}×${info.alto} px` + (info.dpi ? ` · ${Math.round(info.dpi)} ppi` : " · sin ppi (se asumen 200)");
    const sub = Q("#si-sub"); sub.innerHTML = "";
    Object.keys(info.sustratos).forEach(k => sub.append(h("option", { value: k }, k)));
    await loadLibs();
    await loadPresses();
    Q("#si-setup").classList.add("hidden"); Q("#si-main").classList.remove("hidden");
    adjust();
    await run(true);
  } catch (e) { err(e.message); } finally { FV.setLoading(false); }
}, err);

async function loadLibs() {
  const libs = await FVApi.getJSON("/api/tintas");
  const sel = h("select", { id: "si-lib", onchange: async e => { await pickLib(e.target.value); } }, libs.map(l => h("option", { value: l.nombre }, `${l.nombre} (${l.tintas})`)));
  Q("#si-libs").innerHTML = "";
  Q("#si-libs").append(h("label", {}, "Biblioteca de tintas ", sel), h("div", { id: "si-list" }));
  await pickLib(libs[0].nombre);
}
async function pickLib(name) {
  const lib = await FVApi.getJSON("/api/tintas/" + encodeURIComponent(name));
  libInks = lib.inks.filter(i => i.lab);
  picked = [];
  const list = Q("#si-list"); list.innerHTML = "";
  libInks.forEach((i, n) => list.append(h("label", { class: "si-ink" },
    h("input", { type: "checkbox", onchange: e => { e.target.checked ? picked.push(n) : picked.splice(picked.indexOf(n), 1); schedule(); } }),
    h("span", { class: "sp-sw", style: { background: i.swatch || "#999" } }), " " + i.name + (i.kind === "white" ? " (blanco)" : ""))));
  list.append(h("p", { class: "hint" }, "Planas / índice: sin marcar = paleta automática. Proceso: marca las tintas (el blanco se imprime primero)."));
}

async function loadPresses() {
  if (presses.length) return;
  const r = await FVApi.getJSON("/api/prensas");
  presses = r.perfiles;
  const sel = Q("#si-press"); sel.innerHTML = "";
  presses.forEach(p => sel.append(h("option", { value: p.id }, `${p.nombre} (${Array.isArray(p.tolerancia_mm) ? p.tolerancia_mm.join("×") : p.tolerancia_mm} mm)`)));
  sel.value = "serigrafia_textil_automatica";
  const upd = () => { const p = presses.find(x => x.id === sel.value); if (p) { Q("#si-tol").value = Array.isArray(p.tolerancia_mm) ? p.tolerancia_mm[0] : p.tolerancia_mm; Q("#si-trap").checked = ["serigrafia", "flexo"].includes(p.proceso); } };
  sel.onchange = () => { upd(); schedule(); };
  Q("#si-tol").oninput = schedule; Q("#si-trap").onchange = schedule;
  upd();
}

function adjust() {
  const m = Q("#si-modo").value, a = Q("#si-adj");
  const num = (id, label, v, min, max, step) => `<label>${label} <input id="${id}" type="number" value="${v}" min="${min}" max="${max}" step="${step}" class="num"></label>`;
  a.innerHTML = {
    planas: num("a-k", "Máx. de tintas", 8, 2, 12, 1) + num("a-fus", "Fusionar colores a ΔE <", 6, 1, 30, 1) + num("a-min", "Isla mínima (mm²)", 0.05, 0, 50, 0.01) +
      `<label><input id="a-soft" type="checkbox"> Bordes suaves</label>`,
    proceso: num("a-lam", "Ahorro de tinta (λ)", 4, 0, 20, 0.5) + num("a-pmin", "Punto mínimo %", 3, 0, 20, 1) + num("a-pmax", "Punto máximo %", 100, 50, 100, 1) +
      num("a-gam", "Gamma", 1, 0.3, 3, 0.05) + num("a-choke", "Choke del blanco (px)", 1, 0, 6, 1),
    indice: num("a-k", "Colores", 6, 2, 64, 1) + `<label>Difusión <select id="a-dif"><option value="fs">Floyd–Steinberg</option><option value="none">Sin difusión</option></select></label>`,
    cmyk: `<label>Perfil ICC <select id="a-prof">${(info.perfiles_icc || []).map(p => `<option>${p}</option>`).join("") || "<option value=''>(ninguno instalado)</option>"}</select></label>` +
      `<label>Intención <select id="a-int"><option value="relativa">Colorimétrica relativa + BPC</option><option value="perceptual">Perceptual</option></select></label>` +
      num("a-tac", "Límite TAC %", 300, 100, 400, 5) + `<label><input id="a-ks" type="checkbox"> Negro solo en sombras</label>`,
  }[m];
  a.querySelectorAll("input,select").forEach(el => el.oninput = schedule);
}
Q("#si-modo").onchange = () => { adjust(); schedule(); };
Q("#si-sub").onchange = schedule;

function val(id, d) { const e = Q("#" + id); return e ? (e.type === "checkbox" ? e.checked : (e.type === "number" ? +e.value : e.value)) : d; }
function params(previa) {
  const modo = Q("#si-modo").value;
  const tintas = picked.map(n => ({ name: libInks[n].name, lab: libInks[n].lab, opacity: libInks[n].kind === "white" ? 1 : 0 }));
  tintas.sort((a, b) => b.opacity - a.opacity);   // opacas (blanco) primero
  return { modo, sustrato: Q("#si-sub").value, tintas, previa,
    k_max: val("a-k", 8), fusionar_de: val("a-fus", 6), area_min_mm2: val("a-min", 0.05), bordes_suaves: val("a-soft", false),
    lam: val("a-lam", 4), punto_min: val("a-pmin", 3), punto_max: val("a-pmax", 100), gamma: val("a-gam", 1), choke_px: val("a-choke", 0),
    auto_trap: Q("#si-trap").checked, prensa: Q("#si-press").value || null, tolerancia_mm: Q("#si-tol").value === "" ? null : +Q("#si-tol").value,
    difusion: val("a-dif", "fs"), perfil: val("a-prof", "") || null, intencion: val("a-int", "relativa"), tac: val("a-tac", 300), negro_sombras: val("a-ks", false) };
}

function schedule() { clearTimeout(timer); timer = setTimeout(() => run(false, true), 400); }

async function run(full, previa) {
  if (!job) return;
  try {
    if (!previa) FV.setLoading(true);
    const { job_id } = await FVApi.postJSON(`/api/separar/img/${job}/procesar`, params(!!previa));
    last = await FVApi.pollJob(job_id, previa ? () => {} : undefined);
    show();
  } catch (e) { toast(e.message, "error", 7000); } finally { if (!previa) FV.setLoading(false); }
}

function show() {
  const r = last, s = r.stats;
  Q("#si-stats").textContent = Object.entries(s).filter(([k]) => k !== "modo").map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ");
  Q("#si-warn").textContent = (r.avisos || []).join(" ") || "—";
  const inks = Q("#si-inks"); inks.innerHTML = "";
  r.nombres.forEach(n => inks.append(h("div", { class: "sp-ink" }, h("span", { class: "sp-nm" }, n), h("small", {}, `${r.cobertura[n]} %`))));
  const cv = Q("#si-canal"), cur = cv.value; cv.innerHTML = '<option value="">— ninguno —</option>';
  r.nombres.forEach(n => cv.append(h("option", { value: n }, n))); cv.value = r.nombres.includes(cur) ? cur : "";
  Q("#si-ver option[value=de]").disabled = !r.de;
  const tp = r.trap;
  Q("#si-ver option[value=trap]").disabled = !tp; Q("#si-ver option[value=prueba]").disabled = !(tp && tp.ok !== null);
  Q("#si-trapmsg").innerHTML = tp ? `<b style="color:${tp.ok === false ? "#ef4444" : "#22c55e"}">${esc(tp.registro || "")}</b><br>` + tp.traps.map(t => `${esc(t.de)} bajo ${esc(t.bajo)} (${esc(t.regla)}) ${t.ancho_mm} mm`).join("<br>")
    : "Valores orientativos: mide el movimiento real de tu máquina.";
  render();
}
function render() {
  if (!last) return;
  const t = "?t=" + Date.now(), base = `/api/separar/img/${job}`;
  const v = Q("#si-ver").value, c = Q("#si-canal").value, i1 = Q("#si-img"), i2 = Q("#si-img2");
  i2.classList.add("hidden");
  if (c) { i1.src = `${base}/canal.png?nombre=${encodeURIComponent(c)}${t.replace("?", "&")}`; return; }
  if (v === "dividida") { i1.src = `${base}/original.png${t}`; i2.src = `${base}/simulacion.png${t}`; i2.classList.remove("hidden"); }
  else i1.src = `${base}/${v === "de" ? "de" : v === "trap" ? "trap" : v === "prueba" ? "prueba" : v}.png${t}`;
}
Q("#si-ver").onchange = render; Q("#si-canal").onchange = render;
Q("#si-go").onclick = () => run(false, false);
Q("#si-new").onclick = () => { Q("#si-main").classList.add("hidden"); Q("#si-setup").classList.remove("hidden"); job = null; last = null; };
Q("#si-exp").onclick = async () => {
  try {
    FV.setLoading(true);
    await run(false, false);
    const tr = Q("#si-tr").value;
    const body = { trama: tr ? { kind: tr, lpi: +Q("#si-lpi").value } : null, dpi_salida: +Q("#si-odpi").value, pdf: true };
    const r = await FVApi.api(`/api/separar/img/${job}/exportar`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const a = h("a", { href: URL.createObjectURL(await r.blob()), download: "separacion.zip" }); document.body.append(a); a.click(); a.remove();
  } catch (e) { toast(e.message, "error", 7000); } finally { FV.setLoading(false); }
};
})();
