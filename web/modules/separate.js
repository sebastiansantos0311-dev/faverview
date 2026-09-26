"use strict";
(function () {
/* Módulo Separar colores → PDF (S2). */
const { h, toast } = FV;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const root = document.getElementById("vista-separar");
const q = s => root.querySelector(s);
let job = null, res = null, inv = null, mode = "comp", solo = "", negative = false;
const hidden = new Set();
let probeT = null;
const viewer = new FVViewer();
const stage = h("div", { class: "stage" });
const img = h("img", { draggable: "false" });
const overlay = h("div", { class: "sp-ov" });
stage.append(img, overlay);
let pane = null;

const base = () => `/api/separar/pdf/${job}`;
const params = () => `pagina=${q("#sp-page").value}&dpi=${q("#sp-dpi").value}`;
function showErr(m) { const b = q("#sp-err"); b.textContent = m || ""; b.classList.toggle("hidden", !m); }

FVDrop.bind(q("#sp-drop"), q("#sp-drop input"), async f => {
  showErr("");
  try {
    FV.setLoading(true);
    const r = await FVApi.postForm("/api/separar/pdf", { file: f });
    job = r.job_id; inv = r.inventario;
    q("#sp-name").textContent = r.nombre;
    const sel = q("#sp-page"); sel.innerHTML = "";
    for (let i = 1; i <= r.paginas; i++) sel.append(h("option", { value: i }, i));
    q("#sp-setup").classList.add("hidden"); q("#sp-main").classList.remove("hidden");
    await analyze();
  } catch (e) { showErr(e.message); } finally { FV.setLoading(false); }
}, showErr);

async function analyze(keepView) {
  FV.setLoading(true);
  try {
    const lim = q("#sp-prof").value;
    const { job_id } = await (await FVApi.api(`${base()}/analizar?${params()}&limite_tac=${lim}`, { method: "POST" })).json();
    res = await FVApi.pollJob(job_id);
    inv = res.inventario;
    (res.avisos || []).forEach(a => toast(a, "warn", 8000));
    renderInks(); renderIssues(); loadImage(!keepView);
    const t = res.tac;
    q("#sp-tacinfo").innerHTML = `Máxima: <b>${t.max} %</b> · p99,5: ${t.p995} % · media ${t.media} %<br>Límite elegido: ${res.limite_tac} %`;
  } catch (e) { toast(e.message, "error", 8000); } finally { FV.setLoading(false); }
}

function loadImage(fit) {
  const p = params();
  let url;
  if (mode === "tac") url = `${base()}/tac.png?${p}&limite=${res.limite_tac}&t=${Date.now()}`;
  else if (solo) url = `${base()}/placa.png?${p}&nombre=${encodeURIComponent(solo)}&negativo=${negative}&t=${Date.now()}`;
  else url = `${base()}/composicion.png?${p}&ocultas=${encodeURIComponent([...hidden].join("|"))}&t=${Date.now()}`;
  img.onload = () => {
    if (fit || !pane) {
      const box = q("#sp-viewer"); box.innerHTML = "";
      const el = h("div", { class: "pane" }); el.append(stage); box.append(el);
      viewer.reset(res.ancho, res.alto, res.dpi);
      pane = viewer.attach(el, stage);
      viewer.onProbe = onProbe;
      stage.style.width = res.ancho + "px"; stage.style.height = res.alto + "px";
      viewer.fit();
    }
    drawOverlay();
  };
  img.src = url;
}

const PROC = { Cyan: "#00aeef", Magenta: "#ec008c", Yellow: "#fff200", Black: "#231f20" };
function swatch(p) {
  if (PROC[p.nombre]) return PROC[p.nombre];
  const t = (inv.tintas || []).find(x => x.nombre === p.nombre);
  return t && t.muestra ? t.muestra : "#999";
}

function renderInks() {
  const box = q("#sp-inks"); box.innerHTML = "";
  for (const p of res.placas) {
    box.append(h("div", { class: "sp-ink" + (p.vacia ? " empty" : "") },
      h("input", { type: "checkbox", checked: !hidden.has(p.nombre), title: "Mostrar / ocultar",
        onchange: e => { e.target.checked ? hidden.delete(p.nombre) : hidden.add(p.nombre); mode = "comp"; solo = ""; loadImage(false); } }),
      h("span", { class: "sp-sw", style: { background: swatch(p) } }),
      h("span", { class: "sp-nm", title: p.nombre }, p.nombre),
      h("small", {}, `${p.tipo} · ${p.cobertura.toFixed(1)} %`),
      h("button", { class: "ghost mini", title: "Ver solo esta placa", onclick: () => { solo = solo === p.nombre ? "" : p.nombre; mode = "comp"; loadImage(false); } }, "Solo"),
      h("button", { class: "ghost mini", title: "Placa en negativo", onclick: () => { solo = p.nombre; negative = !negative; mode = "comp"; loadImage(false); } }, "Neg.")));
  }
  (inv.no_usadas || []).filter(n => !res.placas.some(p => p.nombre === n))
    .forEach(n => box.append(h("div", { class: "sp-ink empty" }, h("span", { class: "sp-nm" }, n), h("small", {}, "definida, sin uso"))));
  q("#sp-merge").disabled = !(inv.duplicadas || []).length;
  q("#sp-del").disabled = !(inv.no_usadas || []).length;
}

function renderIssues() {
  const box = q("#sp-issues"); box.innerHTML = "";
  q("#sp-count").textContent = `(${res.hallazgos.length})`;
  if (!res.hallazgos.length) box.append(h("p", { class: "hint" }, "No se detectaron problemas de separación."));
  res.hallazgos.forEach(f => box.append(
    h("div", { class: "sp-issue " + f.severidad, onclick: () => f.bbox && viewer.zoomToRect(...f.bbox) }, f.mensaje)));
}

function drawOverlay() {
  overlay.innerHTML = "";
  if (!res) return;
  res.hallazgos.forEach(f => {
    if (!f.bbox) return;
    const [x, y, w, hh] = f.bbox;
    overlay.append(h("div", { class: "sp-box " + f.severidad, style: { left: x + "px", top: y + "px", width: w + "px", height: hh + "px" } }));
  });
}

function onProbe(x, y) {
  if (!res || x < 0 || y < 0 || x > res.ancho || y > res.alto) return;
  clearTimeout(probeT);
  probeT = setTimeout(async () => {
    try {
      const r = await FVApi.getJSON(`${base()}/sonda?${params()}&x=${Math.round(x)}&y=${Math.round(y)}`);
      const parts = Object.entries(r.tintas).filter(([, v]) => v > 0).map(([k, v]) => `${esc(k)} ${v} %`);
      q("#sp-probe").innerHTML = `<b>Cobertura total ${r.tac} %</b>${r.tac > res.limite_tac ? " ⚠" : ""} — ${parts.join(" · ") || "sin tinta (papel)"}`;
    } catch {}
  }, 60);
}

async function edit(body, okMsg) {
  try {
    FV.setLoading(true);
    const r = await FVApi.postJSON(`${base()}/editar`, body);
    toast(okMsg(r), "ok");
    q("#sp-undo").classList.remove("hidden");
    const dl = q("#sp-dl"); dl.classList.remove("hidden"); dl.href = `${base()}/descargar`;
    await analyze(true);
  } catch (e) { toast(e.message, "error", 8000); } finally { FV.setLoading(false); }
}

q("#sp-merge").onclick = () => {
  const map = {};
  (inv.tintas || []).filter(t => t.variantes.length > 1).forEach(t => t.variantes.forEach(n => { if (n !== t.nombre) map[n] = t.nombre; }));
  edit({ renombrar: map }, r => `Se unieron ${r.renombradas} nombre(s).`);
};
q("#sp-del").onclick = () => edit({ eliminar_no_usadas: true }, r => `Se eliminaron ${r.eliminadas} tinta(s) sin uso.`);
q("#sp-conv").onclick = () => {
  const spots = res.placas.filter(p => p.tipo === "spot");
  if (!spots.length) return toast("No hay tintas directas para convertir.", "warn");
  const sel = h("select", {}, spots.map(p => h("option", { value: p.nombre }, p.nombre)));
  FV.dialog("Convertir una directa a proceso (CMYK)", h("div", {},
    h("p", {}, "Se reescribe el contenido con su equivalente CMYK. Solo funciona con directas simples cuyo color alternativo es CMYK. El original no se modifica."), sel),
    [{ label: "Cancelar" },
     { label: "Convertir", primary: true, onclick: close => { close(); edit({ convertir: [sel.value] }, r => `Se convirtieron ${r.convertidas} objeto(s).`); } }]);
};
q("#sp-undo").onclick = async () => {
  await FVApi.postJSON(`${base()}/deshacer`, {});
  q("#sp-undo").classList.add("hidden"); q("#sp-dl").classList.add("hidden");
  analyze(true);
};
q("#sp-tac").onclick = () => { mode = mode === "tac" ? "comp" : "tac"; q("#sp-tac").classList.toggle("active", mode === "tac"); loadImage(false); };
q("#sp-page").onchange = () => analyze(false);
q("#sp-dpi").onchange = () => analyze(false);
q("#sp-prof").onchange = () => analyze(true);
q("#sp-new").onclick = () => {
  q("#sp-main").classList.add("hidden"); q("#sp-setup").classList.remove("hidden");
  pane = null; job = null; hidden.clear(); solo = ""; mode = "comp";
};
q("#sp-exp").onclick = () => {
  const fmt = h("select", {}, [["tiff8", "TIFF 8 bits (una por tinta)"], ["tiff1", "TIFF 1 bit (umbral 50 %)"], ["pdf", "PDF de placas"], ["informe", "Solo informe"]]
    .map(([v, t]) => h("option", { value: v }, t)));
  FV.dialog("Exportar placas", h("div", {}, h("p", {}, "Se descarga un ZIP con las placas y un informe de cobertura y problemas."), fmt),
    [{ label: "Cancelar" },
     { label: "Exportar", primary: true, onclick: async close => {
       close();
       try {
         FV.setLoading(true);
         const r = await FVApi.api(`${base()}/exportar`, { method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify({ formato: fmt.value, pagina: +q("#sp-page").value, dpi: +q("#sp-dpi").value, limite_tac: +q("#sp-prof").value }) });
         const url = URL.createObjectURL(await r.blob());
         const a = h("a", { href: url, download: "placas.zip" }); document.body.append(a); a.click(); a.remove();
       } catch (e) { toast(e.message, "error", 8000); } finally { FV.setLoading(false); }
     } }]);
};
FVViewer.bindShortcuts(() => (q("#sp-viewer") && q("#sp-viewer").offsetParent ? viewer : null));
})();
