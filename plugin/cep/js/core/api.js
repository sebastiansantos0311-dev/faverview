/* Conexión con el servidor local de FAVERVIEW: plugin.json → handshake → peticiones con token, subida/descarga de archivos y trabajos. */
(function (g) {
  "use strict";
  var FVP = g.FVP = g.FVP || {};
  var API_VERSION_ESPERADA = 1;

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  FVP.api = {
    API_VERSION_ESPERADA: API_VERSION_ESPERADA,
    state: { estado: "rojo", base: null, token: null, version: null, mensaje: "" },
    _fetch: null,                                     // inyectable en pruebas
    _f: function () { return FVP.api._fetch || g.fetch.bind(g); },

    /** ruta del archivo de conexión (mismo lugar que escribe el servidor) */
    connectionFile: function () { return FVP.host.systemPath("userData") + "/FAVERVIEW/plugin.json"; },

    /** lee plugin.json y hace el handshake. Estados: verde | amarillo (versión incompatible) | rojo (sin conexión) */
    connect: function () {
      var st = FVP.api.state;
      st.estado = "rojo"; st.base = null; st.token = null;
      var info;
      try { info = JSON.parse(FVP.files.readText(FVP.api.connectionFile())); } catch (e) {
        st.mensaje = FVP.t("estado.rojo");
        return Promise.resolve(st);
      }
      st.base = "http://127.0.0.1:" + info.puerto; st.token = info.token;
      return FVP.api.get("/api/plugin/handshake").then(function (hs) {
        st.version = hs.version;
        if (hs.api_version > API_VERSION_ESPERADA) { st.estado = "amarillo"; st.mensaje = FVP.t("estado.amarillo.plugin"); st.motivo = "plugin"; }
        else if (hs.api_version < API_VERSION_ESPERADA) { st.estado = "amarillo"; st.mensaje = FVP.t("estado.amarillo.servidor"); st.motivo = "servidor"; }
        else { st.estado = "verde"; st.mensaje = FVP.t("estado.verde", { version: hs.version }); st.motivo = null; }
        st.handshake = hs;
        return st;
      }, function () {
        st.estado = "rojo"; st.mensaje = FVP.t("estado.rojo");
        return st;
      });
    },

    _headers: function (extra) {
      var h = { "X-FAVERVIEW-Token": FVP.api.state.token || "" };
      for (var k in extra) { if (extra.hasOwnProperty(k)) { h[k] = extra[k]; } }
      return h;
    },

    _check: function (resp) {
      if (resp.ok) { return resp; }
      return resp.text().then(function (txt) {
        var msg = "Error " + resp.status;
        try { var j = JSON.parse(txt); msg = j.error || j.detail || msg; } catch (e) { /* texto plano */ }
        if (resp.status === 401) { msg = "FAVERVIEW rechazó la conexión (token no válido). Pulsa Reintentar."; }
        throw new Error(msg);
      });
    },

    request: function (path, opts) {
      opts = opts || {};
      var headers = FVP.api._headers(opts.json ? { "Content-Type": "application/json" } : {});
      var init = { method: opts.method || (opts.json || opts.form ? "POST" : "GET"), headers: headers };
      if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); }
      if (opts.form) { init.body = opts.form; }
      return FVP.api._f()(FVP.api.state.base + path, init).then(FVP.api._check);
    },
    get: function (path) { return FVP.api.request(path).then(function (r) { return r.json(); }); },
    postJSON: function (path, body) { return FVP.api.request(path, { json: body }).then(function (r) { return r.json(); }); },

    /** multipart: `campos` = {nombre: valor}; `archivos` = {nombre: {blob, nombre}} */
    postForm: function (path, campos, archivos) {
      var fd = new g.FormData(), k;
      for (k in campos) { if (campos.hasOwnProperty(k) && campos[k] !== null && campos[k] !== undefined) { fd.append(k, typeof campos[k] === "object" ? JSON.stringify(campos[k]) : String(campos[k])); } }
      for (k in archivos) { if (archivos.hasOwnProperty(k)) { fd.append(k, archivos[k].blob, archivos[k].nombre); } }
      return FVP.api.request(path, { form: fd }).then(function (r) { return r.json(); });
    },

    /** sube el archivo de `ruta` comprobando el tamaño máximo del servidor */
    uploadFile: function (path, campo, ruta, campos, mime) {
      var mb = FVP.files.sizeMB(ruta), max = (FVP.api.state.handshake && FVP.api.state.handshake.max_upload_mb) || 200;
      if (mb > max) { return Promise.reject(new Error(FVP.t("comun.tamano_max", { mb: max }))); }
      var arch = {}, nombre = ruta.split(/[\\/]/).pop();
      arch[campo] = { blob: FVP.files.readBlob(ruta, mime), nombre: nombre };
      return FVP.api.postForm(path, campos || {}, arch);
    },

    /** baja un archivo del servidor y lo guarda en `destino` */
    downloadToFile: function (url, destino) {
      return FVP.api.request(url).then(function (r) { return r.arrayBuffer(); }).then(function (ab) { return FVP.files.writeArrayBuffer(destino, ab); });
    },
    downloadBlob: function (url) { return FVP.api.request(url).then(function (r) { return r.blob(); }); },

    /** espera un trabajo (/api/jobs/{id}) con progreso y cancelación. `ctl` = {cancelado: bool} */
    pollJob: function (id, onProgress, ctl) {
      ctl = ctl || {};
      function step() {
        if (ctl.cancelado) {
          return FVP.api.request("/api/jobs/" + id + "/cancel", { method: "POST" }).then(function () { return step2(); }, function () { return step2(); });
        }
        return step2();
      }
      function step2() {
        return FVP.api.get("/api/jobs/" + id).then(function (st) {
          if (onProgress) { onProgress(st.message, st.pct); }
          if (st.status === "done") { return st.result; }
          if (st.status === "error") { throw new Error(st.error || "Error en el servidor."); }
          return sleep(FVP.api.pollMs || 350).then(step);
        });
      }
      return step();
    },
    pollMs: 350
  };
}(typeof window !== "undefined" ? window : globalThis));
