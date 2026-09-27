/* CSInterface mínimo de FAVERVIEW (implementación propia, licencia AGPL-3.0-or-later del proyecto).
 * Envuelve window.__adobe_cep__ (API nativa de CEP) con la misma superficie que usa el panel. Se puede reemplazar por el
 * CSInterface.js oficial de Adobe (Adobe-CEP/CEP-Resources) sin cambiar el resto del panel. */
function SystemPath() {}
SystemPath.USER_DATA = "userData";
SystemPath.COMMON_FILES = "commonFiles";
SystemPath.MY_DOCUMENTS = "myDocuments";
SystemPath.APPLICATION = "application";
SystemPath.EXTENSION = "extension";
SystemPath.HOST_APPLICATION = "hostApplication";

function CSInterface() {}
CSInterface.prototype.hostEnvironment = null;

CSInterface.prototype.evalScript = function (script, callback) {
  if (callback === null || callback === undefined) { callback = function () {}; }
  window.__adobe_cep__.evalScript(script, callback);
};
CSInterface.prototype.getHostEnvironment = function () {
  this.hostEnvironment = JSON.parse(window.__adobe_cep__.getHostEnvironment());
  return this.hostEnvironment;
};
CSInterface.prototype.getSystemPath = function (pathType) {
  var path = decodeURI(window.__adobe_cep__.getSystemPath(pathType));
  if (navigator.platform.indexOf("Win") !== -1) { path = path.replace(/\\/g, "/"); }
  return path;
};
CSInterface.prototype.addEventListener = function (type, listener, obj) {
  window.__adobe_cep__.addEventListener(type, listener, obj);
};
CSInterface.prototype.removeEventListener = function (type, listener, obj) {
  window.__adobe_cep__.removeEventListener(type, listener, obj);
};
CSInterface.prototype.getExtensionID = function () {
  return window.__adobe_cep__.getExtensionId();
};
CSInterface.prototype.closeExtension = function () {
  window.__adobe_cep__.closeExtension();
};
CSInterface.prototype.openURLInDefaultBrowser = function (url) {
  if (window.cep && window.cep.util) { return window.cep.util.openURLInDefaultBrowser(url); }
};
