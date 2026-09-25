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
function setLoading(on) { $("#loading").classList.toggle("hidden", !on); }

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
  box.addEventListener("drop", e => { const f = e.dataTransfer.files[0]; if (f) setFile(kind, f); });
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
}

async function compare() {
  showError("");
  const fd = new FormData();
  fd.append("client_file", files.client);
  fd.append("design_file", files.design);
  fd.append("client_page", $("#pages-client select").value || 1);
  fd.append("design_page", $("#pages-design select").value || 1);
  setLoading(true);
  try {
    const j = await (await api("/api/compare", { method: "POST", body: fd })).json();
    showResult(j.result);
    loadHistory();
  } catch (e) { showError(e.message); }
  finally { setLoading(false); }
}

async function recalc() {
  if (!data) return;
  showError("");
  setLoading(true);
  try {
    const body = {
      ssim_threshold: +$("#r-ssim").value, delta_e_tolerance: +$("#r-de").value, min_region_area: +$("#r-area").value,
      client_page: +($("#pages-client select").value || data.pages?.client || 1),
      design_page: +($("#pages-design select").value || data.pages?.design || 1),
    };
    const j = await (await api("/api/recompute/" + data.job_id, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
    showResult(j.result, true);
  } catch (e) { showError(e.message); }
  finally { setLoading(false); }
}

/* ---------- resultado ---------- */
function showResult(res, keepUi = false) {
  data = res;
  ignored = new Set();
  selectedId = null;
  showIgnored = false;
  if (!keepUi) activeCats = new Set(CATS.map(c => c[0]));
  $("#results").classList.remove("hidden");
  renderSummary();
  renderWarnings();
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
      h("div", {}, `${data.differences.length} errores · ${data.elapsed_s}s`)));
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
  return data.differences.filter(d => activeCats.has(d.category) && (showIgnored || !ignored.has(d.id)));
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
  if (d.category === "spelling") btns.append(h("button", { onclick: async e => {
    e.stopPropagation();
    try { await api("/api/dictionary", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ word: d.found }) });
      ignored.add(d.id); renderErrors(); renderBoxes(); } catch (er) { showError(er.message); }
  } }, "Agregar al diccionario"));
  btns.append(h("button", { onclick: e => { e.stopPropagation(); ignored.add(d.id); renderErrors(); renderBoxes(); } },
    ignored.has(d.id) ? "Ignorado" : "Ignorar"));
  return h("div", { class: "err" + (d.id === selectedId ? " sel" : ""), "data-id": d.id,
    style: { "--col": CAT_COLOR[d.category] }, onclick: () => selectError(d.id, true) },
    h("div", { class: "top" }, h("span", { class: "num" }, d.id), h("span", { class: "msg" }, d.message.replace(/ΔE/g, "ΔE"))),
    says, btns);
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

/* ---------- inicio ---------- */
setupDrop("client");
setupDrop("design");
$("#btn-compare").addEventListener("click", compare);
$("#btn-fit").addEventListener("click", fit);
$("#btn-sens").addEventListener("click", () => { $("#sens").classList.toggle("hidden"); fit(); });
$("#btn-recalc").addEventListener("click", recalc);
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
