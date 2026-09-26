"use strict";
(function () {
/* Módulo Vectorizar (S4). */
const { h, toast } = FV;
const root = document.getElementById("vista-vectorizar");
const q = s => root.querySelector(s);
let job = null, last = null, pane = null, timer = null, sel = 0, drawZone = false;
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
    bn: q("#vz-preset").value === "linea", primitivas: q("#vz-prim").checked, geometria_limpia: q("#vz-limpia").checked,
    simetria: q("#vz-sim").checked, trazos: q("#vz-trazos").checked, engrosar_mm: num("#vz-eng"), texto: q("#vz-texto").value,
    fuente: q("#vz-fuente").value || "Arial" };
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

function show(keep) {
  const s = last.stats;
  q("#vz-stats").textContent = `${s.trazados} trazados · ${s.nodos} nodos · ${s.colores} colores · ${s.segundos} s`;
  const cols = q("#vz-cols"); cols.innerHTML = "";
  if (sel >= last.colores.length) sel = 0;
  last.colores.forEach(c => cols.append(h("div", { class: "sp-ink" + (c.i === sel ? " sel" : ""), onclick: () => { sel = c.i; q("#vz-recol").value = c.hex; show(true); } },
    h("span", { class: "sp-sw", style: { background: c.hex } }), h("span", { class: "sp-nm" }, c.nombre), h("small", {}, c.hex))));
  if (keep) return;
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

async function editar(body, msg) {
  try {
    FV.setLoading(true);
    last = Object.assign(last, await FVApi.postJSON(`${base()}/editar`, body));
    toast(msg, "ok");
    show();
  } catch (e) { toast(e.message, "error", 7000); } finally { FV.setLoading(false); }
}
q("#vz-unir").onclick = () => { if (last.colores.length < 2) return; editar({ op: "unir", a: sel, b: (sel + 1) % last.colores.length }, "Colores unidos."); };
q("#vz-borrar").onclick = () => editar({ op: "borrar", a: sel }, "Región borrada.");
q("#vz-recol").onchange = e => editar({ op: "recolorear", a: sel, color: e.target.value }, "Color cambiado.");
q("#vz-zona").onclick = () => { drawZone = true; toast("Arrastra un rectángulo sobre la imagen.", "info"); };
viewer.onPointerDown = (p, ev) => {
  if (!drawZone) return false;
  const [x0, y0] = viewer.toImg(p, ev);
  const rect = h("div", { style: { position: "absolute", border: "2px dashed #eab308", pointerEvents: "none" } });
  stage.append(rect);
  const mv = e2 => { const [x, y] = viewer.toImg(p, e2); Object.assign(rect.style, { left: Math.min(x, x0) + "px", top: Math.min(y, y0) + "px", width: Math.abs(x - x0) + "px", height: Math.abs(y - y0) + "px" }); };
  const up = e2 => {
    p.el.removeEventListener("pointermove", mv);
    const [x, y] = viewer.toImg(p, e2); rect.remove(); drawZone = false;
    editar({ op: "zona", zona: [Math.round(Math.min(x, x0)), Math.round(Math.min(y, y0)), Math.round(Math.abs(x - x0)), Math.round(Math.abs(y - y0))], k_max: num("#vz-k") + 2 }, "Zona vuelta a trazar.");
  };
  p.el.addEventListener("pointermove", mv); p.el.addEventListener("pointerup", up, { once: true });
  return true;
};
})();
