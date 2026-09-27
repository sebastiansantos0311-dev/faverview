# FAVERVIEW para Illustrator – Plan del plugin (para agente ejecutor)

> **Instrucciones para el agente**
> 1. Lee antes: `README.md`, `PLAN_SUITE.md`, **`PLAN_AUTOTRAP.md`** (debe estar terminado antes de P7), `DECISIONES.md`
>    y `CHANGELOG.md`. Revisa las rutas actuales del servidor (`app/modules/*/api.py`).
> 2. Ejecuta las etapas **P0 → P10 en orden**. Marca `[x]` al terminar cada casilla. Commit por etapa: `P<n>: …`.
>    Sin `git push` salvo que el usuario lo pida.
> 3. **No dupliques motores**: toda la lógica de imagen, color, vectorización, preflight, separación y trapping vive en el
>    servidor Python de FAVERVIEW. El plugin es un **panel puente**: exporta desde Illustrator → llama a la API local →
>    trae el resultado de vuelta a Illustrator.
> 4. Todo lo que no se pueda verificar sin Illustrator (el agente normalmente no lo tiene) se deja con **pruebas
>    automatizables fuera de Illustrator** + una **lista de pruebas manuales** (`plugin/PRUEBAS_MANUALES.md`) que el usuario
>    ejecuta y reporta. Nunca marques como probado algo que no se ejecutó.
> 5. Si algo es ambiguo o inviable, elige lo más simple que cumpla los criterios, documéntalo en `DECISIONES.md` y sigue.

---

## 0. Decisiones de base (resultado de la investigación, septiembre 2026)

| Tema | Decisión | Motivo |
|---|---|---|
| Tecnología | **CEP** (panel HTML/JS) + **ExtendScript** (host) | Es la **única** forma pública de hacer paneles en Illustrator hoy. UXP para Illustrator: beta pública en primavera 2027 y GA en verano 2027. |
| Fin de CEP | Illustrator deja de aceptar CEP nuevos y lo **desactiva por defecto en dic. 2028**; lo **elimina en dic. 2029** | Anuncio de Adobe (sept. 2026). Hay que migrar a UXP (etapa P10) antes de dic. 2028. |
| Diseño "listo para UXP" | Panel **sin Node.js**, capa host mínima detrás de una interfaz (`HostAdapter`), UI con HTML/CSS estándar (opcional: Spectrum Web Components) | Lo que no use Node ni APIs exclusivas de CEP se porta a UXP casi sin cambios. |
| SDK en C++ (.aip) | **No** en este plan | Meses de trabajo, compilación por plataforma y versión; solo justificable para herramientas en tiempo real (futuro). |
| Versiones de Illustrator | **2024 (v28), 2025 (v29), 2026 (v30)** → manifest `Host Name="ILST" Version="[28.0,99.9]"` | Illustrator 2023–2025 usan CEP 11 (`CSXS.11`); **2026 (v30) usa CEP 12.1 (`CSXS.12`)**. **Confirmar con el usuario** qué versiones usan en el taller. |
| Plataformas | **Windows** (principal). macOS: se deja compatible, pero se prueba solo si el usuario tiene Mac | Taller en Windows. |
| Comunicación | HTTP a `http://127.0.0.1:<puerto>` con **token** + CORS restringido | Reutiliza la API existente sin exponer el servidor a páginas web. |
| Intercambio de archivos | **PDF** para traer vectores (conserva tintas directas como muestras spot y la sobreimpresión); PNG/TIFF para ráster | SVG pierde las tintas directas y la sobreimpresión. |
| Distribución | `.zxp` **firmado** (certificado propio con `ZXPSignCmd`) publicado en **GitHub Releases**; instalación con el instalador oficial de Creative Cloud (UPIA) | Sin `.exe`/`.bat` propios (regla del proyecto); UPIA es de Adobe y está firmado. |

---

## 1. Arquitectura

```
┌──────────────────────── Adobe Illustrator ────────────────────────┐
│  Panel CEP "FAVERVIEW" (HTML/JS, Chromium embebido)               │
│   ├─ ui/ …            pestañas: Vectorizar · Preflight · Separar  │
│   │                   · Comparar · Códigos · Trap · Ajustes       │
│   ├─ core/api.js      fetch a 127.0.0.1 + token + trabajos        │
│   ├─ core/host.js     HostAdapter → CSInterface.evalScript(JSON)  │
│   └─ core/files.js    lectura/escritura de temporales (cep.fs)    │
│          │ evalScript("FV.exportSelection({...})")                │
│  host/ (ExtendScript, ES3)                                        │
│   ├─ json2.js         (JSON no existe en ExtendScript)            │
│   ├─ fv_host.jsx      funciones FV.* (una por operación)          │
│   └─ fv_geom.jsx      conversión de coordenadas                   │
└───────────────┬───────────────────────────────────────────────────┘
                │ HTTP JSON / multipart  (127.0.0.1, token)
┌───────────────▼─────────────── FAVERVIEW (uv run faverview) ──────┐
│  /api/plugin/*  (nuevo: handshake, versión, capacidades)          │
│  /api/<módulo>/* (existentes: vectorizar, preflight, separar…)    │
└───────────────────────────────────────────────────────────────────┘
```

**Principios:**
- ExtendScript hace **solo** lo que exige la API de Illustrator (exportar, colocar, seleccionar, crear muestras, zoom).
  Cada función `FV.*` recibe y devuelve **una cadena JSON** `{"ok": true, "data": …}` o `{"ok": false, "error": "mensaje en español"}`.
  Nunca lanza excepciones sin capturar (siempre `try/catch` y devolver `ok: false`).
- Toda operación larga del servidor usa el sistema de trabajos existente (`/api/jobs/{id}`), con progreso y **Cancelar**.
- Illustrator se bloquea mientras corre ExtendScript: las funciones host deben ser **cortas**. El trabajo pesado siempre en el servidor.

### 1.1 Estructura de carpetas
```
plugin/
├── cep/
│   ├── CSXS/manifest.xml
│   ├── index.html
│   ├── css/panel.css                 (tema claro/oscuro según Illustrator)
│   ├── js/
│   │   ├── lib/CSInterface.js        (oficial de Adobe, licencia MIT/Adobe; copiar de Adobe-CEP/CEP-Resources CEP_12.x)
│   │   ├── core/{api,host,files,jobs,theme,i18n}.js
│   │   └── ui/{app,vectorize,preflight,separate,compare,barcodes,trap,settings}.js
│   ├── host/{json2.js,fv_host.jsx,fv_geom.jsx}
│   ├── icons/ (panel 23×23 normal/oscuro/rollover, PNG)
│   └── .debug                        (solo desarrollo; excluido del .zxp)
├── tests/
│   ├── host_mock/                    (simulación mínima de la API de Illustrator para probar fv_host.jsx en Node/QuickJS)
│   └── panel/                        (pruebas del panel con el servidor real en modo test)
├── tools/
│   ├── build_zxp.py                  (empaquetar + firmar; lo ejecuta el usuario/CI con su certificado)
│   └── dev_install.py                (instalación de desarrollo: copia/enlace + PlayerDebugMode, con confirmación)
├── PRUEBAS_MANUALES.md
└── README.md                         (instalación y uso del plugin)
```

---

## 2. P0 – Servidor listo para el plugin

- [x] **Token del plugin**: al arrancar, FAVERVIEW genera (si no existe) un token aleatorio de 32 bytes
      (`secrets.token_urlsafe`) y lo guarda junto con el puerto en un archivo de ruta fija:
      Windows `%APPDATA%\FAVERVIEW\plugin.json`, macOS `~/Library/Application Support/FAVERVIEW/plugin.json`:
      `{"puerto": 8000, "token": "…", "version": "3.x.y", "pid": 1234}`. Se actualiza en cada arranque (el puerto puede cambiar).
- [x] **Middleware de autenticación**: las peticiones con cabecera `Origin` distinta de `http://127.0.0.1:<puerto>` (el propio
      frontend) **deben** traer `X-FAVERVIEW-Token` válido. Sin token → 401. Comparar con `secrets.compare_digest`.
- [x] **CORS**: permitir solo los orígenes que usa CEP (`null` y `file://`), **y solo** junto con un token válido. Métodos
      GET/POST, cabeceras `Content-Type` y `X-FAVERVIEW-Token`. Responder a los preflight `OPTIONS`. No usar `*`.
- [x] Verificar si el Chromium de CEP exige **Private Network Access** (cabecera `Access-Control-Allow-Private-Network: true`
      en el preflight); si hace falta, añadirla solo para los orígenes permitidos. Documentar lo observado.
- [x] `GET /api/plugin/handshake` → `{version, api_version: 1, modulos, herramientas}` (reutiliza `/api/status`).
      `api_version` sube si cambia algo incompatible; el panel muestra "Actualiza FAVERVIEW" o "Actualiza el plugin" según el caso.
- [x] Rutas **orientadas al plugin** (`app/modules/plugin/api.py`), finas, que reutilizan los módulos:
  | Ruta | Entrada | Salida |
  |---|---|---|
  | `POST /api/plugin/vectorizar` | imagen + parámetros + `tamano_mm` | trabajo → **PDF** vectorial (tintas directas, capa de traps opcional) + estadísticas |
  | `POST /api/plugin/preflight` | PDF + perfil | trabajo → hallazgos con **bbox en puntos PDF** (origen abajo-izquierda) + página |
  | `POST /api/plugin/separar` | PDF + página + dpi + perfil de máquina | trabajo → tintas, cobertura, hallazgos, URLs de placas/mapas |
  | `POST /api/plugin/comparar` | arte del cliente + PDF de la mesa | trabajo → diferencias con **bbox en puntos PDF** + % |
  | `POST /api/plugin/codigo` | tipo, datos, parámetros | **PDF** vectorial del código |
  | `POST /api/plugin/braille` | texto, parámetros | **PDF** vectorial (tinta técnica Braille) |
  | `POST /api/plugin/trap` | PDF + perfil de máquina | trabajo → placas con trap + prueba de movimiento + (si es arte plano) PDF de traps vectoriales |
- [x] **Coordenadas**: todos los bbox devueltos al plugin en **puntos PDF de la página enviada** (`[x0, y0, x1, y1]`, origen
      abajo-izquierda, sin rotación) + `page_size_pt`. La conversión a coordenadas de Illustrator se hace en `fv_geom.jsx` (P2).
- [x] Tests (pytest): sin token → 401; token malo → 401; origen desconocido con token → rechazado; handshake OK; cada ruta
      del plugin con archivos sintéticos devuelve la forma esperada; los bbox en pt coinciden con objetos conocidos (± 0.5 pt).

## 3. P1 – Esqueleto del panel CEP

- [x] `manifest.xml` (ExtensionManifest versión 7.0 o la que exija CEP 11/12):
      `ExtensionBundleId="com.faverview.illustrator"`, extensión `com.faverview.illustrator.panel`, `Host Name="ILST" Version="[28.0,99.9]"`,
      `RequiredRuntime Name="CSXS" Version="11.0"` (funciona en CEP 11 y 12), `ScriptPath=./host/fv_host.jsx`,
      tipo `Panel`, tamaño 360×640 (mín. 300×400), íconos, menú "Ventana → Extensiones → FAVERVIEW".
      **Sin** `--enable-nodejs` ni `--mixed-context` (diseño listo para UXP).
- [x] `CSInterface.js` oficial (CEP 12) copiado con su licencia.
- [x] `host.js` → `HostAdapter` con **una única** forma de llamar: `await host.call("exportSelection", {...})` →
      `evalScript('FV.dispatch(' + JSON.stringify(nombre) + ',' + JSON.stringify(json) + ')')` → parsea el resultado.
      Escapar correctamente (`JSON.stringify` doble). Timeout configurable.
- [x] `fv_host.jsx`: `#include "json2.js"`; `FV.dispatch(nombre, argsJson)` con una lista blanca de funciones, `try/catch` y
      respuesta `{ok, data|error}`; `FV.ping()` → versión de Illustrator (`app.version`), documento activo (sí/no), unidades.
- [x] **Conexión**: al abrir el panel, leer `plugin.json` con `window.cep.fs.readFile` (API nativa de CEP, **no** Node) →
      handshake → indicador de estado:
      🟢 "Conectado a FAVERVIEW 3.x" · 🟡 "Versión incompatible: actualiza X" · 🔴 "FAVERVIEW no está abierto" (con
      instrucciones: "Abre FAVERVIEW desde su acceso directo y pulsa Reintentar"). Reintento automático cada 5 s mientras está en rojo.
- [x] **Tema**: leer el color de la interfaz de Illustrator (`CSInterface.getHostEnvironment().appSkinInfo`) y escuchar
      `com.adobe.csxs.events.ThemeColorChanged` → tema claro/oscuro.
- [x] Todo el texto en español mediante `i18n.js` (preparado para agregar idiomas).
- [x] Desarrollo: `.debug` con el puerto de DevTools (p. ej. 8088); `plugin/README.md` explica cómo activar `PlayerDebugMode`
      (clave `HKCU\Software\Adobe\CSXS.11` **y** `CSXS.12`, valor cadena `1`), que es **solo para desarrollo** y lo hace el usuario.

## 4. P2 – Transporte de archivos y geometría

**Exportar desde Illustrator (ExtendScript):**
- [x] `FV.exportArtboardPDF({artboard, preset})`: guarda una **copia** del documento como PDF en `Folder.temp/FAVERVIEW/<uuid>.pdf`
      con `PDFSaveOptions` (preset configurable; por defecto "[PDF/X-4:2008]" si existe, si no "[Calidad de prensa]"), solo la mesa
      de trabajo indicada (`artboardRange`), **sin** alterar el documento del usuario (usar `saveAs` sobre un **duplicado**
      o `exportFile`; comprobar que el documento activo sigue apuntando a su archivo original y que no queda marcado como
      guardado con otro nombre). Devolver la ruta, el tamaño de la mesa en pt, su `artboardRect` y el origen de la regla.
- [x] `FV.exportSelectionPNG({ppi})`: para una imagen colocada/incrustada seleccionada: si está **vinculada**, devolver la
      ruta del archivo original (mejor calidad) + su transformación (matriz, bounds); si está incrustada, exportar la selección
      con `exportFile(ExportType.PNG24, ...)` a `ppi` (por defecto la resolución efectiva, máx. 600) con fondo transparente.
- [x] `FV.exportSelectionPDF()`: copia la selección a un documento temporal nuevo, del tamaño de la selección, y lo guarda como PDF.

**Mover archivos entre el panel y el servidor:**
- [x] `files.js`: leer el temporal con `cep.fs.readFile(ruta, cep.encoding.Base64)` → `Blob` → `FormData` → `POST` multipart.
      Descargar el resultado con `fetch` → `ArrayBuffer` → Base64 → `cep.fs.writeFile(ruta, datos, cep.encoding.Base64)` en temporales.
- [x] Límite de tamaño (el del servidor, `max_upload_mb`) con un mensaje claro.
- [x] Limpieza: borrar `Folder.temp/FAVERVIEW/*` de más de 24 h al abrir el panel.

**Traer a Illustrator:**
- [x] `FV.placePDF({ruta, x, y, ancho, alto, capa, nombre, incrustar})`: `groupItems.createFromFile(File(ruta))` → queda un grupo
      con los vectores y **las tintas directas como muestras spot** (verificar; si alguna llega como proceso, recrearla con
      `doc.spots.add()` y reasignarla). Posicionarlo en coordenadas de la mesa, en la capa indicada (crearla si no existe), con nombre.
- [x] `FV.ensureSpot({nombre, cmyk|lab, tipo})`: busca la muestra por nombre **normalizado** (mismas reglas que
      `core/inks.normalize_name`) y la crea si no existe (`SpotColor`, modelo Lab o CMYK), para no duplicar tintas.

**Geometría (`fv_geom.jsx`) — la parte más delicada:**
- [x] Convertir un bbox en **puntos PDF de la mesa exportada** (origen abajo-izquierda) a **coordenadas de documento de
      Illustrator** usando el `artboardRect` de la mesa `[izq, arriba, der, abajo]` (el eje Y de Illustrator crece hacia arriba
      en el sistema de scripting), el origen de regla (`doc.rulerOrigin` / `artboard.rulerOrigin`) y el sistema de
      coordenadas activo (`app.coordinateSystem`). Fijar explícitamente `CoordinateSystem.DOCUMENTCOORDINATESYSTEM` dentro
      de cada función y restaurarlo al final.
- [x] Casos a cubrir con tests (mock): mesa en el origen, mesa desplazada, varias mesas, mesa en posición negativa, documento
      con origen de regla cambiado, unidades en mm/pt/px.
- [x] `FV.zoomTo({bbox, margen})`: `doc.views[0].centerPoint` al centro y `zoom` para que el bbox + margen quepa en la ventana.
- [x] `FV.selectInBBox({bbox, capas})`: selecciona los objetos de página (no bloqueados ni ocultos) cuyo `visibleBounds`
      intersecta el bbox. Límite de objetos recorridos (p. ej. 20 000) con aviso para documentos enormes.
- [x] `FV.markers({lista})`: crea en una capa **"FAVERVIEW – Revisión"** (bloqueada, que no se imprime:
      `layer.printable = false`) rectángulos sin relleno y con trazo de color por categoría, más una etiqueta con el número.
      `FV.clearMarkers()` borra la capa.

## 5. P3 – Vectorizar dentro de Illustrator

- [x] UI: con una imagen seleccionada → preajuste (Logo, Línea, Ilustración, Escaneo, Foto posterizada), número de colores,
      detalle mínimo, geometría limpia, **"Usar tintas de la biblioteca"** (lista de bibliotecas del servidor),
      **"Añadir trap"** (perfil de máquina; requiere `PLAN_AUTOTRAP.md` T4) y el tamaño final (por defecto el tamaño de la
      imagen en el documento).
- [x] **Vista previa** en el panel (PNG reducido del servidor) antes de colocar.
- [x] "Colocar": el PDF vectorial se coloca **exactamente encima** de la imagen original (misma posición y tamaño, respetando
      la rotación de la imagen colocada: aplicar su matriz), en una capa nueva "FAVERVIEW – Vector"; la imagen original se
      oculta o bloquea (opción). Las tintas se crean o reutilizan como muestras spot. El grupo de traps queda como subgrupo aparte.
- [x] Deshacer: todo el colocado en **una sola operación** si es posible (un único `evalScript`), para que un solo Ctrl+Z lo revierta.
      Si Illustrator registra varios pasos, documentarlo.
- [x] Estadísticas en el panel: nodos, trazados, colores y tiempo.

## 6. P4 – Preflight dentro de Illustrator

- [x] UI: perfil (lista del servidor) + "Revisar mesa actual" / "Revisar todas las mesas".
- [x] Flujo: `exportArtboardPDF` → `POST /api/plugin/preflight` → lista agrupada por severidad (errores / advertencias / info).
- [x] Clic en un hallazgo → `zoomTo` + `selectInBBox` (+ marcador temporal).
- [x] Botón "Marcar todos en el documento" → `markers` en la capa de revisión; "Quitar marcas".
- [x] **Correcciones nativas en Illustrator** (mejor que corregir el PDF, porque el documento sigue editable), cada una con
      vista previa del número de objetos afectados y confirmación:
  - sobreimpresión en tintas técnicas (troquel, cotas, braille): `fillOverprint`/`strokeOverprint = true` en los objetos
    que usan esas muestras;
  - texto negro pequeño a 100% K con sobreimpresión (cambiar negro enriquecido → K puro en textos < X pt);
  - **unir muestras spot duplicadas** (reasignar los objetos de la muestra duplicada a la canónica y eliminar la duplicada);
  - eliminar muestras no usadas;
  - convertir un color RGB a CMYK (mediante `app.executeMenuCommand` de conversión de modo de color **solo** si es fiable;
    si no, **solo reportar**).
  Las correcciones que no se puedan hacer con seguridad desde ExtendScript **solo se reportan** (documentar en `DECISIONES.md`).
- [x] Re-preflight automático después de corregir.

## 7. P5 – Separaciones y tintas dentro de Illustrator

- [x] "Analizar separaciones" de la mesa: tintas (comparadas con las **muestras del documento**: marcar las muestras spot sin
      uso y las tintas del PDF sin muestra), cobertura por tinta, TAC máximo con perfil y hallazgos (clic → zoom).
- [x] Vista de **placas** en el panel (miniaturas por tinta, del servidor), con "solo esta tinta" y negativo.
- [x] **Densitómetro** simplificado: clic en la vista previa del panel → % por tinta en ese punto.
- [x] "Exportar placas" (TIFF/PDF de placas) → diálogo de guardado nativo (`cep.fs.showSaveDialogEx`) → escribir el zip.
- [x] Enlace "Abrir en FAVERVIEW" (abre la app web con este trabajo cargado: `cep.util.openURLInDefaultBrowser`).

## 8. P6 – Comparar con el arte del cliente

- [x] "Elegir arte del cliente" (`cep.fs.showOpenDialogEx`: JPG/PNG/PDF/…) o **pegar** una imagen del portapapeles.
- [x] Flujo: exportar la mesa → `POST /api/plugin/comparar` → % de similitud, semáforo y lista de diferencias.
- [x] Marcadores de las diferencias sobre el diseño (capa de revisión); clic → zoom al objeto.
- [x] Botón "Ver comparación completa en FAVERVIEW" (abre la app con el resultado).

## 9. P7 – Trap (reventado) dentro de Illustrator

**Requiere `PLAN_AUTOTRAP.md` terminado.**
- [x] UI: perfil de máquina + tolerancia (mm) → "Analizar registro": exporta la mesa → prueba de movimiento → mapa de filetes
      en el panel y marcadores en el documento donde hay filetes.
- [x] **"Crear traps vectoriales"** (solo arte vectorial plano, sin degradados ni imágenes en la zona):
      el servidor calcula, a partir del PDF, las fronteras entre tintas (render a alta resolución → mapa planar → cadenas,
      reutilizando el vectorizador) y devuelve un **PDF con los trazos de trap** (overprint, clip A ∪ B) → se coloca en una
      capa **"FAVERVIEW – Traps"** encima del arte, alineado al pt.
      Límite honesto: en arte con degradados, transparencias o imágenes → "usa la exportación de placas con trap (raster)".
- [x] Verificación posterior: volver a exportar → prueba de movimiento → "✔ 0 filetes con ±X mm".
- [x] Mencionar en la ayuda la alternativa nativa de Illustrator (Buscatrazos → Reventar/Trap) para casos simples.

## 10. P8 – Códigos de barras y braille

- [x] Formulario de código (tipo, datos con validación en vivo, magnificación, BWR, tinta) → vista previa → "Insertar" en
      el centro de la vista o en la posición de la selección → PDF vectorial colocado como grupo, con su muestra spot.
- [x] "Verificar códigos del documento": exportar la mesa → verificar → lista con el grado estimado → clic → zoom.
- [x] Braille: texto → vista previa → "Insertar" en la tinta técnica "Braille" (sobreimpresión) en una capa propia.

## 11. P9 – Empaquetado, firma, instalación y actualizaciones

- [x] `plugin/tools/build_zxp.py`:
  1. copia `plugin/cep/` a `build/zxp/` **excluyendo** `.debug`, tests y mapas de código;
  2. escribe la versión en el manifest (igual a la de FAVERVIEW o con su propia versión `plugin_version`);
  3. firma con `ZXPSignCmd` (herramienta oficial de Adobe, se descarga del repositorio `Adobe-CEP/CEP-Resources`;
     **no** incluirla en el repositorio si su licencia no lo permite): `ZXPSignCmd -sign build/zxp FAVERVIEW.zxp cert.p12 <clave> -tsa <url_TSA>`;
  4. verifica con `ZXPSignCmd -verify`.
  El **certificado** (`.p12`) y su clave **nunca** se suben a git. Crear el certificado propio una vez:
  `ZXPSignCmd -selfSignedCert <país> <provincia> <organización> <nombre> <clave> cert.p12` (documentar el paso para el usuario).
- [ ] Publicación: `FAVERVIEW-Illustrator-<versión>.zxp` como archivo adjunto de un **GitHub Release** (lo sube el usuario, o la CI
      si el usuario configura el certificado como secreto del repositorio; documentar ambas opciones).
- [ ] Instalación para el usuario (en `plugin/README.md` y en el manual), sin `.exe` propios:
  1. Descargar el `.zxp` del Release.
  2. PowerShell: ejecutar el instalador oficial de Creative Cloud:
     `& "C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe" /install "<ruta>\FAVERVIEW-Illustrator-<versión>.zxp"`
     (**verificar la ruta real** en un equipo con Creative Cloud y documentar cómo encontrarla si difiere).
  3. Reiniciar Illustrator → **Ventana → Extensiones → FAVERVIEW**.
  - Alternativas documentadas: instalar el `.zxp` con un instalador de ZXP gratuito de terceros (solo mencionarlo) o, en
    desarrollo, copiar la carpeta a `%APPDATA%\Adobe\CEP\extensions\` con `PlayerDebugMode`.
  - Desinstalar: `UnifiedPluginInstallerAgent.exe /remove com.faverview.illustrator` (verificar la sintaxis).
- [ ] **Firma propia y avisos**: documentar que un certificado propio es válido para CEP, y qué hacer si Creative Cloud
      muestra un aviso de editor no verificado (verificar el comportamiento real y documentarlo con una captura).
- [x] **Actualizaciones**: el panel compara su versión con la del último Release (vía `/api/update` del servidor, que ya
      consulta GitHub) y muestra "Hay una versión nueva del plugin" con el enlace de descarga.
- [x] CI: job que valida el `manifest.xml` (XML bien formado, versiones) y ejecuta las pruebas del host con el mock y las del
      panel contra el servidor en modo test. La firma **no** se hace en CI salvo que el usuario configure el secreto.

## 12. P10 – Preparación para UXP (hacer al terminar; migrar cuando exista la beta)

- [x] `plugin/MIGRACION_UXP.md`: mapa de cada pieza CEP → UXP:
  | CEP | UXP (esperado) |
  |---|---|
  | `CSInterface.evalScript` + ExtendScript | API DOM de Illustrator para UXP (JavaScript moderno) |
  | `cep.fs` | `require('uxp').storage.localFileSystem` (con permisos en el manifest v5) |
  | `fetch` a 127.0.0.1 | `fetch` con permiso `network.domains` en el manifest |
  | `manifest.xml` | `manifest.json` (v5) |
  | `.zxp` + UPIA | `.ccx` + Creative Cloud / UPIA |
- [x] Confirmar que ningún archivo del panel usa Node, `window.__adobe_cep__` fuera de `host.js`/`files.js` ni APIs de CEP fuera
      del `HostAdapter` (test estático con grep en CI).
- [ ] Cuando Adobe publique la **beta de UXP para Illustrator (primavera 2027)**: crear `PLAN_PLUGIN_UXP.md` a partir de la
      documentación oficial y migrar antes de **diciembre 2028**.

---

## 13. Pruebas

### Automatizables (el agente las ejecuta)
- [x] **Servidor** (pytest): token, CORS, handshake y rutas del plugin (P0).
- [x] **ExtendScript con mock** (`plugin/tests/host_mock/`): implementar un mock mínimo de `app`, `Document`, `Artboard`,
      `GroupItem`, `Spot`, `SpotColor`, `View`, `File`, `Folder` suficiente para ejecutar `fv_host.jsx` en Node (solo para
      tests, **no** en el panel) y probar: `dispatch` con lista blanca, manejo de errores, conversión de geometría (todos los
      casos de P2), `ensureSpot` sin duplicados, `markers` y `selectInBBox`.
- [x] **Panel** (Playwright o pruebas JS en un navegador normal con `CSInterface`/`cep.fs` simulados): flujo de conexión
      (verde/amarillo/rojo), subida y descarga de archivos, trabajos con progreso y cancelación, errores del servidor
      mostrados en español.
- [x] **Estático**: sin Node (`require(`), sin `eval` en el panel, textos sin traducir (todas las cadenas visibles pasan por `i18n`).

### Manuales (`plugin/PRUEBAS_MANUALES.md`, las ejecuta el usuario en Illustrator)
Formato por prueba: **pasos → resultado esperado → ✔/✘ → observaciones/captura**. Mínimo:
1. Instalar el `.zxp` con UPIA en Illustrator 2024, 2025 y 2026 (los que tenga) → aparece en Ventana → Extensiones.
2. Panel con FAVERVIEW cerrado → rojo con instrucciones; abrir FAVERVIEW → pasa a verde solo.
3. Vectorizar un logo JPG colocado (vinculado) y otro incrustado y rotado 30° → el vector cae exactamente encima, con las muestras spot correctas y sin duplicados.
4. Vectorizar con "Añadir trap" → existe la capa de traps con sobreimpresión (ver con Ventana → Previsualizar separaciones).
5. Preflight de un documento con errores conocidos (archivo de prueba incluido en `plugin/tests/archivos/`) → los hallazgos esperados; clic → zoom correcto en mesas 1 y 3 de un documento con 3 mesas desplazadas.
6. Correcciones nativas: unir spots duplicados y sobreimpresión en troquel → comprobar en Previsualizar separaciones.
7. Separaciones: tintas y TAC coinciden con Acrobat → Previsualización de salida (± 1%).
8. Comparar con un arte del cliente con 3 diferencias conocidas → 3 marcadores en el lugar correcto.
9. Código EAN-13 insertado → escaneable con el celular; la tinta es la elegida.
10. Trap vectorial en un logo plano de 3 tintas → "0 filetes con ±0.2 mm"; en un arte con degradado → mensaje de límite.
11. Deshacer (Ctrl+Z) después de colocar un vector → vuelve al estado anterior.
12. Documento grande (> 5 000 objetos) → el panel no congela Illustrator más de 2 s en ninguna operación del host.
13. Desinstalar con UPIA → el panel desaparece.

## 14. Documentación
- [x] `plugin/README.md`: requisitos (Illustrator 2024+, FAVERVIEW abierto), instalación, actualización, desinstalación y
      resolución de problemas (panel en blanco → versión de CSXS; "no conecta" → FAVERVIEW cerrado o firewall; aviso de
      firma).
- [x] Manual de usuario: capítulo "FAVERVIEW en Illustrator" con capturas de cada pestaña.
- [x] `CHANGELOG.md`, `DECISIONES.md` y `README.md` principal (enlace al plugin).

## 15. Criterios de aceptación finales
- [ ] Todas las pruebas automatizables en verde; tests del servidor y bancos existentes sin regresiones.
- [ ] `.zxp` firmado y verificado con `ZXPSignCmd -verify`.
- [ ] `PRUEBAS_MANUALES.md` ejecutado por el usuario con ≥ 12/13 ✔ en al menos una versión de Illustrator (las ✘
      documentadas con su plan de arreglo).
- [ ] El servidor rechaza peticiones sin token desde cualquier origen externo.
- [ ] Ninguna operación modifica el documento del usuario sin una acción explícita (colocar, corregir, marcar) y todas
      se pueden deshacer.
- [ ] `MIGRACION_UXP.md` completo; sin dependencias de Node en el panel.

## 16. Orden y estimación orientativa
| Etapa | Depende de | Esfuerzo aprox. del agente |
|---|---|---|
| P0 Servidor (token, CORS, rutas) | — | 1–2 días |
| P1 Esqueleto del panel | P0 | 1–2 días |
| P2 Transporte y geometría | P1 | 2–3 días (la geometría es lo más delicado) |
| P3 Vectorizar | P2 | 1–2 días |
| P4 Preflight + correcciones nativas | P2 | 2–3 días |
| P5 Separaciones | P2 | 1–2 días |
| P6 Comparar | P2 | 1 día |
| P7 Trap | P2 + PLAN_AUTOTRAP | 2–3 días |
| P8 Códigos y braille | P2 | 1 día |
| P9 Empaquetado e instalación | P1 | 1–2 días |
| P10 Preparación UXP | todo | 0.5 día (+ la migración en 2027) |

## 17. Tareas del usuario (el agente no puede hacerlas)
- [ ] Confirmar las **versiones de Illustrator** del taller (2024, 2025, 2026) y si hay equipos Mac.
- [ ] Descargar `ZXPSignCmd` y **crear el certificado propio** siguiendo `plugin/README.md` (guardar el `.p12` y la clave en
      un lugar seguro, **fuera** del repositorio).
- [ ] Ejecutar `PRUEBAS_MANUALES.md` en Illustrator y reportar los resultados (capturas de lo que falle).
- [ ] Subir el `.zxp` firmado al GitHub Release (o configurar el secreto para la CI).

## Fuentes
- [Adobe: CEP → UXP en las aplicaciones principales (sept. 2026)](https://blog.developer.adobe.com/en/publish/2026/09/investing-in-the-future-of-creative-cloud-extensibility-uxp-comes-to-our-flagship-applications)
- [Mapsoft: estado de UXP en Illustrator](https://mapsoft.com/posts/illustrator-uxp-status.html) · [Mapsoft: extensiones CEP en Illustrator (2026)](https://mapsoft.com/posts/illustrator-cep-extensions.html)
- [CEP 12 HTML Extension Cookbook (Adobe-CEP)](https://github.com/Adobe-CEP/CEP-Resources/blob/master/CEP_12.x/Documentation/CEP%2012%20HTML%20Extension%20Cookbook.md) · [Depuración en CEP](https://github.com/Adobe-CEP/Getting-Started-guides/blob/master/Client-side%20Debugging/readme.md)
- [Illustrator 2026 usa CEP 12.1 / CSXS.12 (notas de instalación)](https://github.com/hacker-cb/adobe-ai-cutter-tools/issues/1) · [Panel CEP que no aparece en Illustrator 2025](https://community.adobe.com/questions-652/cep-panel-not-showing-up-in-illustrator-2025-815871)
- [Instalar plugins por línea de comandos (UPIA)](https://blog.developer.adobe.com/en/publish/2022/03/how-to-install-uxp-plugins-using-command-line-tools)
- [Guía de scripting de Illustrator: GroupItems](https://ai-scripting.docsforadobe.dev/jsobjref/GroupItems/) · [Tipos de la API de Illustrator 29](https://www.indesignjs.de/extendscriptAPI/illustrator-latest/)
