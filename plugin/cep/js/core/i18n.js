/* Textos del panel (español). Toda cadena visible pasa por FVP.t(): listo para agregar idiomas. */
(function (g) {
  "use strict";
  var FVP = g.FVP = g.FVP || {};
  var ES = {
    "app.title": "FAVERVIEW",
    "estado.verde": "Conectado a FAVERVIEW {version}",
    "estado.amarillo.servidor": "Versión incompatible: actualiza FAVERVIEW (el servidor es demasiado antiguo)",
    "estado.amarillo.plugin": "Versión incompatible: actualiza el plugin (FAVERVIEW es más nuevo)",
    "estado.rojo": "FAVERVIEW no está abierto",
    "estado.rojo.ayuda": "Abre FAVERVIEW desde su acceso directo y pulsa Reintentar.",
    "estado.reintentar": "Reintentar",
    "tab.vectorizar": "Vectorizar", "tab.preflight": "Preflight", "tab.separar": "Separar", "tab.comparar": "Comparar",
    "tab.codigos": "Códigos", "tab.trap": "Trap", "tab.ajustes": "Ajustes",
    "comun.cancelar": "Cancelar", "comun.procesando": "Procesando…", "comun.sin_doc": "Abre un documento en Illustrator.",
    "comun.error": "Ocurrió un error: {mensaje}", "comun.listo": "Listo.", "comun.mesa_actual": "Mesa actual", "comun.todas": "Todas las mesas",
    "comun.cancelado": "Operación cancelada.", "comun.tamano_max": "El archivo supera el máximo de {mb} MB.", "comun.mesa": "Mesa",
    "vec.titulo": "Vectorizar la imagen seleccionada", "vec.preajuste": "Preajuste", "vec.colores": "Colores", "vec.detalle": "Detalle mínimo (mm)",
    "vec.limpia": "Geometría limpia", "vec.biblioteca": "Usar tintas de la biblioteca", "vec.trap": "Añadir trap", "vec.tamano": "Tamaño final (mm de ancho)",
    "vec.vista": "Vista previa", "vec.vectorizar": "Vectorizar", "vec.colocar": "Colocar sobre la imagen", "vec.ocultar": "Ocultar la imagen original",
    "vec.estadisticas": "{trazados} trazados · {nodos} nodos · {colores} colores · {segundos} s",
    "vec.selecciona": "Selecciona una imagen (colocada o incrustada).",
    "pf.titulo": "Preflight", "pf.perfil": "Perfil", "pf.revisar_mesa": "Revisar mesa actual", "pf.revisar_todas": "Revisar todas las mesas",
    "pf.marcar": "Marcar todos en el documento", "pf.quitar": "Quitar marcas", "pf.errores": "Errores", "pf.advertencias": "Advertencias", "pf.info": "Información",
    "pf.sin_problemas": "Sin problemas con este perfil.", "pf.corregir": "Correcciones en Illustrator", "pf.aplicar": "Aplicar", "pf.afectados": "{n} objeto(s) afectado(s)",
    "pf.confirmar": "¿Aplicar «{nombre}» a {n} objeto(s)? Se puede deshacer con Ctrl+Z.", "pf.solo_reporta": "Esta corrección no se puede hacer con seguridad desde Illustrator: solo se reporta.",
    "pf.fix.sobreimpresion": "Sobreimpresión en tintas técnicas", "pf.fix.negro": "Texto negro pequeño a K 100 % con sobreimpresión",
    "pf.fix.unir": "Unir muestras spot duplicadas", "pf.fix.sin_uso": "Eliminar muestras sin uso", "pf.fix.rgb": "Convertir RGB a CMYK",
    "sep.titulo": "Separaciones y tintas", "sep.analizar": "Analizar separaciones", "sep.tintas": "Tintas", "sep.sin_muestra": "Tinta del PDF sin muestra en el documento",
    "sep.muestra_sin_uso": "Muestra spot sin uso en el PDF", "sep.tac": "Cobertura total máxima {v} %", "sep.exportar": "Exportar placas…", "sep.abrir": "Abrir en FAVERVIEW",
    "sep.solo": "Solo", "sep.negativo": "Negativo", "sep.medida": "TAC {tac} % — {tintas}", "sep.densitometro": "Toca la vista previa para medir", "sep.hallazgos": "Problemas de separación",
    "cmp.titulo": "Comparar con el arte del cliente", "cmp.elegir": "Elegir arte del cliente…", "cmp.pegar": "Pegar imagen", "cmp.comparar": "Comparar con la mesa actual",
    "cmp.similitud": "Similitud {pct} %", "cmp.ver": "Ver comparación completa en FAVERVIEW", "cmp.sin_dif": "Sin diferencias.", "cmp.pegado": "Imagen pegada", "cmp.sin_arte": "Elige primero el arte del cliente.",
    "cod.titulo": "Código de barras", "cod.tipo": "Tipo", "cod.datos": "Datos", "cod.mag": "Magnificación %", "cod.bwr": "Reducción de barras (µm)", "cod.tinta": "Tinta",
    "cod.insertar": "Insertar", "cod.verificar": "Verificar códigos del documento", "cod.braille": "Braille", "cod.texto": "Texto en braille", "cod.grado": "Grado estimado {g} (no certificado)",
    "cod.negro": "Negro (K 100 %)", "cod.sin_codigos": "No se detectó ningún código legible.",
    "trap.titulo": "Trap (reventado)", "trap.perfil": "Perfil de máquina", "trap.tol": "Tolerancia de movimiento (mm)", "trap.analizar": "Analizar registro",
    "trap.crear": "Crear traps vectoriales", "trap.ok": "✔ Sin filetes con ±{tol} mm", "trap.mal": "✘ {mm2} mm² de filetes con ±{tol} mm: ver marcadores",
    "trap.limite": "Este arte tiene degradados, transparencias o imágenes: usa la exportación de placas con trap (ráster) en FAVERVIEW.",
    "trap.ayuda": "También puedes usar Buscatrazos → Reventar (Trap) de Illustrator para casos simples.", "trap.estimacion": "Estimación orientativa: confirma con tu imprenta.",
    "aj.titulo": "Ajustes", "aj.preset": "Preajuste de PDF", "aj.version": "Versión del panel {v}", "aj.actualizacion": "Hay una versión nueva del plugin: {v}", "aj.servidor": "Servidor: {url}",
    "aj.limpiar": "Borrar temporales", "aj.descargar": "Descargar"
  };
  var TABLES = { es: ES };
  FVP.lang = "es";
  FVP.t = function (key, params) {
    var s = (TABLES[FVP.lang] || ES)[key];
    if (s === undefined) { s = ES[key]; }
    if (s === undefined) { return key; }
    if (params) { s = s.replace(/\{(\w+)\}/g, function (m, k) { return params[k] === undefined ? m : String(params[k]); }); }
    return s;
  };
  FVP.i18nKeys = function () { var k = []; for (var n in ES) { if (ES.hasOwnProperty(n)) { k.push(n); } } return k; };
}(typeof window !== "undefined" ? window : globalThis));
