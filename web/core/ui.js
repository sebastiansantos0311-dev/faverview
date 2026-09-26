"use strict";
(function () {
/* Utilidades de interfaz compartidas: creación de elementos, avisos, diálogos y barra de progreso. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

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

function setProgress(msg, pct) {
  $("#loading-msg").textContent = msg || "Procesando…";
  $("#loading-bar").style.width = Math.round((pct || 0) * 100) + "%";
}
function setLoading(on) { $("#loading").classList.toggle("hidden", !on); if (on) setProgress("Procesando…", 0); }

/* aviso breve que desaparece solo */
function toast(msg, kind = "info", ms = 4000) {
  let box = $("#toasts");
  if (!box) { box = h("div", { id: "toasts", class: "toasts" }); document.body.append(box); }
  const t = h("div", { class: "toast " + kind }, msg);
  box.append(t);
  setTimeout(() => t.remove(), ms);
}

/* diálogo modal simple: devuelve el elemento del contenido y una función para cerrarlo */
function dialog(title, body, buttons = [], wide = false) {
  const bg = h("div", { class: "dialog-bg" });
  const close = () => bg.remove();
  const row = h("div", { class: "row" }, buttons.map(b => h("button", { class: b.primary ? "primary" : "", onclick: () => { if (b.onclick) b.onclick(close); else close(); } }, b.label)));
  bg.append(h("div", { class: "dialog" + (wide ? " wide" : "") }, h("b", {}, title), body, row));
  document.body.append(bg);
  return { close, el: bg };
}

function fmt(n, d = 1) { return Number(n).toLocaleString("es", { minimumFractionDigits: d, maximumFractionDigits: d }); }

window.FV = { $, $$, h, showError, setLoading, setProgress, toast, dialog, fmt };
})();
