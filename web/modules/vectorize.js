"use strict";
(function () {
/* Módulo Vectorizar (S4). */
const { h, toast } = FV;
const root = document.getElementById("vista-vectorizar");
const q = s => root.querySelector(s);
let job = null, last = null, pane = null, timer = null;
const viewer = new FVViewer();
const stage = h("div", { class: "stage" });
const imgO = h("img", { draggable: "false" }), imgV = h("img", { draggable: "false" });
stage.append(imgO, imgV);
const base = () => `/api/vectorizar/${job}`;
const err = m => { const b = q("#vz-err"); b.textContent = m || ""; b.classList.toggle("hidden", !m); };

FVDrop.bind(q("#vz-drop"), q("#vz-drop input"), async f => {
  err("");
  try {
    FV.setLoading(true);
    const r = await FVApi.postForm("/api/vectorizar", { file: f });
    job = r.job_id;
    q("#vz-name").textContent = `${r.nombre} · ${r.ancho}×${r.alto} px` + (r.dpi ? ` · ${Math.round(r.dpi)} ppi` : "");
    q("#vz-setup").classList.add("hidden"); q("#vz-main").classList.remove("hidden");
    await run();
  } catch (e) { err(e.message); } finally { FV.setLoading(false); }
}, err);

const PRE = { logo: [6, 8, 0.15, 0.7], linea: [2, 8, 0.1, 0.7], ilustracion: [10, 5, 0.15, 0.9], escaneo: [4, 8, 0.2, 1.0], foto: [12, 3, 0.3, 1.2] };
q("#vz-preset").onchange = () => {
  const [k, fus, det, tol] = PRE[q("#vz-preset").value];
  q("#vz-k").value = k; q("#vz-fus").value = fus; q("#vz-det").value = det; q("#vz-tol").value = tol;
  run();
};
const num = id => +q(id).value;
function params() {
  return { preset: q("#vz-preset").value, k_max: num("#vz-k"), fusionar_de: num("#vz-fus"), detalle_min_mm: num("#vz-det"),
    tolerancia: num("#vz-tol"), esquinas: num("#vz-esq"), suavidad: num("#vz-suav"), modo: q("#vz-modo").value,
    bn: q("#vz-preset").value === "linea" };
}
async function run() {
  if (!job) return;
  try {
    FV.setLoading(true);
    const p = params();
    // los valores de los controles mandan sobre el preajuste: se envían sin preajuste
    p.preset = null;
    const { job_id } = await FVApi.postJSON(`${base()}/procesar`, p);
    last = await FVApi.pollJob(job_id);
    show();
  } catch (e) { toast(e.message, "error", 7000); } finally { FV.setLoading(false); }
}
q("#vz-go").onclick = run;

function show() {
  const s = last.stats;
  q("#vz-stats").textContent = `${s.trazados} trazados · ${s.nodos} nodos · ${s.colores} colores · ${s.segundos} s`;
  const cols = q("#vz-cols"); cols.innerHTML = "";
  last.colores.forEach(c => cols.append(h("div", { class: "sp-ink" }, h("span", { class: "sp-sw", style: { background: c.hex } }), h("span", { class: "sp-nm" }, c.nombre), h("small", {}, c.hex))));
  const mm = num("#vz-mm") || "";
  const t = "?t=" + Date.now();
  imgO.src = `${base()}/original.png${t}`;
  imgV.src = `${base()}/vector.svg${t}`;
  q("#vz-dsvg").href = `${base()}/descargar?formato=svg&tam_mm=${mm}`;
  q("#vz-dpdf").href = `${base()}/descargar?formato=pdf&tam_mm=${mm}`;
  q("#vz-deps").href = `${base()}/descargar?formato=eps&tam_mm=${mm}`;
  q("#vz-ddxf").href = `${base()}/descargar?formato=dxf&tam_mm=${mm}`;
  const box = q("#vz-viewer"); box.innerHTML = "";
  const el = h("div", { class: "pane" }); el.append(stage); box.append(el);
  viewer.reset(last.ancho, last.alto);
  pane = viewer.attach(el, stage);
  for (const im of [imgO, imgV]) { im.style.width = last.ancho + "px"; im.style.height = last.alto + "px"; }
  stage.style.width = last.ancho + "px"; stage.style.height = last.alto + "px";
  viewer.fit();
  view();
}
function view() {
  if (!last) return;
  const v = q("#vz-ver").value, op = num("#vz-op") / 100, t = "?t=" + Date.now();
  imgO.style.opacity = 1; imgV.style.opacity = 1;
  imgV.style.visibility = imgO.style.visibility = "visible";
  if (v === "vector") imgO.style.visibility = "hidden";
  else if (v === "original") imgV.style.visibility = "hidden";
  else if (v === "sobre") imgV.style.opacity = op;
  else if (v === "contornos") { imgO.style.opacity = 0.35; imgV.src = `${base()}/contornos.svg${t}`; return; }
  else if (v === "dif") { imgV.src = `${base()}/diferencias.png${t}`; imgO.style.visibility = "hidden"; return; }
  imgV.src = `${base()}/vector.svg${t}`;
}
q("#vz-ver").onchange = view; q("#vz-op").oninput = view;
q("#vz-new").onclick = () => { q("#vz-main").classList.add("hidden"); q("#vz-setup").classList.remove("hidden"); job = null; last = null; };
FVViewer.bindShortcuts(() => (q("#vz-viewer") && q("#vz-viewer").offsetParent ? viewer : null));
})();
