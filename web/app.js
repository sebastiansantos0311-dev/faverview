"use strict";
/* FAVERVIEW – interfaz. JavaScript puro, sin dependencias. */

const CATS = [
  ["text", "Texto"], ["spelling", "Ortografía"], ["color", "Color"], ["visual", "Elemento visual"], ["font", "Fuente"],
];
const CAT_NAME = Object.fromEntries(CATS);
const CAT_COLOR = { text: "#ef4444", spelling: "#eab308", color: "#f97316", visual: "#3b82f6", font: "#a855f7" };
const STATUS_TXT = { aprobado: "Aprobado", revisar: "Revisar", con_errores: "Con errores" };
const SCORE_LABELS = [["visual", "Visual"], ["text", "Texto"], ["color", "Color"], ["spelling", "Ortografía"], ["font", "Fuente"]];

const $ = (s, r = document) => r.querySelector(s);
const files = { client: null, design: null };
let data = null;            // resultado actual
let mode = "side";
let view = { s: 1, tx: 0, ty: 0 };
let panes = [];
let sliderFrac = 0.5;
let ignored = new Set();
let activeCats = new Set(CATS.map(c => c[0]));
let selectedId = null;
let showIgnored = false;
let reviewMode = false;
let drawMode = false;
let verdicts = {};      // id -> "real" | "falso_positivo"
let missed = [];        // errores no detectados marcados a mano
let mode2 = "cliente";  // "cliente" | "versiones"
let lastBatch = null;
let zones = [];         // zonas a ignorar (coordenadas relativas 0–1 al diseño)
let drawKind = "missed"; // "missed" | "zone"

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") {
      for (const [sk, sv] of Object.entries(v)) sk.startsWith("--") ? el.style.setProperty(sk, sv) : (el.style[sk] = sv);
    }
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function showError(msg) {
  const b = $("#error");
  if (!msg) { b.classList.add("hidden"); return; }
  b.textContent = msg;
  b.classList.remove("hidden");
}
function setLoading(on) { $("#loading").classList.toggle("hidden", !on); if (on) setProgress("Procesando…", 0); }

async function api(url, opts) {
  let r;
  try { r = await fetch(url, opts); }
  catch { throw new Error("No se pudo conectar con FAVERVIEW. ¿Está abierta la ventana de consola?"); }
  if (!r.ok) {
    let d = "Ocurrió un error inesperado.";
    try { const j = await r.json(); if (j.detail) d = typeof j.detail === "string" ? j.detail : d; } catch {}
    throw new Error(d);
  }
  return r;
}

/* ---------- carga de archivos ---------- */
function setupDrop(kind) {
  const box = $("#drop-" + kind), input = $("input", box);
  box.addEventListener("click", e => { if (!e.target.closest(".pagesel")) input.click(); });
  input.addEventListener("change", () => input.files[0] && setFile(kind, input.files[0]));
  ["dragenter", "dragover"].forEach(ev => box.addEventListener(ev, e => { e.preventDefault(); box.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => box.addEventListener(ev, e => { e.preventDefault(); box.classList.remove("over"); }));
  box.addEventListener("drop", async e => { const f = await fileFromDrop(e.dataTransfer); if (f) setFile(kind, f); });
}

async function setFile(kind, file) {
  showError("");
  files[kind] = file;
  $("#drop-" + kind).classList.add("has-file");
  $("#file-" + kind).textContent = file.name;
  const sel = $("#pages-" + kind);
  sel.classList.add("hidden");
  if (/\.(pdf|tif|tiff)$/i.test(file.name)) {
    try {
      const fd = new FormData(); fd.append("file", file);
      const { pages } = await (await api("/api/pages", { method: "POST", body: fd })).json();
      if (pages > 1) {
        const s = $("select", sel); s.replaceChildren();
        for (let i = 1; i <= pages; i++) s.append(h("option", { value: i }, `${i} de ${pages}`));
        sel.classList.remove("hidden");
      }
    } catch (e) { showError(e.message); files[kind] = null; $("#drop-" + kind).classList.remove("has-file"); $("#file-" + kind).textContent = ""; }
  }
  $("#btn-compare").disabled = !(files.client && files.design);
  updateBatchBtn();
  suggestTemplate();
}

async function compare() {
  showError("");
  const fd = new FormData();
  let url = "/api/compare";
  if (mode2 === "versiones") {
    url = "/api/compare-versions";
    fd.append("v1_file", files.client);
    fd.append("v2_file", files.design);
    fd.append("v1_page", $("#pages-client select").value || 1);
    fd.append("v2_page", $("#pages-design select").value || 1);
  } else {
    fd.append("client_file", files.client);
    fd.append("design_file", files.design);
    fd.append("client_page", $("#pages-client select").value || 1);
    fd.append("design_page", $("#pages-design select").value || 1);
    if ($("#tpl-select").value) fd.append("template", $("#tpl-select").value);
  }
  setLoading(true);
  try {
    const j = await (await api(url, { method: "POST", body: fd })).json();
    showResult(await pollJob(j.job_id));
    loadHistory();
  } catch (e) { showError(e.message); }
  finally { setLoading(false); }
}

/* consulta el progreso por etapas hasta que termina */
async function pollJob(id) {
  for (;;) {
    const st = await (await api("/api/jobs/" + id)).json();
    setProgress(st.message, st.pct);
    if (st.status === "done") return st.result;
    if (st.status === "error") throw new Error(st.error || "Ocurrió un error inesperado.");
    await new Promise(r => setTimeout(r, 350));
  }
}
function setProgress(msg, pct) {
  $("#loading-msg").textContent = msg || "Procesando…";
  $("#loading-bar").style.width = Math.round((pct || 0) * 100) + "%";
}

async function recalc(manualPoints) {
  if (!data) return;
  if (manualPoints instanceof Event) manualPoints = null;
  showError("");
  setLoading(true);
  try {
    const body = {
      ssim_threshold: +$("#r-ssim").value, delta_e_tolerance: +$("#r-de").value, min_region_area: +$("#r-area").value,
      client_page: +($("#pages-client select").value || data.pages?.client || 1),
      design_page: +($("#pages-design select").value || data.pages?.design || 1),
      manual_points: manualPoints || data.params?.manual_points || null,
      zones: zones.length ? zones : null,
      template: null,
    };
    const j = await (await api("/api/recompute/" + data.job_id, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
    showResult(await pollJob(j.job_id), true);
  } catch (e) { showError(e.message); }
  finally { setLoading(false); }
}

/* ---------- resultado ---------- */
function showResult(res, keepUi = false) {
  data = res;
  ignored = new Set();
  selectedId = null;
  showIgnored = false;
  verdicts = {}; missed = []; drawMode = false;
  zones = (res.params && res.params.zones) ? res.params.zones.map(z => ({ ...z })) : [];
  renderMissed(); renderZones();
  if (!keepUi) activeCats = new Set(CATS.map(c => c[0]));
  $("#results").classList.remove("hidden");
  renderSummary();
  renderWarnings();
  renderFix();
  renderFilters();
  renderErrors();
  renderFonts();
  $("#btn-report").href = "/api/report/" + res.job_id;
  const p = res.params || {};
  $("#r-ssim").value = p.ssim_threshold ?? 0.85;
  $("#r-de").value = p.delta_e_tolerance ?? 10;
  $("#r-area").value = p.min_region_area ?? 150;
  updateSensLabels();
  renderViewer();
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSummary() {
  const s = data.scores, box = $("#summary");
  box.replaceChildren(
    h("div", { class: "total" },
      h("span", { class: "pct" }, s.total.toFixed(1) + "%"),
      h("span", { class: "badge " + data.status }, STATUS_TXT[data.status]),
      h("span", { class: "diffpct" }, `${(100 - s.total).toFixed(1)}% de diferencia`)),
    h("div", { class: "chips" }, SCORE_LABELS.map(([k, name]) => {
      const cat = k;
      return h("div", { class: "chip", style: { borderLeftColor: CAT_COLOR[cat] } },
        h("b", {}, s[k].toFixed(1) + "%"), h("small", {}, name));
    })),
    h("div", { class: "meta" },
      h("div", {}, `A: ${data.client_name}`), h("div", {}, `B: ${data.design_name}`),
      data.color_spaces && data.color_spaces.design
        ? h("div", {}, `Color · Diseño: ${data.color_spaces.design} · Cliente: ${data.color_spaces.client}`) : null,
      h("div", {}, `Alineación: ${alignLabel()} (${data.alignment_method || "—"})`),
      h("div", {}, `${data.differences.filter(d => !d.ignored_by_zone).length} errores · ${data.elapsed_s}s`),
      h("div", { id: "ready" })));
  renderReady();
}

function alignLabel() {
  if (!data.aligned) return "mala";
  if (data.alignment_method === "manual") return "manual";
  const q = data.alignment_quality;
  return q >= 0.6 ? "buena" : q >= 0.35 ? "regular" : "mala";
}

/* ---------- alineación manual: 4 puntos equivalentes en cada imagen ---------- */
function manualAlign() {
  if (!data) return;
  const pts = { client: [], design: [] };
  const mk = (which, src) => {
    const wrap = h("div", { class: "al-wrap" });
    const img = h("img", { src, class: "al-img" });
    wrap.append(img);
    img.addEventListener("click", e => {
      if (pts[which].length >= 4) return;
      const r = img.getBoundingClientRect();
      const x = (e.clientX - r.left) * img.naturalWidth / r.width, y = (e.clientY - r.top) * img.naturalHeight / r.height;
      pts[which].push([Math.round(x), Math.round(y)]);
      wrap.append(h("span", { class: "al-pt", style: { left: (e.clientX - r.left) + "px", top: (e.clientY - r.top) + "px" } }, pts[which].length));
      status();
    });
    return wrap;
  };
  const st = h("div", { class: "hint" });
  const status = () => { st.textContent = `Cliente: ${pts.client.length}/4 · Diseño: ${pts.design.length}/4 (mismo orden en ambos, p. ej. esquinas)`;
    ok.disabled = !(pts.client.length === 4 && pts.design.length === 4); };
  const close = () => bg.remove();
  const ok = h("button", { class: "primary", disabled: true, onclick: async () => {
    close();
    await recalc({ client: pts.client, design: pts.design });
  } }, "Aplicar y recalcular");
  const bg = h("div", { class: "dialog-bg" }, h("div", { class: "dialog wide" },
    h("b", {}, "Alineación manual: marca 4 puntos equivalentes en cada imagen"),
    h("div", { class: "al-grid" },
      h("div", {}, h("div", { class: "hint" }, "Arte del cliente (original)"), mk("client", `/api/results/${data.job_id}/${data.images.client_original}`)),
      h("div", {}, h("div", { class: "hint" }, "Mi diseño"), mk("design", imgUrl("design.png")))),
    st, h("div", { class: "row" }, h("button", { onclick: close }, "Cancelar"), ok)));
  document.body.append(bg);
  status();
}

function renderFix() {
  const box = $("#fixpanel"); box.replaceChildren();
  const f = data.fix_report; if (!f) return;
  box.append(h("div", { class: "banner fix" }, h("b", {}, "Verificación de correcciones: "), f.resumen,
    f.corregidos.length ? h("details", {}, h("summary", {}, `Errores corregidos ✔ (${f.corregidos.length})`),
      f.corregidos.map(c => h("div", { class: "hint" }, `#${c.id} · ${CAT_NAME[c.category]} · ${c.message}`))) : null,
    f.persisten.length ? h("details", { open: true }, h("summary", {}, `Siguen ✘ (${f.persisten.length})`),
      f.persisten.map(c => h("div", { class: "hint" }, h("a", { onclick: () => c.nuevo_id && selectError(c.nuevo_id, true) },
        `#${c.nuevo_id || c.id} · ${CAT_NAME[c.category]} · ${c.message}`)))) : null));
}

function applyModeLabels() {
  const ver = data && data.mode === "versiones";
  document.querySelectorAll(".pane .cap").forEach(c => {
    if (ver) c.textContent = c.textContent.replace("A · Cliente", "A · Versión 1").replace("B · Mi diseño", "B · Versión 2");
  });
}

function renderWarnings() {
  const box = $("#warnings"); box.replaceChildren();
  const list = [...data.warnings];
  if (!data.aligned) list.unshift("El arte del cliente no se pudo alinear con precisión: revisa los resultados con cuidado.");
  list.forEach(w => box.append(h("div", { class: "banner warn" }, w)));
}

function renderFilters() {
  const box = $("#filters"); box.replaceChildren();
  CATS.forEach(([k, name]) => {
    const n = data.differences.filter(d => d.category === k).length;
    const cb = h("input", { type: "checkbox", onchange: e => {
      e.target.checked ? activeCats.add(k) : activeCats.delete(k); renderErrors(); renderBoxes(); } });
    cb.checked = activeCats.has(k);
    box.append(h("label", {}, cb, h("span", { class: "dot", style: { background: CAT_COLOR[k] } }), `${name} (${n})`));
  });
}

function visibleDiffs() {
  return data.differences.filter(d => activeCats.has(d.category) && (showIgnored || (!ignored.has(d.id) && !d.ignored_by_zone)));
}

function swatch(hex, label) {
  return h("span", { class: "sw" }, h("i", { style: { background: hex } }), `${label} ${hex}`);
}

function renderErrors() {
  const box = $("#errors"); box.replaceChildren();
  const vis = visibleDiffs();
  if (!data.differences.length) box.append(h("div", { class: "empty" }, "No se encontraron diferencias. ✔"));
  else if (!vis.length) box.append(h("div", { class: "empty" }, "No hay errores con los filtros actuales."));
  CATS.forEach(([k, name]) => {
    const items = vis.filter(d => d.category === k);
    if (!items.length) return;
    const g = h("div", { class: "group" }, h("h3", {}, name, h("span", { class: "count" }, items.length)));
    items.forEach(d => g.append(errItem(d)));
    box.append(g);
  });
  const r = $("#restore");
  if (ignored.size) {
    r.classList.remove("hidden");
    r.replaceChildren(h("a", { onclick: () => { showIgnored = !showIgnored; renderErrors(); renderBoxes(); } },
      showIgnored ? "Ocultar ignorados" : `Mostrar ${ignored.size} ignorado(s)`),
      " · ", h("a", { onclick: () => { ignored.clear(); showIgnored = false; renderErrors(); renderBoxes(); } }, "Restaurar todos"));
  } else r.classList.add("hidden");
}

function errItem(d) {
  const says = [];
  if (d.category === "text") {
    says.push(h("div", { class: "says" }, "Cliente dice: ", h("b", {}, d.expected || "(nada)"),
      " · Tu diseño dice: ", h("b", {}, d.found || "(nada)")));
  } else if (d.category === "color") {
    says.push(h("div", { class: "says" }, swatch(d.expected_hex, "Cliente"), swatch(d.found_hex, "Diseño")));
  } else if (d.category === "spelling" && d.suggestions.length) {
    says.push(h("div", { class: "says" }, "Sugerencias: " + d.suggestions.join(", ")));
  } else if (d.category === "font" && d.found) {
    says.push(h("div", { class: "says" }, "Tu diseño: " + d.found));
  }
  const btns = h("div", { class: "btns" });
  if (reviewMode) {
    const v = verdicts[d.id];
    btns.append(
      h("button", { class: v === "real" ? "on-real" : "", onclick: e => { e.stopPropagation(); verdicts[d.id] = "real"; renderErrors(); } }, "✔ Real"),
      h("button", { class: v === "falso_positivo" ? "on-fp" : "", onclick: e => { e.stopPropagation(); verdicts[d.id] = "falso_positivo"; renderErrors(); } }, "✘ Falso positivo"));
  }
  if (d.category === "spelling") btns.append(h("button", { onclick: async e => {
    e.stopPropagation();
    try { await api("/api/dictionary", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ word: d.found }) });
      ignored.add(d.id); renderErrors(); renderBoxes(); } catch (er) { showError(er.message); }
  } }, "Agregar al diccionario"));
  btns.append(h("button", { onclick: e => { e.stopPropagation(); ignored.add(d.id); renderErrors(); renderBoxes(); } },
    ignored.has(d.id) ? "Ignorado" : "Ignorar"));
  return h("div", { class: "err" + (d.id === selectedId ? " sel" : "") + (d.ignored_by_zone ? " ign" : ""), "data-id": d.id,
    style: { "--col": CAT_COLOR[d.category] }, onclick: () => selectError(d.id, true) },
    h("div", { class: "top" }, h("span", { class: "num" }, d.id), h("span", { class: "msg" }, d.message.replace(/ΔE/g, "ΔE"))),
    says, btns, checklistRow(d));
}

function checklistRow(d) {
  const sel = h("select", { onclick: e => e.stopPropagation(), onchange: e => { e.stopPropagation(); setStatus(d, { status: e.target.value }); } },
    [["pendiente", "Pendiente"], ["corregido", "Corregido ✔"], ["no_aplica", "No aplica"]].map(([v, t]) => h("option", { value: v }, t)));
  sel.value = d.status || "pendiente";
  const inp = h("input", { class: "cmt", placeholder: "Comentario (opcional)", value: d.comment || "",
    onclick: e => e.stopPropagation(), onchange: e => setStatus(d, { comment: e.target.value }) });
  return h("div", { class: "checklist" }, sel, inp);
}

async function setStatus(d, patch) {
  Object.assign(d, patch);
  try {
    const r = await (await api(`/api/results/${data.job_id}/checklist`, { method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: { [d.id]: patch } }) })).json();
    renderReady(r);
  } catch (e) { showError(e.message); }
}

function readyInfo() {
  const vivos = data.differences.filter(d => !d.ignored_by_zone);
  const pend = vivos.filter(d => (d.status || "pendiente") === "pendiente").length;
  return { pendientes: pend, listo: pend === 0 };
}
function renderReady(r) {
  const el = $("#ready"); if (!el) return;
  r = r || readyInfo();
  el.className = "ready " + (r.listo ? "ok" : "pend");
  el.textContent = r.listo ? "✔ Listo para enviar" : `${r.pendientes} pendiente(s)`;
}

function renderFonts() {
  const box = $("#fonts"); box.replaceChildren();
  if (!data.fonts_in_design.length) { box.append(h("div", { class: "empty" }, "No se detectó texto vectorial en el diseño.")); return; }
  box.append(h("table", {}, h("tr", {}, h("th", {}, "Fuente"), h("th", {}, "Tam."), h("th", {}, "Estilo"), h("th", {}, "Usos")),
    data.fonts_in_design.map(f => h("tr", { title: f.example }, h("td", {}, f.font), h("td", {}, f.size_pt + " pt"),
      h("td", {}, [f.bold ? "negrita" : "", f.italic ? "cursiva" : ""].filter(Boolean).join(" ") || "normal"), h("td", {}, f.spans)))));
}

/* ---------- visor ---------- */
const imgUrl = name => `/api/results/${data.job_id}/${name}?t=${encodeURIComponent(data.created)}${data.elapsed_s}`;

function makeStage(imgs) {
  const st = h("div", { class: "stage", style: { width: data.width + "px", height: data.height + "px" } });
  imgs.forEach(([name, cls]) => st.append(h("img", { src: imgUrl(name), width: data.width, height: data.height, draggable: false, class: cls || "" })));
  return st;
}

function renderViewer() {
  const v = $("#viewer");
  v.replaceChildren();
  panes = [];
  const add = (caption, imgs, extra) => {
    const stage = makeStage(imgs);
    const pane = h("div", { class: "pane" }, h("div", { class: "cap" }, caption), stage);
    v.append(pane);
    panes.push({ el: pane, stage });
    bindPane(pane);
    if (extra) extra(pane, stage);
  };
  if (mode === "side") {
    add("A · Cliente", [["client_aligned.png"]]);
    add("B · Mi diseño", [["design.png"]]);
  } else if (mode === "slider") {
    add("◀ Mi diseño  |  Cliente ▶", [["design.png"], ["client_aligned.png", "top"]], (pane) => {
      const hd = h("div", { class: "handle" });
      pane.append(hd);
      pane._handle = hd;
      hd.addEventListener("pointerdown", e => {
        e.stopPropagation(); hd.setPointerCapture(e.pointerId);
        const mv = ev => {
          const r = pane.getBoundingClientRect();
          sliderFrac = Math.min(1, Math.max(0, ((ev.clientX - r.left) - view.tx) / (data.width * view.s)));
          applyView();
        };
        hd.addEventListener("pointermove", mv);
        hd.addEventListener("pointerup", () => hd.removeEventListener("pointermove", mv), { once: true });
      });
    });
  } else if (mode === "diff") {
    add("Mapa de diferencias", [["diff_heatmap.png"]]);
  } else {
    add("Superpuesto 50%", [["overlay.png"]]);
  }
  renderBoxes();
  applyModeLabels();
  fit();
}

function renderBoxes() {
  if (!data) return;
  const vis = new Set(visibleDiffs().map(d => d.id));
  panes.forEach(p => {
    p.stage.querySelectorAll(".box").forEach(b => b.remove());
    data.differences.filter(d => vis.has(d.id)).forEach(d => {
      const [x, y, w, h_] = d.bbox;
      const b = h("div", { class: "box" + (d.id === selectedId ? " sel" : ""), "data-id": d.id,
        style: { left: x + "px", top: y + "px", width: w + "px", height: h_ + "px", "--col": CAT_COLOR[d.category] },
        title: d.message, onclick: e => { e.stopPropagation(); selectError(d.id, false); } }, h("span", { class: "n" }, d.id));
      p.stage.append(b);
    });
    zones.forEach((z, i) => {
      p.stage.append(h("div", { class: "box zone", title: `Zona ignorada (${z.modo})`,
        style: { left: z.x * data.width + "px", top: z.y * data.height + "px", width: z.w * data.width + "px",
          height: z.h * data.height + "px", "--col": "#94a3b8" } }, h("span", { class: "n" }, "Z" + (i + 1))));
    });
    missed.forEach((m, i) => {
      const [x, y, w, h_] = m.bbox;
      p.stage.append(h("div", { class: "box missed", title: "No detectado: " + CAT_NAME[m.categoria],
        style: { left: x + "px", top: y + "px", width: w + "px", height: h_ + "px", "--col": CAT_COLOR[m.categoria] } },
        h("span", { class: "n" }, "M" + (i + 1))));
    });
  });
}

function paneSize() { const r = panes[0].el.getBoundingClientRect(); return [r.width, r.height]; }

function fit() {
  if (!panes.length) return;
  const [pw, ph] = paneSize();
  const s = Math.min(pw / data.width, ph / data.height) * 0.98;
  view = { s, tx: (pw - data.width * s) / 2, ty: (ph - data.height * s) / 2 };
  applyView();
}

function applyView() {
  panes.forEach(p => {
    p.stage.style.transform = `translate(${view.tx}px, ${view.ty}px) scale(${view.s})`;
    p.el.style.setProperty("--s", view.s);
    const top = p.stage.querySelector("img.top");
    if (top) top.style.clipPath = `inset(0 0 0 ${sliderFrac * 100}%)`;
    if (p.el._handle) p.el._handle.style.left = (view.tx + sliderFrac * data.width * view.s) + "px";
  });
}

function bindPane(pane) {
  pane.addEventListener("wheel", e => {
    e.preventDefault();
    const r = pane.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const s2 = Math.min(40, Math.max(0.02, view.s * f));
    view.tx = mx - (mx - view.tx) * (s2 / view.s);
    view.ty = my - (my - view.ty) * (s2 / view.s);
    view.s = s2;
    applyView();
  }, { passive: false });
  pane.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    if (drawMode) return startDraw(pane, e);
    pane.setPointerCapture(e.pointerId);
    pane.classList.add("dragging");
    let lx = e.clientX, ly = e.clientY;
    const mv = ev => { view.tx += ev.clientX - lx; view.ty += ev.clientY - ly; lx = ev.clientX; ly = ev.clientY; applyView(); };
    const up = () => { pane.classList.remove("dragging"); pane.removeEventListener("pointermove", mv); };
    pane.addEventListener("pointermove", mv);
    pane.addEventListener("pointerup", up, { once: true });
    pane.addEventListener("pointercancel", up, { once: true });
  });
}

function selectError(id, zoom) {
  selectedId = id;
  const d = data.differences.find(x => x.id === id);
  if (!d) return;
  document.querySelectorAll(".err").forEach(e => e.classList.toggle("sel", +e.dataset.id === id));
  if (!activeCats.has(d.category)) { activeCats.add(d.category); renderFilters(); renderErrors(); }
  renderBoxes();
  if (zoom) {
    const [x, y, w, h_] = d.bbox, [pw, ph] = paneSize();
    const fitS = Math.min(pw / data.width, ph / data.height);
    const s = Math.min(8, Math.max(fitS, Math.min(pw / (w * 1.8), ph / (h_ * 1.8))));
    view = { s, tx: pw / 2 - (x + w / 2) * s, ty: ph / 2 - (y + h_ / 2) * s };
    applyView();
  } else {
    const el = document.querySelector(`.err[data-id="${id}"]`);
    el && el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  panes.forEach(p => {
    const b = p.stage.querySelector(`.box[data-id="${id}"]`);
    if (b) { b.classList.remove("blink"); void b.offsetWidth; b.classList.add("blink"); }
  });
}

/* ---------- revisión: marcar errores no detectados y guardar caso ---------- */
function toImg(pane, e) {
  const r = pane.getBoundingClientRect();
  return [(e.clientX - r.left - view.tx) / view.s, (e.clientY - r.top - view.ty) / view.s];
}

function startDraw(pane, e) {
  const stage = pane.querySelector(".stage");
  const [x0, y0] = toImg(pane, e);
  const el = h("div", { class: "box drawing" });
  stage.append(el);
  pane.setPointerCapture(e.pointerId);
  const rect = ev => {
    const [x1, y1] = toImg(pane, ev);
    return [Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)];
  };
  const mv = ev => { const [x, y, w, h_] = rect(ev);
    Object.assign(el.style, { left: x + "px", top: y + "px", width: w + "px", height: h_ + "px" }); };
  pane.addEventListener("pointermove", mv);
  pane.addEventListener("pointerup", ev => {
    pane.removeEventListener("pointermove", mv);
    el.remove();
    const [x, y, w, h_] = rect(ev).map(Math.round);
    if (w > 6 && h_ > 6) {
      if (drawKind === "zone") {
        zones.push({ x: x / data.width, y: y / data.height, w: w / data.width, h: h_ / data.height, modo: $("#zone-mode").value });
        setDrawMode(false); renderZones(); renderBoxes();
      } else askMissed([x, y, w, h_]);
    }
  }, { once: true });
}

function askMissed(bbox) {
  const cat = h("select", {}, CATS.map(([k, n]) => h("option", { value: k }, n)));
  const cli = h("input", { placeholder: "El cliente dice (texto correcto)" });
  const dis = h("input", { placeholder: "Tu diseño dice (opcional)" });
  const close = () => bg.remove();
  const bg = h("div", { class: "dialog-bg" }, h("div", { class: "dialog" },
    h("b", {}, "Error no detectado"), h("label", {}, "Categoría", cat), cli, dis,
    h("div", { class: "row" }, h("button", { onclick: close }, "Cancelar"),
      h("button", { class: "primary", onclick: () => {
        missed.push({ categoria: cat.value, bbox, cliente_dice: cli.value || null, diseno_dice: dis.value || null });
        close(); setDrawMode(false); renderMissed(); renderBoxes(); } }, "Agregar"))));
  document.body.append(bg);
}

function setDrawMode(on, kind) {
  if (on && kind) drawKind = kind;
  drawMode = on;
  document.querySelectorAll(".pane").forEach(p => p.classList.toggle("drawmode", on));
  $("#btn-missed").textContent = on && drawKind === "missed" ? "Dibuja el rectángulo en el visor… (clic para cancelar)" : "Marcar error no detectado";
  $("#btn-zone").textContent = on && drawKind === "zone" ? "Dibuja la zona… (clic para cancelar)" : "Ignorar zona";
}

function renderZones() {
  const box = $("#zones-list"); if (!box) return;
  $("#zones-panel").classList.toggle("hidden", !zones.length);
  box.replaceChildren(...zones.map((z, i) => h("div", { class: "missed-item" }, `Z${i + 1} · ${z.modo}`,
    h("button", { onclick: () => { zones.splice(i, 1); renderZones(); renderBoxes(); } }, "✕"))));
}

async function saveTemplate() {
  const name = prompt("Nombre de la plantilla (por ejemplo «Cliente Pérez – volante»):");
  if (!name) return;
  try {
    await api("/api/templates", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre: name, zonas: zones, ancho: data.width, alto: data.height }) });
    loadTemplates(name);
  } catch (e) { showError(e.message); }
}

async function loadTemplates(select) {
  try {
    const list = await (await api("/api/templates")).json();
    const sel = $("#tpl-select");
    sel.replaceChildren(h("option", { value: "" }, "(ninguna)"), ...list.map(t => h("option", { value: t.nombre }, `${t.nombre} (${t.zonas} zonas)`)));
    if (select) sel.value = select;
  } catch {}
}

async function suggestTemplate() {
  if (!files.design && !files.client) return;
  try {
    const f = files.client || files.design;
    const s = await (await api("/api/templates/suggest?filename=" + encodeURIComponent(f.name))).json();
    $("#tpl-hint").textContent = s.length ? `Sugerida: ${s[0]}` : "";
    if (s.length && !$("#tpl-select").value) $("#tpl-select").value = s[0];
  } catch {}
}

function renderMissed() {
  const box = $("#missed-list"); if (!box) return;
  box.replaceChildren(...missed.map((m, i) => h("div", { class: "missed-item" },
    `M${i + 1} · ${CAT_NAME[m.categoria]}${m.cliente_dice ? " · " + m.cliente_dice : ""}`,
    h("button", { onclick: () => { missed.splice(i, 1); renderMissed(); renderBoxes(); } }, "✕"))));
}

async function saveCase() {
  if (!data) return;
  const pend = data.differences.filter(d => !verdicts[d.id]).length;
  if (pend && !confirm(`${pend} error(es) sin revisar se guardarán como REALES. ¿Continuar?`)) return;
  try {
    const r = await (await api("/api/cases/" + data.job_id, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdicts, missed, client_text: $("#rv-text").value || null, tipo: $("#rv-tipo").value }) })).json();
    $("#rv-msg").textContent = `Guardado como ${r.caso} (${r.errores} errores esperados) en datos_locales/casos.`
      + (r.autoajuste ? " Se está ajustando el OCR con tus casos en segundo plano (puedes seguir trabajando)." : "");
  } catch (e) { showError(e.message); }
}

/* ---------- sensibilidad / historial ---------- */
function updateSensLabels() {
  $("#v-ssim").textContent = (+$("#r-ssim").value).toFixed(2);
  $("#v-de").textContent = $("#r-de").value;
  $("#v-area").textContent = $("#r-area").value;
}

async function loadHistory() {
  try {
    const list = await (await api("/api/history")).json();
    const sel = $("#history");
    sel.replaceChildren(h("option", { value: "" }, list.length ? "Comparaciones recientes…" : "(vacío)"));
    list.forEach(e => sel.append(h("option", { value: e.job_id },
      `${e.created.replace("T", " ")} · ${e.client_name} vs ${e.design_name} · ${e.total}%`)));
  } catch {}
}

async function openHistory(id) {
  if (!id) return;
  showError("");
  setLoading(true);
  try {
    const res = await (await api(`/api/results/${id}/result.json`)).json();
    showResult(res);
  } catch (e) { showError("No se pudo abrir ese resultado: " + e.message); }
  finally { setLoading(false); $("#history").value = ""; }
}

/* ---------- panel «Aprendizaje» (Fase 7) ---------- */
async function openLearning() {
  const body = h("div", { class: "learn-body" }, "Cargando…");
  const close = () => { clearInterval(timer); bg.remove(); };
  const bg = h("div", { class: "dialog-bg" }, h("div", { class: "dialog wide" },
    h("b", {}, "Aprendizaje del OCR"), body, h("div", { class: "row" }, h("button", { onclick: close }, "Cerrar"))));
  document.body.append(bg);
  let timer = null;

  async function act(url, opts) {
    try { await api(url, opts); } catch (e) { showError(e.message); }
    await render();
  }

  async function render() {
    let r;
    try { r = await (await api("/api/learning")).json(); } catch (e) { body.textContent = e.message; return; }
    const ajustes = Object.entries(r.ajustes_por_tipo);
    const tarea = r.tarea || {};
    body.replaceChildren(
      h("div", { class: "hint" }, "Todo se guarda solo en este equipo (datos_locales/aprendizaje). Cada caso revisado en «Modo revisión» "
        + "enseña al OCR: vocabulario y patrones → confusiones → ajuste por tipo de imagen → modelo re-entrenado."),
      h("div", { class: "learn-stats" },
        stat(r.casos_revisados, "casos revisados"), stat(r.vocabulario, "palabras aprendidas"),
        stat(r.confusiones, "confusiones"), stat(`${r.lineas_para_entrenar}/300`, "líneas para entrenar"),
        stat(r.huella || "—", "huella")),
      h("h3", {}, "Ajuste por tipo de imagen"),
      ajustes.length ? h("table", { class: "learn-table" }, h("tr", {}, h("th", {}, "Tipo"), h("th", {}, "CER antes"), h("th", {}, "CER después"), h("th", {}, "Líneas")),
        ajustes.map(([t, a]) => h("tr", {}, h("td", {}, t), h("td", {}, (a.cer_antes * 100).toFixed(2) + "%"),
          h("td", {}, (a.cer_despues * 100).toFixed(2) + "%"), h("td", {}, a.lineas))))
        : h("div", { class: "hint" }, "Aún no hay ajustes (se calculan cada 5 casos revisados o con el botón)."),
      h("div", { class: "learn-actions" },
        h("button", { class: "primary", disabled: !!tarea.en_curso, onclick: () => act("/api/learning/tune", { method: "POST" }) }, "Ajustar OCR ahora"),
        h("button", { disabled: !!tarea.en_curso || r.lineas_para_entrenar < 300, title: "Requiere ≥ 300 líneas revisadas",
          onclick: () => confirm("El re-entrenamiento puede tardar varios minutos. ¿Continuar?") && act("/api/learning/train", { method: "POST" }) }, "Re-entrenar modelo"),
        r.modelo ? h("button", { onclick: () => act("/api/learning/model", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ activo: !r.modelo_activo }) }) }, r.modelo_activo ? "Volver al modelo original" : "Activar modelo entrenado") : null),
      tarea.en_curso ? h("div", { class: "banner warn" }, `En curso: ${tarea.en_curso}…`, h("pre", {}, (tarea.registro || []).join("\n"))) : "",
      tarea.resultado ? h("div", { class: "hint" }, "Último resultado: " + (tarea.resultado.mensaje || JSON.stringify(tarea.resultado).slice(0, 300))) : "",
      r.ab ? h("div", { class: "hint" }, `Prueba A/B: CER ${r.ab.cer_base}% → ${r.ab.cer_nuevo}% · F1 texto ${r.ab.f1_base}% → ${r.ab.f1_nuevo}% · ${r.ab.activado ? "activado" : "descartado"}`) : "",
      h("h3", {}, "Confusiones aprendidas"),
      r.confusiones_lista.length ? h("table", { class: "learn-table" }, h("tr", {}, h("th", {}, "Leído"), h("th", {}, "Correcto"), h("th", {}, "Veces"), h("th", {}, "Ejemplo"), h("th", {}, "")),
        r.confusiones_lista.map(c => h("tr", {}, h("td", {}, `«${c.leido}»`), h("td", {}, `«${c.correcto}»`), h("td", {}, c.veces),
          h("td", {}, (c.ejemplos[0] || []).join(" → ")),
          h("td", {}, h("button", { onclick: () => act("/api/learning/confusion?key=" + encodeURIComponent(c.clave), { method: "DELETE" }) }, "Borrar")))))
        : h("div", { class: "hint" }, "Ninguna todavía. Marca errores de texto como «✘ Falso positivo» al revisar."),
      h("details", {}, h("summary", {}, `Vocabulario aprendido (${r.vocabulario})`),
        h("div", { class: "vocab" }, r.vocabulario_lista.map(v => h("span", { class: "vocab-item" }, `${v.palabra} ×${v.veces} `,
          h("a", { onclick: () => act("/api/learning/vocab?word=" + encodeURIComponent(v.palabra), { method: "DELETE" }) }, "✕"))))),
      h("h3", {}, "Llevar el aprendizaje a otro equipo"),
      h("div", { class: "learn-actions" },
        h("a", { class: "button", href: "/api/learning/export", download: "" }, "Exportar (sin imágenes de clientes)"),
        h("a", { class: "button", href: "/api/learning/export?recortes=true", download: "",
          onclick: e => { if (!confirm("El ZIP incluirá recortes de imágenes de tus clientes (datos privados). ¿Continuar?")) e.preventDefault(); } }, "Exportar con recortes (privado)"),
        h("label", { class: "button" }, "Importar…", h("input", { type: "file", accept: ".zip", hidden: true, onchange: async e => {
          const f = e.target.files[0]; if (!f) return;
          const fd = new FormData(); fd.append("file", f);
          try { const j = await (await api("/api/learning/import", { method: "POST", body: fd })).json();
            alert("Importado: " + JSON.stringify(j.agregado)); } catch (er) { showError(er.message); }
          render(); } }))));
    if (tarea.en_curso && !timer) timer = setInterval(render, 2500);
    if (!tarea.en_curso && timer) { clearInterval(timer); timer = null; }
  }
  const stat = (v, l) => h("div", { class: "chip" }, h("b", {}, v), h("small", {}, l));
  render();
}

/* ---------- modo, lote, correcciones, pegar (Fase 8) ---------- */
function setMode(m) {
  mode2 = m;
  const ver = m === "versiones";
  $("#drop-client .drop-title").textContent = ver ? "A · Mi diseño, versión 1" : "A · Arte del cliente";
  $("#drop-design .drop-title").textContent = ver ? "B · Mi diseño, versión 2 (nueva)" : "B · Mi diseño";
  $("#drop-client input").accept = ver ? ".pdf" : ".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.pdf";
  $("#btn-compare").textContent = ver ? "Comparar versiones" : "Comparar";
  $("#tpl-select").closest("label").classList.toggle("hidden", ver);
  updateBatchBtn();
}

function updateBatchBtn() {
  const multi = !$("#pages-client").classList.contains("hidden") || !$("#pages-design").classList.contains("hidden");
  const b = $("#btn-batch");
  b.classList.toggle("hidden", !(multi && mode2 === "cliente"));
  b.disabled = !(files.client && files.design);
}

async function compareBatch() {
  showError("");
  const fd = new FormData();
  fd.append("client_file", files.client);
  fd.append("design_file", files.design);
  if ($("#tpl-select").value) fd.append("template", $("#tpl-select").value);
  setLoading(true);
  try {
    const j = await (await api("/api/compare-batch", { method: "POST", body: fd })).json();
    lastBatch = await pollJob(j.job_id);
    showBatch(lastBatch);
  } catch (e) { showError(e.message); }
  finally { setLoading(false); }
}

function showBatch(b) {
  const close = () => bg.remove();
  const lbl = { aprobado: "Aprobado", revisar: "Revisar", con_errores: "Con errores" };
  const bg = h("div", { class: "dialog-bg" }, h("div", { class: "dialog wide" },
    h("b", {}, `Lote: ${b.paginas.length} páginas · similitud promedio ${b.total_promedio}%`),
    h("table", { class: "learn-table" },
      h("tr", {}, h("th", {}, "Pág."), h("th", {}, "Cliente"), h("th", {}, "Diseño"), h("th", {}, "%"), h("th", {}, "Estado"), h("th", {}, "Errores"), h("th", {}, "Pend."), h("th", {}, "")),
      b.paginas.map(p => h("tr", {}, h("td", {}, p.n), h("td", {}, p.client_page), h("td", {}, p.design_page),
        h("td", {}, p.total + "%"), h("td", {}, h("span", { class: "badge " + p.status }, lbl[p.status])), h("td", {}, p.errores), h("td", {}, p.pendientes),
        h("td", {}, h("button", { onclick: async () => { close(); await openHistory(p.job_id); } }, "Abrir"))))),
    (b.sin_pareja_cliente.length || b.sin_pareja_diseno.length)
      ? h("div", { class: "banner warn" }, `Sin pareja — cliente: ${b.sin_pareja_cliente.join(", ") || "—"} · diseño: ${b.sin_pareja_diseno.join(", ") || "—"}`) : null,
    h("div", { class: "row" }, h("a", { class: "button", href: "/api/report-batch/" + b.batch_id, target: "_blank" }, "Reporte PDF de todo el lote"),
      h("button", { class: "primary", onclick: close }, "Cerrar"))));
  document.body.append(bg);
}

async function verifyFix(file) {
  if (!file || !data) return;
  showError("");
  const fd = new FormData();
  fd.append("previous_job_id", data.job_id);
  fd.append("design_file", file);
  setLoading(true);
  try {
    const j = await (await api("/api/compare-fix", { method: "POST", body: fd })).json();
    showResult(await pollJob(j.job_id));
    loadHistory();
  } catch (e) { showError(e.message); }
  finally { setLoading(false); $("#fix-file").value = ""; }
}

/* pegar una imagen con Ctrl+V o arrastrarla desde el navegador / WhatsApp Web */
function askTarget(file) {
  if (!files.client) return setFile("client", file);
  if (!files.design && !file.type.includes("pdf")) return setFile("design", file);
  const close = () => bg.remove();
  const bg = h("div", { class: "dialog-bg" }, h("div", { class: "dialog" }, h("b", {}, "¿Para qué es esta imagen?"),
    h("div", { class: "row" },
      h("button", { class: "primary", onclick: () => { close(); setFile("client", file); } }, "A · Arte del cliente"),
      h("button", { onclick: () => { close(); setFile("design", file); } }, "B · Mi diseño"),
      h("button", { onclick: close }, "Cancelar"))));
  document.body.append(bg);
}

document.addEventListener("paste", e => {
  const it = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/"));
  if (!it) return;
  const blob = it.getAsFile(); if (!blob) return;
  e.preventDefault();
  const ext = (it.type.split("/")[1] || "png").replace("jpeg", "jpg");
  askTarget(new File([blob], `pegado_${Date.now()}.${ext}`, { type: it.type }));
});

async function fileFromDrop(dt) {
  if (dt.files && dt.files.length) return dt.files[0];
  let url = (dt.getData("text/uri-list") || "").split("\n")[0].trim();
  if (!url) {
    const m = /<img[^>]+src=["']([^"']+)["']/i.exec(dt.getData("text/html") || "");
    url = m ? m[1] : "";
  }
  if (!url) return null;
  try {
    const r = await fetch(url);
    const b = await r.blob();
    if (!b.type.startsWith("image/")) return null;
    return new File([b], `arrastrada_${Date.now()}.${(b.type.split("/")[1] || "png").replace("jpeg", "jpg")}`, { type: b.type });
  } catch {
    showError("No se pudo leer esa imagen desde el navegador (el sitio no lo permite). Guárdala o cópiala y pégala con Ctrl+V.");
    return null;
  }
}

/* ---------- inicio ---------- */
setupDrop("client");
setupDrop("design");
$("#btn-compare").addEventListener("click", compare);
$("#btn-fit").addEventListener("click", fit);
$("#btn-sens").addEventListener("click", () => { $("#sens").classList.toggle("hidden"); fit(); });
$("#btn-recalc").addEventListener("click", () => recalc());
$("#mode-select").addEventListener("change", e => setMode(e.target.value));
$("#btn-batch").addEventListener("click", compareBatch);
$("#btn-fix").addEventListener("click", () => $("#fix-file").click());
$("#fix-file").addEventListener("change", e => verifyFix(e.target.files[0]));
$("#btn-learning").addEventListener("click", openLearning);
$("#btn-align").addEventListener("click", manualAlign);
$("#btn-review").addEventListener("click", () => {
  reviewMode = !reviewMode;
  $("#review-panel").classList.toggle("hidden", !reviewMode);
  $("#btn-review").classList.toggle("primary", reviewMode);
  if (!reviewMode) setDrawMode(false);
  renderErrors();
});
$("#btn-missed").addEventListener("click", () => setDrawMode(!(drawMode && drawKind === "missed"), "missed"));
$("#btn-zone").addEventListener("click", () => setDrawMode(!(drawMode && drawKind === "zone"), "zone"));
$("#btn-zones-apply").addEventListener("click", () => recalc());
$("#btn-zones-save").addEventListener("click", saveTemplate);
$("#btn-savecase").addEventListener("click", saveCase);
["#r-ssim", "#r-de", "#r-area"].forEach(s => $(s).addEventListener("input", updateSensLabels));
$("#history").addEventListener("change", e => openHistory(e.target.value));
$("#tabs").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  mode = b.dataset.mode;
  document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("active", x === b));
  data && renderViewer();
});
window.addEventListener("resize", () => panes.length && fit());
loadHistory();
loadTemplates();

/* versión en el pie y aviso de actualización */
(async function () {
  try {
    const u = await (await fetch("/api/update")).json();
    $("#version").textContent = "FAVERVIEW v" + u.version;
    if (u.disponible) {
      const b = $("#update");
      b.classList.remove("hidden");
      b.replaceChildren(u.mensaje + " ", h("button", { class: "primary", onclick: async () => {
        const r = await (await fetch("/api/update/apply", { method: "POST" })).json();
        b.textContent = r.mensaje;
      } }, "Actualizar"));
    }
  } catch {}
})();
