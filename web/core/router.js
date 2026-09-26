"use strict";
/* Enrutador por hash: #/comparar, #/separar, #/vectorizar, #/preflight, #/codigos, #/herramientas, #/automatizar.
   Cada módulo tiene un fragmento HTML y un script que se cargan la primera vez que se visita su pestaña; después la
   vista solo se muestra u oculta (así conserva su estado al cambiar de pestaña). */

const FVRouter = {
  modules: {
    comparar: { titulo: "Comparar", html: "/static/modules/compare.html", js: ["/static/modules/compare.js"] },
    separar: { titulo: "Separar colores", html: "/static/modules/separate.html", js: ["/static/modules/separate.js"] },
    vectorizar: { titulo: "Vectorizar", soon: "Convierte imágenes en vectores por tintas, sin huecos entre colores." },
    preflight: { titulo: "Preflight", soon: "Revisión técnica de PDF con perfiles: fuentes, imágenes, tintas, sangrado y más." },
    codigos: { titulo: "Códigos de barras", soon: "Generar y verificar EAN, GS1, DataMatrix y QR." },
    herramientas: { titulo: "Herramientas", soon: "Trapping, step & repeat, distorsión flexo, braille, gama extendida y prueba en pantalla." },
    automatizar: { titulo: "Automatizar", soon: "Recetas y carpetas vigiladas para encadenar los módulos." },
  },
  status: null,        // respuesta de /api/status (se rellena en main.js)
  current: null,
  loaded: {},

  current_name() { return (location.hash.replace(/^#\/?/, "") || "comparar").split("/")[0]; },

  async go() {
    const name = this.current_name();
    const mod = this.modules[name] || this.modules.comparar;
    const key = this.modules[name] ? name : "comparar";
    document.querySelectorAll(".maintabs a").forEach(a => a.classList.toggle("active", a.dataset.mod === key));
    document.querySelectorAll("#vista > .vista").forEach(s => s.classList.add("hidden"));
    let sec = document.getElementById("vista-" + key);
    if (!sec) {
      sec = document.createElement("section");
      sec.id = "vista-" + key;
      sec.className = "vista";
      document.getElementById("vista").append(sec);
    }
    sec.classList.remove("hidden");
    document.title = `FAVERVIEW · ${mod.titulo}`;
    this.current = key;
    if (this.loaded[key]) return;
    this.loaded[key] = true;
    if (mod.soon) {
      sec.innerHTML = `<div class="soon"><h2>${mod.titulo}</h2><p>Próximamente.</p><p class="hint">${mod.soon}</p></div>`;
      return;
    }
    sec.innerHTML = await (await fetch(mod.html)).text();
    for (const src of mod.js) await this._script(src);
    window.dispatchEvent(new CustomEvent("fv:mounted", { detail: key }));
  },

  _script(src) {
    return new Promise((ok, err) => {
      const s = document.createElement("script");
      s.src = src + "?v=" + (this.version || "0");
      s.onload = ok;
      s.onerror = () => err(new Error("No se pudo cargar " + src));
      document.body.append(s);
    });
  },
};

window.addEventListener("hashchange", () => FVRouter.go());
window.FVRouter = FVRouter;
