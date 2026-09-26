"use strict";
/* Visor compartido: zoom (10 %–3200 %), paneo, «ajustar», 100 %, capas, regla/cursor en mm y cuentagotas.
   Lo usan todos los módulos de la suite. Cada «panel» es un div con un `stage` (contenedor de tamaño = imagen en px)
   que se escala y traslada con una transformación común a todos los paneles (así se mueven sincronizados). */

class FVViewer {
  constructor(opts = {}) {
    this.width = opts.width || 1;
    this.height = opts.height || 1;
    this.minScale = opts.minScale || 0.02;
    this.maxScale = opts.maxScale || 32;       // 3200 %
    this.dpi = opts.dpi || 0;                  // si se conoce, la regla y el cursor muestran mm
    this.view = { s: 1, tx: 0, ty: 0 };
    this.panes = [];                           // [{ el, stage }]
    this.layers = [];                          // [{ id, name, els, visible, opacity }]
    this.onApply = null;                       // () => void   tras cada cambio de vista
    this.onPointerDown = null;                 // (pane, ev) => true si lo consume (p. ej. dibujar)
    this.onProbe = null;                       // (x, y, pane, ev) => void   posición en px de la imagen
    this.syncGroups = [];                      // otros visores a sincronizar con este
    this.cursorLabel = null;
  }

  /* ---------- paneles ---------- */
  reset(width, height, dpi) {
    this.width = width; this.height = height;
    if (dpi !== undefined) this.dpi = dpi;
    this.panes.length = 0;
    this.layers.length = 0;
  }

  attach(el, stage) {
    const p = { el, stage };
    this.panes.push(p);
    el.style.touchAction = "none";
    el.addEventListener("wheel", e => this._wheel(el, e), { passive: false });
    el.addEventListener("pointerdown", e => this._down(p, e));
    el.addEventListener("pointermove", e => this._move(p, e));
    if (this.dpi) this._ensureCursorLabel(el);
    return p;
  }

  paneSize() {
    const r = this.panes[0].el.getBoundingClientRect();
    return [r.width, r.height];
  }

  /* ---------- vista ---------- */
  apply() {
    for (const p of this.panes) {
      p.stage.style.transform = `translate(${this.view.tx}px, ${this.view.ty}px) scale(${this.view.s})`;
      p.el.style.setProperty("--s", this.view.s);
    }
    if (this.onApply) this.onApply(this.view);
    for (const other of this.syncGroups) other._adopt(this.view);
  }

  _adopt(view) {
    this.view = { ...view };
    for (const p of this.panes) {
      p.stage.style.transform = `translate(${view.tx}px, ${view.ty}px) scale(${view.s})`;
      p.el.style.setProperty("--s", view.s);
    }
    if (this.onApply) this.onApply(this.view);
  }

  fit() {
    if (!this.panes.length) return;
    const [pw, ph] = this.paneSize();
    const s = Math.min(pw / this.width, ph / this.height) * 0.98;
    this.view = { s, tx: (pw - this.width * s) / 2, ty: (ph - this.height * s) / 2 };
    this.apply();
  }

  actualSize() {           // 100 % (1 px de imagen = 1 px de pantalla)
    if (!this.panes.length) return;
    const [pw, ph] = this.paneSize();
    this.view = { s: 1, tx: (pw - this.width) / 2, ty: (ph - this.height) / 2 };
    this.apply();
  }

  zoomToRect(x, y, w, h, margin = 1.8, maxScale = 8) {
    const [pw, ph] = this.paneSize();
    const fitS = Math.min(pw / this.width, ph / this.height);
    const s = Math.min(maxScale, Math.max(fitS, Math.min(pw / (w * margin), ph / (h * margin))));
    this.view = { s, tx: pw / 2 - (x + w / 2) * s, ty: ph / 2 - (y + h / 2) * s };
    this.apply();
  }

  zoomAt(mx, my, factor) {
    const s2 = Math.min(this.maxScale, Math.max(this.minScale, this.view.s * factor));
    this.view.tx = mx - (mx - this.view.tx) * (s2 / this.view.s);
    this.view.ty = my - (my - this.view.ty) * (s2 / this.view.s);
    this.view.s = s2;
    this.apply();
  }

  /* coordenadas del ratón → píxeles de la imagen */
  toImg(pane, ev) {
    const r = (pane.el || pane).getBoundingClientRect();
    return [(ev.clientX - r.left - this.view.tx) / this.view.s, (ev.clientY - r.top - this.view.ty) / this.view.s];
  }

  pxToMm(px) { return this.dpi ? px * 25.4 / this.dpi : null; }

  /* ---------- eventos ---------- */
  _wheel(el, e) {
    e.preventDefault();
    const r = el.getBoundingClientRect();
    this.zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.15 : 1 / 1.15);
  }

  _down(p, e) {
    if (e.button !== 0 && e.button !== 1) return;
    if (e.target.closest && e.target.closest("[data-nopan]")) return;
    if (this.onPointerDown && this.onPointerDown(p, e)) return;
    const pane = p.el;
    pane.setPointerCapture(e.pointerId);
    pane.classList.add("dragging");
    let lx = e.clientX, ly = e.clientY;
    const mv = ev => { this.view.tx += ev.clientX - lx; this.view.ty += ev.clientY - ly; lx = ev.clientX; ly = ev.clientY; this.apply(); };
    const up = () => { pane.classList.remove("dragging"); pane.removeEventListener("pointermove", mv); };
    pane.addEventListener("pointermove", mv);
    pane.addEventListener("pointerup", up, { once: true });
    pane.addEventListener("pointercancel", up, { once: true });
  }

  _move(p, e) {
    if (!this.onProbe && !this.dpi) return;
    const [x, y] = this.toImg(p, e);
    if (this.onProbe) this.onProbe(x, y, p, e);
    if (this.cursorLabel && this.dpi) {
      const inside = x >= 0 && y >= 0 && x <= this.width && y <= this.height;
      this.cursorLabel.textContent = inside ? `${this.pxToMm(x).toFixed(1)} mm · ${this.pxToMm(y).toFixed(1)} mm` : "";
    }
  }

  _ensureCursorLabel(el) {
    if (!this.cursorLabel) {
      this.cursorLabel = document.createElement("div");
      this.cursorLabel.className = "vw-cursor";
    }
    el.appendChild(this.cursorLabel);
  }

  /* ---------- capas ---------- */
  addLayer({ id, name, els, visible = true, opacity = 1 }) {
    const layer = { id, name, els: Array.isArray(els) ? els : [els], visible, opacity };
    this.layers.push(layer);
    this._paintLayer(layer);
    return layer;
  }

  _paintLayer(l) {
    for (const el of l.els) { el.style.display = l.visible ? "" : "none"; el.style.opacity = l.opacity; }
  }

  setLayer(id, { visible, opacity } = {}) {
    const l = this.layers.find(x => x.id === id);
    if (!l) return;
    if (visible !== undefined) l.visible = visible;
    if (opacity !== undefined) l.opacity = opacity;
    this._paintLayer(l);
  }

  /* panel de capas: casillas de visibilidad + deslizador de opacidad */
  renderLayerPanel(container) {
    container.replaceChildren();
    for (const l of this.layers) {
      const row = document.createElement("div");
      row.className = "vw-layer";
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = l.visible;
      cb.addEventListener("change", () => this.setLayer(l.id, { visible: cb.checked }));
      const label = document.createElement("span"); label.textContent = l.name;
      const range = document.createElement("input");
      range.type = "range"; range.min = 0; range.max = 100; range.value = Math.round(l.opacity * 100);
      range.addEventListener("input", () => this.setLayer(l.id, { opacity: range.value / 100 }));
      row.append(cb, label, range);
      container.appendChild(row);
    }
  }
}

/* atajos comunes: Ctrl+0 = ajustar, Ctrl+1 = 100 %; Espacio + arrastrar = paneo (el paneo ya es arrastrar) */
FVViewer.bindShortcuts = function (getViewer) {
  document.addEventListener("keydown", e => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const v = getViewer();
    if (!v || !v.panes.length) return;
    if (e.key === "0") { e.preventDefault(); v.fit(); }
    else if (e.key === "1") { e.preventDefault(); v.actualSize(); }
  });
};

window.FVViewer = FVViewer;
