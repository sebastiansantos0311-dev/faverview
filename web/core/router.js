"use strict";
/* Enrutador por hash: #/comparar, #/separar, #/vectorizar, #/preflight, #/codigos, #/herramientas, #/automatizar.
   Cada módulo tiene un fragmento HTML y un script que se cargan la primera vez que se visita su pestaña; después la
   vista solo se muestra u oculta (así conserva su estado al cambiar de pestaña). */

const FVRouter = {
  modules: {
    comparar: { titulo: "Comparar", html: "/static/modules/compare.html", js: ["/static/modules/compare.js"] },
    separar: { titulo: "Separar colores", html: "/static/modules/separate.html", js: ["/static/modules/separate.js", "/static/modules/separate_img.js"] },
    vectorizar: { titulo: "Vectorizar", html: "/static/modules/vectorize.html", js: ["/static/modules/vectorize.js"] },
    preflight: { titulo: "Preflight", html: "/static/modules/preflight.html", js: ["/static/modules/preflight.js"] },
    codigos: { titulo: "Códigos de barras", html: "/static/modules/barcodes.html", js: ["/static/modules/barcodes.js"] },
    herramientas: { titulo: "Herramientas", html: "/static/modules/tools.html", js: ["/static/modules/tools.js"] },
    automatizar: { titulo: "Automatizar", html: "/static/modules/automation.html", js: ["/static/modules/automation.js"] },
  },
  /* «Enviar a…»: el último archivo soltado se pasa a otro módulo sin volver a subirlo. */
  inbox: {},
  targets(file) {
    const pdf = /\.pdf$/i.test(file.name);
    return pdf ? [["separar", "Separar colores"], ["preflight", "Preflight"], ["codigos", "Códigos de barras"], ["herramientas", "Herramientas"], ["automatizar", "Automatizar"]]
               : [["separar", "Separar colores (imagen)"], ["vectorizar", "Vectorizar"], ["codigos", "Códigos de barras"], ["automatizar", "Automatizar"]];
  },
  send(mod, file) { this.inbox[mod] = file; if (this.current_name() === mod) this._deliver(mod); else location.hash = "#/" + mod; },
  _deliver(mod) {
    const f = this.inbox[mod];
    if (!f) return;
    const pdf = /\.pdf$/i.test(f.name);
    const sel = { separar: pdf ? "#sp-drop input" : "#si-drop input", vectorizar: "#vz-drop input", preflight: "#pf-drop input",
                  codigos: "#bc-drop input", herramientas: "#tl-drop input", automatizar: "#au-drop input" }[mod];
    const sec = document.getElementById("vista-" + mod);
    if (!sec) return;
    if (mod === "separar") sec.querySelector(`.sep-tabs [data-sub="${pdf ? "pdf" : "img"}"]`)?.click();
    if (mod === "codigos") sec.querySelector('.sep-tabs [data-sub="ver"]')?.click();
    const inp = sec.querySelector(sel);
    if (!inp) return;
    delete this.inbox[mod];
    const dt = new DataTransfer(); dt.items.add(f); inp.files = dt.files; inp.dispatchEvent(new Event("change"));
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
    if (this.loaded[key]) { this._deliver(key); return; }
    this.loaded[key] = true;
    if (mod.soon) {
      sec.innerHTML = `<div class="soon"><h2>${mod.titulo}</h2><p>Próximamente.</p><p class="hint">${mod.soon}</p></div>`;
      return;
    }
    sec.innerHTML = await (await fetch(mod.html)).text();
    for (const src of mod.js) await this._script(src);
    window.dispatchEvent(new CustomEvent("fv:mounted", { detail: key }));
    setTimeout(() => this._deliver(key), 50);
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
