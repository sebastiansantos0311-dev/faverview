/* JSON minimo para ExtendScript (ES3), que no trae JSON. Implementacion propia: stringify y parse. */
if (typeof JSON === "undefined") { JSON = {}; }
(function () {
  var esc = { "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r", '"': '\\"', "\\": "\\\\" };
  function quote(s) {
    return '"' + String(s).replace(/[\\"\u0000-\u001f\u007f-\uffff]/g, function (c) {
      if (esc[c]) { return esc[c]; }
      var h = c.charCodeAt(0).toString(16);
      return "\\u" + ("0000" + h).slice(-4);
    }) + '"';
  }
  function str(v) {
    var t = typeof v, i, out, k;
    if (v === null || v === undefined) { return "null"; }
    if (t === "number") { return isFinite(v) ? String(v) : "null"; }
    if (t === "boolean") { return String(v); }
    if (t === "string") { return quote(v); }
    if (t === "function") { return "null"; }
    if (Object.prototype.toString.call(v) === "[object Array]") {
      out = [];
      for (i = 0; i < v.length; i++) { out.push(str(v[i])); }
      return "[" + out.join(",") + "]";
    }
    out = [];
    for (k in v) {
      if (Object.prototype.hasOwnProperty.call(v, k) && typeof v[k] !== "function" && v[k] !== undefined) { out.push(quote(k) + ":" + str(v[k])); }
    }
    return "{" + out.join(",") + "}";
  }
  if (typeof JSON.stringify !== "function") { JSON.stringify = function (v) { return str(v); }; }
  if (typeof JSON.parse !== "function") {
    JSON.parse = function (text) {
      var t = String(text);
      // validacion (RFC 4627, seccion 6): solo estructuras JSON antes de evaluar
      var probe = t.replace(/\\(?:["\\\/bfnrt]|u[0-9a-fA-F]{4})/g, "@")
                   .replace(/"[^"\\\n\r]*"|true|false|null|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?/g, "]")
                   .replace(/(?:^|:|,)(?:\s*\[)+/g, "");
      if (!/^[\],:{}\s]*$/.test(probe)) { throw new SyntaxError("JSON no v\u00e1lido"); }
      return eval("(" + t + ")");
    };
  }
}());
