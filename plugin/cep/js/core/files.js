/* Archivos entre el panel y el disco con la API nativa de CEP (window.cep.fs), sin Node.js. */
(function (g) {
  "use strict";
  var FVP = g.FVP = g.FVP || {};

  function fsApi() { return FVP.files._fs || (g.cep && g.cep.fs); }
  function enc() { return (g.cep && g.cep.encoding) || FVP.files._enc || { Base64: "Base64", UTF8: "UTF-8" }; }

  function b64ToBlob(b64, mime) {
    var bin = atob(b64), n = bin.length, u8 = new Uint8Array(n), i;
    for (i = 0; i < n; i++) { u8[i] = bin.charCodeAt(i); }
    return new Blob([u8], { type: mime || "application/octet-stream" });
  }
  function abToB64(ab) {
    var u8 = new Uint8Array(ab), CH = 0x8000, s = "", i;
    for (i = 0; i < u8.length; i += CH) { s += String.fromCharCode.apply(null, u8.subarray(i, i + CH)); }
    return btoa(s);
  }
  function check(r, what) {
    if (r && r.err) { throw new Error(what + " (código " + r.err + ")."); }
    return r;
  }

  FVP.files = {
    _fs: null, _enc: null,
    b64ToBlob: b64ToBlob, arrayBufferToBase64: abToB64,
    readText: function (path) { return check(fsApi().readFile(path, enc().UTF8), "No se pudo leer " + path).data; },
    readBlob: function (path, mime) { return b64ToBlob(check(fsApi().readFile(path, enc().Base64), "No se pudo leer " + path).data, mime); },
    writeArrayBuffer: function (path, ab) { check(fsApi().writeFile(path, abToB64(ab), enc().Base64), "No se pudo escribir " + path); return path; },
    writeText: function (path, text) { check(fsApi().writeFile(path, text, enc().UTF8), "No se pudo escribir " + path); return path; },
    exists: function (path) { var r = fsApi().stat(path); return !!r && !r.err; },
    /** tamaño en MB (para avisar antes de subir) */
    sizeMB: function (path) { var r = fsApi().stat(path); return r && !r.err ? r.data.size / 1048576 : 0; },
    openDialog: function (title, types) {
      var r = fsApi().showOpenDialogEx(false, false, title, "", types || [], "");
      return r && !r.err && r.data && r.data.length ? r.data[0] : null;
    },
    saveDialog: function (title, defaultName, types) {
      var r = fsApi().showSaveDialogEx(title, "", types || [], defaultName, "");
      return r && !r.err && r.data ? r.data : null;
    },
    /** borra archivos de la carpeta de temporales con más de `hours` horas */
    cleanTemp: function (dir, hours) {
      var r = fsApi().readdir(dir), limit = Date.now() - (hours || 24) * 3600000, n = 0, i;
      if (!r || r.err) { return 0; }
      for (i = 0; i < r.data.length; i++) {
        var p = dir + "/" + r.data[i], st = fsApi().stat(p);
        if (st && !st.err && st.data.mtime && new Date(st.data.mtime).getTime() < limit) { fsApi().deleteFile(p); n++; }
      }
      return n;
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
