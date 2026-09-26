"use strict";
(function () {
/* Llamadas a la API, subida de archivos y sondeo de trabajos en segundo plano (/api/jobs/{id}). */

async function api(url, opts) {
  let r;
  try { r = await fetch(url, opts); }
  catch { throw new Error("No se pudo conectar con FAVERVIEW. ¿Está abierta la ventana de consola?"); }
  if (!r.ok) {
    let d = "Ocurrió un error inesperado.";
    try { const j = await r.json(); d = (typeof j.error === "string" && j.error) || (typeof j.detail === "string" && j.detail) || d; } catch {}
    throw new Error(d);
  }
  return r;
}

const getJSON = async url => (await api(url)).json();
const postJSON = async (url, body) => (await api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
const postForm = async (url, fields) => {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== null && v !== undefined) fd.append(k, v);
  return (await api(url, { method: "POST", body: fd })).json();
};

/* consulta el progreso por etapas hasta que termina; `onProgress(mensaje, 0..1)` es opcional */
async function pollJob(id, onProgress) {
  for (;;) {
    const st = await (await api("/api/jobs/" + id)).json();
    (onProgress || FV.setProgress)(st.message, st.pct);
    if (st.status === "done") return st.result;
    if (st.status === "error") throw new Error(st.error || "Ocurrió un error inesperado.");
    await new Promise(r => setTimeout(r, 350));
  }
}

window.FVApi = { api, getJSON, postJSON, postForm, pollJob };
})();
