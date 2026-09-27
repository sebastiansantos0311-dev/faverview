/* FAVERVIEW - crea en Illustrator el documento de prueba de PRUEBAS_MANUALES.md (ExtendScript).
 *
 * Como usarlo: Archivo > Scripts > Otro script... y elige este archivo. Crea un documento CMYK con 3 mesas de trabajo desplazadas
 * (para probar la geometria de las marcas y el zoom) con errores conocidos:
 *   Mesa 1: rectangulo con la muestra spot "Troquel" SIN sobreimpresion, texto negro enriquecido de 8 pt, dos muestras duplicadas
 *           ("Pantone 485C" y "PANTONE 485 C") usadas cada una en un rectangulo, y una muestra "Sin uso".
 *   Mesa 2: dos rectangulos de tintas directas que se tocan (para probar el trap: filetes con el perfil de serigrafia).
 *   Mesa 3: rectangulo de 3 tintas sin errores (para comprobar que no hay falsos positivos) y un rectangulo pegado al borde.
 * No guarda nada: el documento queda abierto y sin guardar. */
(function () {
  var W = 300, H = 200, GAP = 100;
  var doc = app.documents.add(DocumentColorSpace.CMYK, W, H, 3, DocumentArtboardLayout.GridByRow, GAP, 3);
  var abs = doc.artboards, i;
  // mesa 2 y 3 en posiciones desplazadas (una de ellas por debajo del origen)
  abs[0].artboardRect = [0, H, W, 0];
  abs[1].artboardRect = [W + GAP, H, 2 * W + GAP, 0];
  abs[2].artboardRect = [-400, -50, -400 + W, -50 - H];

  function spot(name, c, m, y, k) {
    var s = doc.spots.add();
    s.name = name; s.colorType = ColorModel.SPOT;
    var col = new CMYKColor(); col.cyan = c; col.magenta = m; col.yellow = y; col.black = k;
    s.color = col;
    return s;
  }
  function spotColor(s) { var sc = new SpotColor(); sc.spot = s; sc.tint = 100; return sc; }
  function rect(l, t, w, h, color) {
    var r = doc.pathItems.rectangle(t, l, w, h);
    r.filled = true; r.fillColor = color; r.stroked = false;
    return r;
  }
  function cmyk(c, m, y, k) { var x = new CMYKColor(); x.cyan = c; x.magenta = m; x.yellow = y; x.black = k; return x; }

  var troquel = spot("Troquel", 0, 100, 100, 0);
  var p1 = spot("Pantone 485C", 0, 95, 100, 0), p2 = spot("PANTONE 485 C", 0, 95, 100, 0);
  spot("Sin uso", 50, 0, 50, 0);
  var amarillo = spot("Amarillo Demo", 0, 0, 100, 0), azul = spot("Azul Demo", 100, 50, 0, 0);
  var verde = spot("Verde Demo", 80, 0, 90, 0);

  // Mesa 1
  var r = abs[0].artboardRect;
  rect(r[0] + 20, r[1] - 20, 120, 80, spotColor(troquel)).name = "troquel_sin_overprint";
  rect(r[0] + 160, r[1] - 20, 60, 60, spotColor(p1)).name = "pantone_1";
  rect(r[0] + 230, r[1] - 20, 60, 60, spotColor(p2)).name = "pantone_2";
  var t = doc.textFrames.add();
  t.contents = "Texto negro enriquecido 8 pt"; t.position = [r[0] + 20, r[1] - 120];
  t.textRange.characterAttributes.size = 8;
  t.textRange.characterAttributes.fillColor = cmyk(60, 50, 50, 100);

  // Mesa 2: dos tintas que se tocan
  r = abs[1].artboardRect;
  rect(r[0] + 20, r[1] - 40, 100, 100, spotColor(amarillo)).name = "amarillo";
  rect(r[0] + 120, r[1] - 40, 100, 100, spotColor(azul)).name = "azul";

  // Mesa 3: sin errores + un objeto pegado al borde
  r = abs[2].artboardRect;
  rect(r[0] + 40, r[1] - 40, 100, 60, spotColor(verde)).name = "verde";
  rect(r[0] + 160, r[1] - 40, 100, 60, cmyk(0, 0, 0, 100)).name = "negro";
  rect(r[0], r[1], 20, H, cmyk(0, 100, 0, 0)).name = "pegado_al_borde";

  alert("Documento de prueba creado (sin guardar). Sigue PRUEBAS_MANUALES.md.");
}());
