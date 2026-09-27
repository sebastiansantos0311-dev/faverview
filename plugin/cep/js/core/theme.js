/* Tema claro/oscuro según la interfaz de Illustrator (appSkinInfo) y el evento ThemeColorChanged. */
(function (g) {
  "use strict";
  var FVP = g.FVP = g.FVP || {};

  function luminance(c) { return (0.299 * c.red + 0.587 * c.green + 0.114 * c.blue) / 255; }

  FVP.theme = {
    /** "dark" si el fondo del panel es oscuro */
    fromSkin: function (skin) {
      if (!skin || !skin.panelBackgroundColor || !skin.panelBackgroundColor.color) { return "dark"; }
      return luminance(skin.panelBackgroundColor.color) < 0.5 ? "dark" : "light";
    },
    apply: function (skin) {
      var mode = FVP.theme.fromSkin(skin);
      if (g.document && g.document.documentElement) { g.document.documentElement.setAttribute("data-theme", mode); }
      if (skin && skin.panelBackgroundColor && g.document && g.document.documentElement) {
        var c = skin.panelBackgroundColor.color;
        g.document.documentElement.style.setProperty("--bg", "rgb(" + Math.round(c.red) + "," + Math.round(c.green) + "," + Math.round(c.blue) + ")");
      }
      return mode;
    },
    init: function () {
      try {
        var env = FVP.host.hostEnvironment();
        FVP.theme.apply(env.appSkinInfo);
        FVP.host.addEventListener("com.adobe.csxs.events.ThemeColorChanged", function () {
          FVP.theme.apply(FVP.host.hostEnvironment().appSkinInfo);
        });
      } catch (e) { FVP.theme.apply(null); }
    }
  };
}(typeof window !== "undefined" ? window : globalThis));
