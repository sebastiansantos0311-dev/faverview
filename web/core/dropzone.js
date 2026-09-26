"use strict";
/* Soltar / elegir / pegar (Ctrl+V) / arrastrar desde el navegador. Compartido por todos los módulos. */

const FVDrop = {
  /* archivo a partir de un evento de arrastre (ficheros, URL de imagen o HTML con <img>) */
  async fileFromDrop(dt, onError) {
    if (dt.files && dt.files.length) return dt.files[0];
    let url = (dt.getData("text/uri-list") || "").split("\n")[0].trim();
    if (!url) {
      const m = /<img[^>]+src=["']([^"']+)["']/i.exec(dt.getData("text/html") || "");
      url = m ? m[1] : "";
    }
    if (!url) return null;
    try {
      const b = await (await fetch(url)).blob();
      if (!b.type.startsWith("image/")) return null;
      const ext = (b.type.split("/")[1] || "png").replace("jpeg", "jpg");
      return new File([b], `arrastrada_${Date.now()}.${ext}`, { type: b.type });
    } catch {
      if (onError) onError("No se pudo leer esa imagen desde el navegador (el sitio no lo permite). "
        + "Guárdala o cópiala y pégala con Ctrl+V.");
      return null;
    }
  },

  /* enlaza una caja: clic → selector, arrastrar y soltar */
  bind(box, input, onFile, onError) {
    box.addEventListener("click", e => { if (!e.target.closest(".pagesel, select, button")) input.click(); });
    input.addEventListener("change", () => input.files[0] && onFile(input.files[0]));
    ["dragenter", "dragover"].forEach(ev => box.addEventListener(ev, e => { e.preventDefault(); box.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => box.addEventListener(ev, e => { e.preventDefault(); box.classList.remove("over"); }));
    box.addEventListener("drop", async e => { const f = await FVDrop.fileFromDrop(e.dataTransfer, onError); if (f) onFile(f); });
  },

  /* Ctrl+V con una imagen en el portapapeles: llama a handler(File) solo si `active()` es verdadero */
  bindPaste(handler, active = () => true) {
    document.addEventListener("paste", e => {
      if (!active()) return;
      const it = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/"));
      if (!it) return;
      const blob = it.getAsFile();
      if (!blob) return;
      e.preventDefault();
      const ext = (it.type.split("/")[1] || "png").replace("jpeg", "jpg");
      handler(new File([blob], `pegado_${Date.now()}.${ext}`, { type: it.type }));
    });
  },
};

window.FVDrop = FVDrop;
