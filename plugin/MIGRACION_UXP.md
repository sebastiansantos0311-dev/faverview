# Migración de CEP a UXP (preparación)

Adobe anunció (septiembre 2026) que Illustrator deja de aceptar extensiones CEP nuevas, las **desactiva por defecto en diciembre de 2028** y las **elimina en
diciembre de 2029**; UXP para Illustrator tendrá beta pública en primavera de 2027 y disponibilidad general en verano de 2027. Este panel se diseñó para
que la migración sea pequeña: **sin Node.js**, con la capa host mínima detrás de una interfaz y HTML/CSS estándar.

## Mapa de piezas
| Pieza actual (CEP) | UXP (esperado) | Dónde cambia |
|---|---|---|
| `CSInterface.evalScript` + ExtendScript (`host/fv_host.jsx`) | API DOM de Illustrator para UXP (JavaScript moderno, `require("illustrator")`) | **Solo** `js/core/host.js` (`HostAdapter`) y la reescritura de `host/*.jsx` como módulo JS |
| `cep.fs` (`js/core/files.js`) | `require("uxp").storage.localFileSystem` (con permisos en el manifest v5) | **Solo** `js/core/files.js` |
| `fetch` a `127.0.0.1` + token | `fetch` con permiso `network.domains` en el manifest | Manifest; `api.js` no cambia |
| `manifest.xml` (CSXS) | `manifest.json` (versión 5) | Nuevo archivo |
| `.zxp` + UPIA | `.ccx` + Creative Cloud / UPIA | `plugin/tools/build_zxp.py` (nuevo empaquetador) |
| `getHostEnvironment` / `ThemeColorChanged` (`theme.js`) | tema de UXP (`uxp.host.theme`) o variables CSS de Spectrum | `js/core/theme.js` |
| Menú «Ventana → Extensiones» | «Ventana → Plugins» | Manifest |

## Lo que ya cumple (comprobado en CI)
- Ningún archivo del panel usa Node (`require(`), `eval` ni `new Function` (`tests/test_plugin_estatico.py`).
- Las APIs de CEP (`__adobe_cep__`, `CSInterface`, `cep.*`) solo aparecen en `host.js`, `files.js` y `CSInterface.js` (test estático).
- Todas las cadenas visibles pasan por `i18n.js`.
- La lógica de geometría (`fv_geom.jsx`) no depende de la API de Illustrator y se prueba con Node; el contrato del host es una lista blanca de funciones con
  entrada/salida JSON, así que se puede reimplementar función por función.

## Pasos cuando exista la beta (primavera de 2027)
1. Crear `PLAN_PLUGIN_UXP.md` a partir de la documentación oficial de UXP para Illustrator (no se inventa aquí).
2. Reescribir `host/fv_host.jsx` como módulo JS UXP que cumpla el mismo contrato (`FV.handlers.*`) y reutilizar `fv_geom` tal cual.
3. Sustituir `host.js` y `files.js`; ejecutar `tests/test_plugin_js.py` y `tests/test_plugin_panel_edge.py` con los nuevos adaptadores simulados.
4. Repetir `PRUEBAS_MANUALES.md` en Illustrator con UXP y publicar el `.ccx`. **Fecha límite: antes de diciembre de 2028.**
