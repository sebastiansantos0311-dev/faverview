# FAVERVIEW Suite (v3) – Plan de implementación (para agente ejecutor)

> **Instrucciones para el agente**
> 1. Lee antes de empezar: `README.md`, `PLAN.md`, `PLAN_V2.md`, `CHANGELOG.md` e **`INVESTIGACION_PREPRENSA.md`**
>    (contexto del sector, justificación y fuentes).
> 2. Ejecuta las etapas **en orden (S0 → S8)**. Dentro de cada etapa, las tareas en el orden listado.
>    Marca `[x]` al terminar cada casilla.
> 3. Tras **cada tarea**: `uv run pytest -q`. Tras **cada etapa**: pytest + banco de pruebas + commit
>    `git commit -m "S<n>: <resumen>"`. No hagas `git push` sin que el usuario lo pida.
> 4. **Nunca rompas el módulo Comparar** (v2). Su banco de pruebas (`bench.run --sinteticos --ci`) debe seguir pasando
>    en cada etapa.
> 5. Si una especificación es ambigua o técnicamente inviable, **no inventes**: elige la opción más simple que cumpla
>    los criterios de aceptación, documenta la decisión en `DECISIONES.md` (fecha, contexto, decisión, alternativa
>    descartada) y continúa.
> 6. Al terminar cada etapa, actualiza `CHANGELOG.md` y el manual de usuario.

---

## 0. Reglas del proyecto (no negociables)

| Regla | Detalle |
|---|---|
| Local | Todo corre en el equipo del usuario (`127.0.0.1`). Sin servicios en la nube ni telemetría. |
| Gratis y libre | Solo dependencias gratuitas con licencia compatible con **AGPL-3.0**. Nada de SDK comerciales. |
| Sin IA | Algoritmos clásicos de procesamiento de imagen, geometría y optimización. (El aprendizaje local del OCR de v2 se mantiene.) |
| Idioma | Interfaz, mensajes, reportes y documentación en **español**. Código e identificadores en inglés o español, pero consistentes con el código existente. |
| Distribución | GitHub + winget + uv. **Sin `.exe`/`.bat`/`.ps1` propios.** |
| Privacidad | Archivos de clientes y resultados solo en `data/` y `datos_locales/` (en `.gitignore`). Los casos de prueba públicos se **generan sintéticamente**. |
| Pantone | **No** incluir bibliotecas Pantone ni valores Lab de Pantone (tienen licencia). El usuario importa las suyas. |
| Honestidad | Nunca afirmar en la UI "certificado", "conforme a ISO" ni "mejor que Illustrator" sin medición. Usar "estimación", "orientativo" y "según el banco de pruebas". |
| Seguridad | Ghostscript siempre con `-dSAFER`, `subprocess` sin `shell=True`, rutas validadas y *timeouts* en todos los procesos externos. |

---

## 1. Punto de partida (v2.0.0)

Ya existe:
- **App FastAPI** (`app/main.py`, unas 570 líneas, con todas las rutas en un archivo), frontend `web/` (`index.html`,
  `app.js` de unas 900 líneas, `styles.css`) y un solo módulo: **Comparar**.
- Trabajos en segundo plano con progreso (`app/jobs.py`), historial, reportes PDF (`app/report.py`), gestión de color
  ICC (`app/color_mgmt.py`), aprendizaje del OCR (`app/learning/`), plantillas, versiones y lotes.
- Banco de pruebas (`bench/`), casos sintéticos (`tests/sinteticos/`), CI en GitHub Actions (`windows-latest`) y
  aviso de actualización.
- Lanzador `uv run faverview` con acceso directo y logo.

**Objetivo v3:** convertir la app en una **suite de preprensa con pestañas**: Comparar · Separar colores ·
Vectorizar · Preflight · Códigos de barras · Herramientas · Automatizar.

---

## 2. Arquitectura objetivo

### 2.1 Estructura de carpetas
```
app/
├── main.py                 # SOLO crea la app, monta routers y estáticos (≤ 80 líneas)
├── launcher.py
├── core/                   # núcleo compartido por todos los módulos
│   ├── __init__.py
│   ├── files.py            # subida, validación, almacenamiento por trabajo, limpieza
│   ├── jobs.py             # (mover app/jobs.py aquí; dejar un re-export en app/jobs.py)
│   ├── units.py            # mm/pt/px/in, dpi, conversiones
│   ├── pdfinfo.py          # cajas (Media/Trim/Bleed), páginas, espacios de color, OutputIntent
│   ├── ghostscript.py      # localizar gswin64c, ejecutar con SAFER y timeout, errores en español
│   ├── inks.py             # modelo Ink + bibliotecas de tintas del usuario (CxF/ASE/CSV/JSON)
│   ├── colorscience.py     # Lab, ΔE2000, ΔE76, conversiones, densidad, mezcla de tintas
│   ├── render.py           # render de PDF/imagen a RGB/CMYK/separaciones (PyMuPDF + Ghostscript)
│   ├── reports.py          # utilidades comunes de reporte PDF (portada, tablas, miniaturas)
│   └── tools.py            # detección de herramientas externas (gs, tesseract) para /api/status
├── modules/
│   ├── compare/            # el módulo v2 movido aquí SIN cambiar comportamiento
│   ├── separate/           # S2 (PDF) + S3 (raster)
│   ├── vectorize/          # S4 + S5
│   ├── preflight/          # S6
│   ├── barcodes/           # S6
│   ├── tools/              # S7: trapping, step & repeat, distorsión, braille, gama extendida, soft proof
│   └── automate/           # S8
├── learning/               # (existente)
└── ...
web/
├── index.html              # shell con barra de pestañas y <main id="vista">
├── core/
│   ├── router.js           # rutas por hash: #/comparar, #/separar, #/vectorizar…
│   ├── api.js              # fetch + subida de archivos + sondeo de trabajos (/api/jobs/{id})
│   ├── viewer.js           # visor reutilizable: zoom, paneo, capas, regla en mm, cuentagotas
│   ├── dropzone.js         # arrastrar/soltar/pegar (Ctrl+V)
│   └── ui.js               # toasts, diálogos, barra de progreso, formato de números
├── modules/
│   ├── compare.js          # el app.js actual, adaptado como módulo
│   ├── separate.js
│   ├── vectorize.js
│   ├── preflight.js
│   ├── barcodes.js
│   ├── tools.js
│   └── automate.js
└── styles.css
```

### 2.2 Convenciones de API
- Cada módulo expone un `APIRouter` con prefijo `/api/<modulo>/…`. Las rutas v2 actuales se mantienen **con la misma URL**
  (alias) para no romper nada.
- Operaciones de más de 1 s → **trabajo en segundo plano**: `POST` devuelve `{job_id}` y la UI consulta
  `/api/jobs/{job_id}` (progreso por etapas).
- Resultados en `data/results/<modulo>/<job_id>/` con un `result.json` + archivos. Limpieza a los 30 días (se reutiliza `history.cleanup`).
- Errores: excepción `UserError(mensaje_es)` → HTTP 400 con `{"error": "..."}`. Nunca mostrar un traceback al usuario.
- `GET /api/status` → versión, herramientas detectadas (`gs`, `tesseract`), con versión y ruta, y los módulos habilitados.

### 2.3 Modelos de datos compartidos (`app/core/inks.py`)
```python
class Ink(BaseModel):
    name: str                     # "PANTONE 485 C", "Cyan", "Blanco", "Barniz"
    kind: Literal["process", "spot", "white", "varnish", "technical"]  # technical = troquel, braille, cotas
    lab: tuple[float, float, float] | None = None   # color sólido al 100% sobre el sustrato de referencia
    alt_cmyk: tuple[float, float, float, float] | None = None  # alternativa del PDF (0–1)
    opacity: float = 0.0          # 0 = transparente (proceso), 1 = opaca (blanco, metálicos)
    print_order: int | None = None
    source: str = ""              # "pdf", "biblioteca:<nombre>", "usuario"

class InkLibrary(BaseModel):
    name: str
    inks: list[Ink]
```
- Normalización de nombres (para unir duplicados): mayúsculas, sin espacios dobles, `PANTONE`/`PMS`/`P`
  unificados, sufijos `C/U/M/CP/UP` separados por un espacio: `"Pantone 485C"` ≡ `"PANTONE 485 C"`.
- Bibliotecas en `datos_locales/tintas/*.json`. Importadores: **CxF3** (XML, ISO 17972), **ASE** (Adobe Swatch
  Exchange, binario) y **CSV** (`nombre,L,a,b[,tipo][,opacidad]`).
- Tintas de proceso por defecto: C, M, Y, K con Lab de **ISO 12647-2 PC1 (FOGRA51)**. Documentar en
  `app/core/inks.py` que son valores de referencia públicos de la caracterización.

### 2.4 Visor compartido (`web/core/viewer.js`)
Obligatorio para todos los módulos:
- zoom (rueda, 10%–3200%), paneo, "ajustar", 100%, sincronización opcional entre dos visores,
- **capas**: lista de capas con visibilidad y opacidad (para placas, vectores y marcas),
- **regla y cursor en mm** (usa el dpi del render),
- **cuentagotas/densitómetro**: al pasar el cursor llama a un callback del módulo (p. ej. % de cada tinta),
- carga por mosaicos (**tiles**) cuando la imagen supera 8000 px de lado, para no congelar el navegador.

---

## 3. Dependencias nuevas

| Paquete / herramienta | Uso | Licencia | Instalación |
|---|---|---|---|
| **Ghostscript** ≥ 10 | separaciones `tiffsep`, overprint, `bbox`, EPS, códigos de barras (BWIPP) | AGPL-3.0 | **No está en winget.** Instalador oficial firmado de Artifex desde GitHub (`ArtifexSoftware/ghostpdl-downloads`, p. ej. `gs10080w64.exe`), instalación silenciosa `/S` tras verificar la firma Authenticode |
| `pikepdf` | leer/editar PDF a bajo nivel (espacios de color, recursos) | MPL-2.0 | pip |
| `vtracer` | vectorización a color (referencia y posible base) | MIT | pip |
| `potracer` (Python puro) o `pypotrace` | vectorización B/N (referencia) | GPL-2.0+ | pip |
| `ezdxf` | exportar DXF (corte, troquel) | MIT | pip |
| `zxing-cpp` | leer/verificar códigos de barras | Apache-2.0 | pip |
| `treepoem` | generar códigos de barras con BWIPP (usa Ghostscript) | MIT | pip |
| `segno` | QR vectorial | BSD | pip |
| `louis` (liblouis) | braille | LGPL-2.1 | pip (`louis`); si no hay wheel para Windows, usar una tabla propia (ver S7.4) |
| `watchdog` | carpetas vigiladas (S8) | Apache-2.0 | pip |
| `lxml` | leer CxF (XML) | BSD | pip |

Tareas de instalación:
- [x] Añadir los paquetes a `pyproject.toml` y regenerar `uv.lock`.
- [x] `README.md` paso 2: agregar el comando de instalación de Ghostscript (descarga del release oficial más reciente vía la API de GitHub → verificar que la firma Authenticode sea válida y de Artifex → `/S`).
- [x] `launcher.py`: avisar si falta Ghostscript (igual que con Tesseract), con el enlace a la sección del README.
      Los módulos que lo necesitan muestran un aviso en la UI y se desactivan; el resto funciona.
- [x] CI (`.github/workflows/tests.yml`): instalar Ghostscript (`choco install ghostscript -y` y añadir `bin` al PATH).
- [x] `core/ghostscript.py`: buscar `gswin64c.exe` en el PATH, en `C:\Program Files\gs\gs*\bin\` (la versión más alta) y en
      `config.json → "ghostscript_cmd"`.

---

## 4. S0 – Preparación y refactor (sin funciones nuevas)

**Objetivo:** dejar la base lista para varios módulos **sin cambiar el comportamiento** de Comparar.

- [x] Crear `DECISIONES.md` y la sección "v3 (en desarrollo)" en `CHANGELOG.md`.
- [x] Crear `app/core/` y mover las utilidades compartidas (`jobs`, carga/validación de archivos, `color_mgmt`,
      utilidades de reporte). Dejar **módulos puente** (`app/jobs.py` que re-exporta `app.core.jobs`) para que los imports
      antiguos y los tests sigan funcionando.
- [x] Mover la lógica de Comparar a `app/modules/compare/` y sus rutas a un `APIRouter`. `app/main.py` queda ≤ 80 líneas.
- [x] Frontend: crear el shell con pestañas + `router.js`; el `app.js` actual pasa a `web/modules/compare.js`.
      Pestañas no implementadas → pantalla "Próximamente".
- [x] Extraer `viewer.js` y `dropzone.js` del código actual de Comparar y usarlos en Comparar (primer consumidor).
- [x] `GET /api/status`.
- [x] Añadir las dependencias de la sección 3 y detectar Ghostscript.

**Criterios de aceptación S0**
- [x] `uv run pytest` pasa **sin modificar** los tests existentes (salvo los imports, si es inevitable; documentar).
- [x] `bench.run --sinteticos --ci` pasa con las mismas métricas (± 0.5).
- [x] Todas las URLs v2 responden igual (test que recorre la lista de rutas de v2).
- [x] Prueba manual: comparar `samples/` en el navegador se ve y funciona igual que antes.

---

## 5. S1 – Núcleo compartido

- [x] `core/units.py`: `mm_to_pt`, `pt_to_mm`, `px_to_mm(px, dpi)`, etc. Tests con valores exactos (1 in = 25.4 mm = 72 pt).
- [x] `core/colorscience.py`:
  - sRGB ↔ XYZ ↔ Lab (D50 para impresión, con adaptación cromática Bradford desde D65),
  - ΔE76 y **ΔE2000** vectorizados (NumPy). Test con los **34 pares de referencia de Sharma et al. (2005)**:
    error < 1e-4,
  - densidad estado T aproximada desde Lab/RGB (orientativa),
  - **modelo de mezcla de tintas** (usado en S3/S7), ver 7.3.
- [x] `core/inks.py`: modelos, normalización de nombres, bibliotecas, importadores CxF/ASE/CSV y exportador JSON/CSV.
      Tests con archivos de ejemplo **creados por el agente** (no Pantone reales: usar nombres como "Demo Rojo 1").
- [x] `core/ghostscript.py`: `run_gs(args, timeout=120)` → siempre antepone `-dSAFER -dBATCH -dNOPAUSE -dQUIET`,
      captura stderr y traduce los errores comunes a español.
- [x] `core/pdfinfo.py`: páginas, cajas (MediaBox/CropBox/TrimBox/BleedBox) en mm, OutputIntent, versión PDF/X
      (clave `GTS_PDFXVersion`), presencia de transparencias y capas (OCG).
- [x] UI **"Tintas"** (dentro de Herramientas o como panel global): ver, importar, editar y exportar bibliotecas.
      Muestra de color sRGB aproximada con el aviso "vista aproximada".

**Criterios S1:** cobertura de tests ≥ 85% en `app/core/`; ΔE2000 validado con la tabla de Sharma.

---

## 6. S2 – Separador de colores: PDF → placas

### 6.1 Inventario de tintas (`modules/separate/pdf_inks.py`)
- [ ] Recorrer con **pikepdf** todas las páginas y recursos, incluidos los **anidados** (Form XObjects, patrones,
      shadings, grupos de transparencia, anotaciones con apariencia) y recoger los espacios de color:
      `DeviceCMYK`, `DeviceRGB`, `DeviceGray`, `ICCBased` (con N componentes), `Separation`, `DeviceN`
      (incluido NChannel con `Colorants`), `Indexed` (con su base) y `Lab`.
- [ ] Para cada `Separation`/`DeviceN`: nombre de la tinta, espacio alternativo y *tint transform* (función tipo 0, 2 o 4;
      evaluar la función para obtener el CMYK/Lab alternativo al 100%).
- [ ] Clasificar el tipo con reglas y palabras clave configurables (`config.json → "ink_keywords"`):
      blanco (`white`, `blanco`, `weiss`), barniz (`varnish`, `barniz`, `lack`), técnica (`die`, `cut`, `troquel`,
      `stanz`, `dieline`, `braille`, `dimension`, `cota`, `crease`, `perf`). `All` = color de registro.
- [ ] Detectar **duplicados** por nombre normalizado y **tintas no usadas** (definidas pero sin objetos que las pinten).
      Para "no usadas", verificar con el render: la placa sale vacía.
- [ ] Resultado: lista de `Ink` + por cada tinta: páginas donde aparece, nº de objetos (aprox.) y si es alternativa RGB.

### 6.2 Render de separaciones (`modules/separate/pdf_render.py`)
- [ ] Ghostscript `tiffsep`:
      `-sDEVICE=tiffsep -r<dpi> -dMaxSpots=<n> -dOverprint=/simulate -dFirstPage=p -dLastPage=p
       -sOutputFile=<dir>/p%03d.tif <archivo.pdf>`
      → un TIFF de 8 bits por tinta (`p001(Cyan).tif`, `p001(PANTONE 485 C).tif`…) + el compuesto.
      Mapear cada archivo con su tinta usando el nombre entre paréntesis (cuidado con caracteres especiales; probar
      nombres con acentos, `/` y espacios).
- [ ] dpi: 150 para la vista previa (rápido) y 300–600 para exportar. Límite configurable de megapíxeles
      (`max_render_mpx`, por defecto 120) → si se supera, bajar el dpi y avisar.
- [ ] Convención de valores: 0 = sin tinta … 255 = 100% (invertir si `tiffsep` entrega al revés; **test obligatorio**
      con un PDF sintético de parches al 0/25/50/75/100%).
- [ ] **Vista compuesta simulada**: combinar las placas con el modelo de mezcla (7.3) y los Lab de las tintas
      (biblioteca del usuario o la alternativa del PDF) → PNG sRGB. Permite activar/desactivar tintas y verlas juntas.
- [ ] Caché del render por (hash del archivo, página, dpi).

### 6.3 Análisis
- [ ] **Densitómetro**: `GET /api/separate/pdf/{job}/probe?x=&y=` → % de cada tinta en un radio de 3 px (media) + TAC.
- [ ] **TAC** (cobertura total = suma de %): mapa de calor, máximo y percentil 99.5. Límite configurable por perfil
      (offset 300%, flexo 280%, digital 320%, papel prensa 240%). Zonas que superan el límite → recuadros como en Comparar.
- [ ] **Cobertura por tinta** (% del área de la página) → útil para el cálculo de consumo de tinta.
- [ ] **Chequeos de separación** (cada uno con recuadro + mensaje en español):
  - [ ] negro enriquecido en texto < 12 pt (texto con K + otras tintas; detectar con las posiciones de texto de PyMuPDF),
  - [ ] texto pequeño (< 6 pt) en más de una tinta (problemas de registro),
  - [ ] blanco o barniz en **knockout** cuando debería sobreimprimir (y al revés: blanco sobreimpreso que desaparece),
  - [ ] objetos en color de **registro** (`All`) fuera de las marcas,
  - [ ] tintas técnicas (troquel/cotas) que **no** estén en sobreimpresión (se imprimirían),
  - [ ] RGB o Lab sin convertir,
  - [ ] líneas finas (< 0.1 mm, configurable) en tintas de proceso combinadas.

### 6.4 Edición de tintas (`modules/separate/pdf_edit.py`, con pikepdf, **siempre sobre una copia**)
- [ ] **Unir** tintas duplicadas: reescribir los arrays `Separation`/`DeviceN` para usar un nombre canónico.
- [ ] **Renombrar** una tinta.
- [ ] **Convertir directa → proceso**: reemplazar el espacio `Separation` por su alternativo (DeviceCMYK), aplicando la
      función de tinte a los operadores de color del contenido (`scn`/`SCN`, imágenes y shadings). Si el contenido no
      permite conversión exacta (p. ej. imágenes DeviceN complejas), avisar y omitir ese objeto.
- [ ] **Eliminar** tintas no usadas del diccionario de recursos.
- [ ] **Mapear** una tinta a otra (A → B).
- [ ] Tras editar: volver a inventariar + render y **comparar visualmente** el antes y el después con el motor de Comparar
      (debe ser idéntico salvo en lo pedido; tolerancia SSIM ≥ 0.999 en las tintas no tocadas).
- [ ] Guardar como `<nombre>_faverview.pdf`; **nunca** sobrescribir el original.

### 6.5 Exportación
- [ ] Placas como **TIFF** 8 bits (o 1 bit con umbral 50% para películas simples), con nombre `<archivo>_<tinta>.tif`.
- [ ] **PDF de placas**: una página por tinta en escala de grises con su nombre, marcas de registro y la cobertura.
- [ ] **Hoja de separaciones** (reporte): miniaturas de cada placa, Lab/alternativo, cobertura, TAC máx., chequeos.

### 6.6 UI (pestaña "Separar colores" → sub-pestaña "PDF")
- Soltar el PDF → selector de página → la lista de tintas (muestra de color, nombre, tipo, cobertura %, ojo 👁,
  solo/ocultar, negativo) + el visor con la composición.
- Panel derecho: densitómetro en vivo (tabla tinta → %), TAC.
- Pestaña "Problemas": chequeos con clic → zoom.
- Botones: Unir duplicadas · Renombrar · Convertir a proceso · Eliminar no usadas · Exportar placas · Reporte.

### 6.7 Pruebas S2
- [ ] Generador `bench/synth_separations.py`: PDFs sintéticos con pikepdf/PyMuPDF que contengan: CMYK, 2 Separation,
      1 DeviceN de 2 tintas, un duplicado de nombre ("Demo 485C" vs "DEMO 485 C"), una tinta no usada, blanco en
      knockout, texto de 5 pt en 4 colores, negro enriquecido y una zona con TAC 340%.
- [ ] Tests: el inventario encuentra exactamente las tintas esperadas; placas con % correctos (± 1%) en los parches;
      TAC detectado; los 7 chequeos disparan en su caso y **no** disparan en el PDF "limpio"; unir, renombrar, convertir
      y eliminar producen el resultado esperado y el render de las demás tintas no cambia.
- [ ] Rendimiento: PDF A4 con 6 tintas a 150 dpi → vista lista en ≤ 5 s.

---

## 7. S3 – Separador de colores: imagen (raster) → tintas

Entrada: JPG/PNG/TIFF/PSD aplanado/PDF rasterizado. Salida: canales por tinta (8 bits), placas tramadas (1 bit),
vista simulada y PDF con canales DeviceN.

### 7.1 Parámetros comunes
- Sustrato: color Lab (blanco papel por defecto; biblioteca de "prendas" editable: negro, gris, rojo, azul marino, kraft).
- Juego de tintas: elegido de la biblioteca del usuario o detectado automáticamente (7.2).
- Resolución de trabajo (por defecto la de la imagen, mínimo 150 ppi al tamaño final en mm, con aviso si es menor).
- Orden de impresión (importa con tintas opacas).

### 7.2 Modo **Tintas planas** (logos, ilustraciones)
1. Suavizado que preserva bordes (bilateral o mean-shift, parámetros según el tamaño).
2. Conversión a Lab.
3. Paleta:
   - **Automática:** k-means en Lab (k de 2 a 12) sobre una muestra de ≤ 200 000 píxeles; k elegido con el criterio
     "fusionar clusters con ΔE2000 < `merge_de` (por defecto 6)" y "descartar clusters < 0.05% del área". Resultado
     editable por el usuario.
   - **Fija:** el usuario elige las tintas; cada píxel se asigna a la más cercana (ΔE2000).
4. Limpieza: eliminar islas < `min_area_mm2` (convertido a px) y reasignarlas a la región vecina dominante; cerrar
   agujeros pequeños.
5. Bordes antialias: opción **"bordes duros"** (asignación directa) u **"bordes suaves"** (en los píxeles de borde,
   % proporcional a la mezcla estimada de las dos tintas vecinas).
6. Salida: 1 canal por tinta (0/255 o suave).
- [ ] Opción "enviar al vectorizador" con la misma paleta (enlace con S4).

### 7.3 Modelo de mezcla de tintas (`core/colorscience.py`, compartido)
Aproximación documentada (no espectral):
- Trabajar en **RGB lineal** (reflectancia aproximada por canal).
- Tinta **transparente** i con cobertura tᵢ: `R = R_sustrato · Π (1 − tᵢ · (1 − Rᵢ/R_sustrato_ref))`,
  donde Rᵢ es la reflectancia de la tinta sólida sobre papel blanco.
- Tinta **opaca** (blanco, metálicos): composición "over" en el orden de impresión con alfa = tᵢ · opacidadᵢ.
- **Factor n de Yule-Nielsen** opcional (`n`, por defecto 1.7) sobre la reflectancia para aproximar la ganancia de punto
  óptica: usar R^(1/n) en el modelo y elevar a n al final.
- Validar: con una tinta, t = 0 → sustrato y t = 1 → tinta sólida (tests).
- Documentar en `DECISIONES.md` que es orientativo; la calibración real (S7.6) mejora la precisión.

### 7.4 Modo **Proceso simulado** (fotos sobre prenda/pocas tintas)
1. Imagen en Lab → **tabla de consulta**: cuantizar la imagen a una rejilla de 33×33×33 en Lab (o a colores únicos
   si hay pocos).
2. Para cada entrada, resolver las coberturas t ∈ [0,1]ⁿ que minimizan ΔE (aprox. con distancia euclídea en Lab,
   pesada) usando el modelo 7.3: `scipy.optimize.least_squares` con límites, inicializado con la solución de la entrada
   vecina (continuidad) + regularización suave hacia menos tinta total (λ configurable, favorece el ahorro de tinta).
3. Interpolar la tabla (trilineal) para toda la imagen.
4. **Base blanca automática** en prenda oscura: canal blanco = f(luminosidad y cobertura del resto de tintas),
   con **choke** (erosión de 1–3 px al dpi de salida) para que no asome por los bordes, y **blanco de luces** opcional
   (una segunda pasada de blanco solo en las luces).
5. Postproceso por canal: curva (gamma), punto mínimo (eliminar < 3–5%, que no se imprime) y punto máximo.
- [ ] Mostrar el **ΔE estimado** (mapa de calor de lo que el juego de tintas no alcanza a reproducir) y el ΔE medio/p95.
- [ ] Rendimiento: imagen de 4000×5000 con 6 tintas → ≤ 30 s (la tabla lo hace viable; paralelizar las entradas por bloques).

### 7.5 Modo **Índice** y modo **CMYK**
- **Índice:** paleta (automática o fija) + **difusión de error** (Floyd–Steinberg o Jarvis-Judice-Ninke, elegible)
  en Lab, con recorrido serpentina, a la resolución de salida (por defecto 200 ppi). Aviso: "no se puede reescalar
  después".
- **CMYK:** conversión ICC con LittleCMS (perfil elegido: FOGRA39/51, GRACoL o uno del usuario), intención perceptual o
  colorimétrica relativa con BPC, y **límite de TAC** aplicado después (reducir CMY proporcionalmente y mantener K,
  una estrategia tipo GCR simple, documentada). Opción "negro solo en sombras" (curva de generación de K).
  Perfiles ICC: **no** incluir perfiles con licencia dudosa; usar los que el usuario tenga (Windows `spool\drivers\color`) o
  los de ECI (verificar la licencia de redistribución antes de incluirlos; si no está clara, solo instrucciones para
  descargarlos).

### 7.6 Calibración opcional (mejora del modelo)
- [ ] Generar un **gráfico de prueba** PDF (rampas 0–100% por tinta + sobreimpresiones de pares) para imprimir con el
      juego de tintas real.
- [ ] El usuario introduce los Lab medidos (CSV o manual) → ajustar por mínimos cuadrados: reflectancia sólida real,
      factor n y curva de ganancia por tinta. Guardar como "perfil de tintas" en `datos_locales/tintas/perfiles/`.

### 7.7 Tramado (`modules/separate/halftone.py`)
- [ ] **AM**: punto redondo/elíptico/cuadrado, lineatura (lpi) y ángulo por tinta (por defecto: serigrafía 45–65 lpi
      a 22.5°; offset 150 lpi con C15 M75 Y0 K45), generado con una **matriz umbral** rotada a la resolución de salida
      (600–2400 dpi). Procesar por mosaicos para no exceder la memoria.
- [ ] **FM/estocástico**: difusión de error o *blue noise* (máscara precomputada, generada por el agente con el
      algoritmo *void-and-cluster* y guardada en `tools/`).
- [ ] Punto mínimo y máximo imprimible (p. ej. 3%/95%).
- [ ] Salida: TIFF 1 bit por placa (compresión CCITT G4) y vista previa ampliada.
- [ ] Test: una rampa 0–100% tramada tiene una cobertura medida ≈ la nominal (± 2%) en cada escalón.

### 7.8 Salidas S3
- [ ] Canales 8 bits (TIFF por tinta), placas 1 bit, **PSD multicanal** (opcional: si no hay librería fiable, omitir y
      documentar), **PDF DeviceN** (una imagen con n canales y los nombres de las tintas, con alternativos CMYK
      desde el Lab) y vista simulada sobre el sustrato (PNG).
- [ ] Reporte: tintas, orden, cobertura, ΔE estimado y parámetros.

### 7.9 UI (pestaña "Separar colores" → sub-pestaña "Imagen")
Asistente de 4 pasos: **1. Imagen y sustrato → 2. Modo y tintas → 3. Ajustes (con vista previa en vivo a baja
resolución) → 4. Salida**. En el visor: vista simulada, canal individual, "solo esta tinta" y comparación dividida
(original | simulada).

### 7.10 Pruebas y banco S3 (`bench/separation/`)
- [ ] 25 casos sintéticos generados por código: logos planos de 2–8 colores con antialias + JPEG, degradados,
      "fotos" sintéticas (ruido de Perlin coloreado), sobre sustrato blanco y negro.
- [ ] Métricas: tintas planas → precisión de la paleta (ΔE a los colores verdaderos), IoU por región y nº de islas
      espurias; proceso simulado → ΔE medio/p95 de la simulación vs el original y la cobertura total media.
- [ ] Metas: tintas planas IoU medio ≥ 0.97 y ΔE de paleta ≤ 3; proceso simulado ΔE medio ≤ 6 con 6 tintas sobre
      negro (orientativo, ajustar tras la línea base).
- [ ] Guardar la línea base y comparar en cada cambio (mismo mecanismo que `bench.run`).

---

## 8. S4 – Vectorizador v1

### 8.1 Pipeline (`modules/vectorize/`)
```
preprocess.py → quantize.py → regions.py → boundaries.py → fit.py → export.py
```
1. **Preprocesado** (`preprocess.py`):
   - si el lado corto es < 800 px, escalar ×2–×4 (Lanczos) antes de todo,
   - quitar el ruido JPEG/antialias con bilateral o mean-shift (`cv2.pyrMeanShiftFiltering`),
   - modo B/N: umbral adaptativo (Sauvola) + opción manual.
2. **Cuantización** (`quantize.py`): reutilizar el modo "tintas planas" de S3 (7.2), con **paleta controlada**
   (automática, fija o desde la biblioteca de tintas). Resultado: un mapa de etiquetas `L[y,x]`.
3. **Regiones** (`regions.py`): componentes conexos por etiqueta; eliminar islas < `min_area_px` reasignándolas
   al vecino con el que comparten más borde; rellenar agujeros < umbral.
4. **Fronteras compartidas** (`boundaries.py`), clave para **cero huecos**:
   - construir el **grafo de bordes de grieta** (*crack edges*): los segmentos entre píxeles de etiquetas distintas,
     incluido el borde de la imagen,
   - encadenar los segmentos en **cadenas** entre **nodos** (puntos donde se tocan ≥ 3 regiones o el borde),
   - cada cadena separa exactamente dos regiones (o región/borde) y se ajusta **una sola vez**. Ambas regiones usan la
     misma curva en sentidos opuestos → **imposible** que queden huecos o solapes.
5. **Ajuste de curvas** (`fit.py`) por cadena:
   - suavizado de la escalera de píxeles (puntos medios de los segmentos + filtro ligero),
   - **detección de esquinas**: ángulo de giro local > `corner_angle` (por defecto 60°) con ventana adaptativa → las
     esquinas se conservan como nodos duros,
   - entre esquinas: **ajuste de Bézier cúbicas por mínimos cuadrados** (algoritmo de Schneider, *Graphics Gems*,
     1990) con tolerancia `fit_tol_px` (por defecto 0.8 px), subdividiendo donde el error supera la tolerancia,
   - continuidad G1 en los nodos no esquina.
6. **Ensamblado**: cada región = lista ordenada de cadenas (con sentido) → trazado cerrado. Agujeros como subtrazados
   con la regla *even-odd* **o** (opción "apilado", tipo VTracer) regiones grandes debajo y las contenidas encima,
   sin agujeros. Por defecto: "sin solapes" (fronteras compartidas); "apilado" como opción.
7. **Exportación** (`export.py`):
   - **SVG** (colores sRGB de la paleta),
   - **PDF** con PyMuPDF/pikepdf, donde cada color es una **tinta directa `Separation`** con su nombre y alternativo
     CMYK, o CMYK puro. Opción **sobreimpresión** para una tinta técnica,
   - **EPS** (vía Ghostscript `eps2write` desde el PDF),
   - **DXF** (ezdxf; curvas como SPLINE o polilíneas finas, en mm) para corte y troquel.
   - Unidades: el usuario indica el tamaño final en mm → escalar las coordenadas.

### 8.2 Controles de preprensa (v1)
- [ ] `min_detail_mm` (por defecto 0.15 mm): detalles más finos que eso → eliminar o engrosar (opción) según
      el tamaño final.
- [ ] Número máximo de colores; bloquear colores de la biblioteca.
- [ ] Simplificación global (tolerancia), respetando las esquinas.
- [ ] Estadísticas: nº de trazados, nodos, colores y tiempo.

### 8.3 UI (pestaña "Vectorizar")
- Soltar la imagen → preajustes: **Logo**, **Línea (B/N)**, **Ilustración**, **Escaneo**, **Foto posterizada**.
- Controles: colores, detalle mínimo, suavidad, esquinas, modo (sin solapes / apilado), tamaño final (mm).
- Visor: original | vector | superpuesto | **contornos** (ver los nodos) | **diferencias** (reutiliza Comparar: resalta
  dónde el vector se aparta del original).
- Vista en vivo con una versión reducida; la vectorización final se hace en segundo plano.
- Descargar SVG / PDF / EPS / DXF.

### 8.4 Banco de pruebas del vectorizador (`bench/vector/`), obligatorio en S4
**Casos con verdad exacta (sintéticos):**
- [ ] 40 logos vectoriales generados por código (formas geométricas, curvas Bézier aleatorias, texto convertido a
      trazados con fuentes libres incluidas en el repositorio, trazos finos, colores de 2 a 8 tintas).
- [ ] Rasterizados con degradaciones: 72–300 ppi, JPEG q 50–95, desenfoque, antialias, rotación ±2° y ruido.
- [ ] Como el vector original se conoce, se mide contra él.

**Casos reales:** `datos_locales/vector_bench/reales/` (el usuario aporta 10–20 imágenes: logos de WhatsApp, escaneos, etc.).

**Métricas** (render de cada SVG/PDF con **PyMuPDF**, que abre SVG, a la resolución del original ×2):
| Métrica | Definición |
|---|---|
| Fidelidad | SSIM entre el render y el original (reales) o el vector verdadero (sintéticos); ΔE2000 medio por píxel |
| IoU por color | intersección/unión de cada color con la verdad (sintéticos) |
| Huecos | % de píxeles de "fondo visible" entre regiones que deberían tocarse (render sin antialias) |
| Complejidad | nº de nodos y nº de trazados (a igual fidelidad, menos es mejor) |
| Fidelidad de color | nº de colores de salida vs los pedidos; ΔE de cada color a su tinta objetivo |
| Tiempo | segundos por imagen |

**Competidores:** VTracer y Potrace (se ejecutan automáticamente) + **Illustrator Image Trace** y **CorelDRAW
PowerTRACE**, cuyos SVG el usuario genera **a mano** con preajustes documentados y guarda en
`datos_locales/vector_bench/externos/<herramienta>/<caso>.svg`. El banco los incluye si existen.

- [ ] `uv run python -m bench.vector.run [--etiqueta …]` → reporte `.md`/`.html` con una tabla por herramienta y por tipo de caso,
      imágenes lado a lado y el ganador por métrica.
- [ ] Guía en el manual: "Cómo generar los archivos de Illustrator/Corel para el banco" (preajuste, colores, exportar SVG).

**Metas S4 (sintéticos):** huecos = 0% (por construcción); SSIM ≥ VTracer en ≥ 80% de los casos; nodos ≤ VTracer
en ≥ 70% de los casos a SSIM igual o mayor (± 0.005).

---

## 9. S5 – Vectorizador v2 (superar a Image Trace)

- [ ] **Primitivas**: para cada cadena (o secuencia de cadenas entre esquinas) intentar ajustar:
  - **segmento recto** (mínimos cuadrados + error máximo < `prim_tol_px`),
  - **arco / círculo** (ajuste algebraico de Kåsa o Taubin + refinamiento geométrico),
  - **elipse** (Fitzgibbon directo),
  - si una región completa es un círculo, elipse o rectángulo (con esquinas redondeadas o no) → emitirla como tal.
  Aceptar la primitiva solo si el error ≤ tolerancia **y** no empeora el SSIM local. Las primitivas se convierten a
  Bézier exactas en la salida (círculo = 4 cúbicas, κ = 0.5523).
- [ ] **Enderezado**: segmentos casi horizontales/verticales (< 2°) → exactos; ángulos casi rectos → 90°
      (opción "geometría limpia").
- [ ] **Simetría**: detectar un eje de simetría global o por región (comparar la región reflejada, IoU > 0.97) →
      ajustar una mitad y reflejarla (opción).
- [ ] **Paralelismo y grosor constante** en trazos (líneas de ancho uniforme): detectar trazos por la transformada de
      distancia + esqueleto; opción de exportarlos como **trazo con grosor** en lugar de relleno (modo "línea").
- [ ] **Zonas de texto**: detectar texto con el OCR existente; opciones: vectorizar normal / marcar la zona /
      reemplazar por texto real con una fuente elegida por el usuario (sugerir fuentes instaladas por la similitud de
      las métricas: altura x, contraste de trazo, serifas; **orientativo**).
- [ ] **Controles de preprensa v2**: engrosar automáticamente los detalles < mínimo (dilatación vectorial por
      offset), cerrar contornos para corte y opción "sin nodos duplicados".
- [ ] **Edición básica** en la UI: fusionar dos colores, recolorear, borrar una región y volver a vectorizar una zona
      seleccionada con otros parámetros.

**Metas S5 (banco):** frente a Image Trace (cuando haya archivos) en logos: SSIM igual o mayor en ≥ 70% de los casos,
**menos nodos** en ≥ 70% y **0 huecos**. La UI solo puede decir "mejor que X en logos" si el último reporte del banco lo
respalda. Mostrar la fecha y el enlace al reporte.

---

## 10. S6 – Preflight y códigos de barras

### 10.1 Preflight (`modules/preflight/`)
- [ ] **Motor de reglas**: cada regla = función `check(doc, ctx) -> list[Finding]` con `id`, `severidad`
      (`error` / `advertencia` / `info`), mensaje en español, página y bbox (para el visor).
- [ ] **Perfiles** en JSON (`app/modules/preflight/perfiles/*.json`), editables y duplicables:
      "Offset hoja (tipo GWG2015 Sheetfed CMYK)", "Flexo empaque", "Etiquetas digital", "Serigrafía",
      "Solo revisión básica". Cada perfil activa reglas con umbrales. **No llamar a los perfiles "GWG"** (no estamos
      certificados): usar "inspirado en GWG 2015".
- [ ] Reglas (mínimo):
  | Regla | Fuente del dato |
  |---|---|
  | Fuentes no incrustadas / Type 3 / subconjunto | PyMuPDF `get_fonts` |
  | Resolución efectiva de imágenes (ppi al tamaño colocado; min color/gris/1 bit) | matriz de colocación × tamaño en píxeles |
  | Espacios de color no permitidos (RGB, Lab, ICC no CMYK) | inventario S2 |
  | Nº de tintas directas > máximo; nombres duplicados | inventario S2 |
  | TAC > límite | S2 |
  | Líneas finas < mínimo (en mm, considerando el CTM) | PyMuPDF `get_drawings` (`width` × escala) |
  | Texto pequeño < mínimo (positivo/negativo, 1 tinta / multitinta) | spans + color |
  | Negro enriquecido en texto pequeño; texto negro que no sobreimprime | S2 + ExtGState |
  | Blanco sobreimpreso; tintas técnicas sin sobreimpresión | ExtGState `OP/op/OPM` |
  | Sangrado insuficiente (BleedBox – TrimBox < 3 mm) y objetos cerca del corte (zona segura) | cajas + bbox de objetos |
  | TrimBox ausente; tamaño de página distinto al esperado | pdfinfo |
  | Transparencias (en perfiles PDF/X-1a) | grupos de transparencia, SMask, CA/ca < 1 |
  | Capas (OCG) ocultas con contenido | OCProperties |
  | Anotaciones/campos de formulario en el área de impresión | Annots |
  | Versión PDF/X y OutputIntent presentes/correctos | pdfinfo |
  | Imágenes con compresión JPEG muy fuerte (estimación de la calidad por las tablas de cuantización) | flujo de la imagen |
- [ ] **Correcciones seguras** (sobre una copia, cada una opcional). **No** se intenta incrustar fuentes que faltan
      (no están disponibles; solo se reporta). Correcciones permitidas: eliminar anotaciones, unir tintas duplicadas (S2), añadir TrimBox/BleedBox con valores
      indicados, poner la sobreimpresión en tintas técnicas y en texto negro 100% K pequeño.
      Cada corrección → re-preflight + comparación visual antes/después (motor de Comparar).
- [ ] Reporte PDF: resumen (errores/advertencias), lista con miniatura de la zona, perfil usado y fecha.
- [ ] UI: soltar el PDF → elegir el perfil → resultados agrupados por severidad → clic → zoom en el visor.

### 10.2 Códigos de barras (`modules/barcodes/`)
**Generar**
- [ ] Tipos: EAN-13, EAN-8, UPC-A, UPC-E, ITF-14, GS1-128, Code 128, Code 39, GS1 DataMatrix, QR (segno),
      GS1 DataBar (vía BWIPP/treepoem).
- [ ] Validación de datos: dígito de control (calcular o verificar), longitudes y AIs de GS1 (tabla básica de AIs
      comunes: 01, 10, 17, 21, 310x, 11, 15). Mensajes claros en español.
- [ ] Parámetros: **magnificación** 80–200% (EAN-13 al 100% = 37.29 × 25.93 mm, con el módulo X = 0.33 mm), altura,
      **reducción de barras (BWR)** en mm o µm (compensación de la ganancia: el usuario la indica según su proceso),
      zonas de silencio (con el indicador `>` opcional en EAN), texto legible (fuente OCR-B libre si está disponible;
      si no, documentar), color = una tinta de la biblioteca.
- [ ] Salida **vectorial**: PDF (tinta directa o K), SVG y EPS. Nunca raster.
- [ ] Lote: CSV → un PDF por código o una hoja.

**Verificar** (en un PDF o una imagen)
- [ ] Detectar y **decodificar** todos los códigos con zxing-cpp sobre el render a 600 dpi (PDF) o la imagen.
- [ ] Informar: tipo, contenido, dígito de control correcto, **magnificación medida** (desde el ancho del módulo en mm),
      zonas de silencio suficientes, contraste entre barras y fondo (desde el render en color y el Lab de las
      tintas: p. ej. rojo sobre blanco = ilegible para escáneres de luz roja → **error**), orientación respecto a la
      dirección de impresión flexo (advertencia si las barras son paralelas a la dirección de impresión).
- [ ] **Grado estimado** inspirado en ISO/IEC 15416 (reflectancia mínima, contraste del símbolo, modulación,
      defectos) a partir del render: mostrar como **"estimación A–F, no es una verificación certificada"**.
- [ ] Test: generar cada tipo → verificar → decodifica el mismo contenido; casos inválidos (dígito de control malo,
      zona de silencio corta, rojo sobre blanco) disparan los avisos.

---

## 11. S7 – Herramientas avanzadas (`modules/tools/`)

### 11.1 Trapping (reventado)
Enfoque **por placas (raster)**, robusto y explicable; el trapping vectorial queda fuera de alcance (documentado).
- [ ] Entrada: placas de S2 (a dpi de salida) + tintas con Lab.
- [ ] Para cada par de tintas adyacentes (bordes donde una termina y otra empieza), decidir la dirección con
      reglas estándar: **la tinta más clara se expande bajo la más oscura** (luminancia L*, o densidad);
      el negro/tintas oscuras no se expanden; blanco y barniz: reglas propias (el blanco se contrae = choke);
      tintas técnicas: nunca.
- [ ] Ancho del trap por tinta y por proceso (por defecto flexo 0.15 mm, offset 0.08 mm, serigrafía 0.2–0.3 mm), con
      una tabla editable "tinta A → tinta B: ancho".
- [ ] Implementación: dilatación morfológica de la placa clara **restringida** a la zona de la oscura (máscara de
      borde), con un elemento estructurante circular del radio en px. Opción de "trap al 100%" o "reducido" (p. ej. 50%) y
      tope de TAC en la zona del trap.
- [ ] No trapear: texto < X pt (opción "mantener el texto pequeño"), degradados que se tocan (opción), imágenes
      (opción).
- [ ] Salida: placas con trapping (TIFF) + **mapa de traps** (capa de color en el visor para revisarlos) + PDF de placas.
- [ ] Simulación de **mal registro**: desplazar una placa ±N µm y mostrar la vista con y sin trap (lo convence al cliente).
- [ ] Tests: dos rectángulos adyacentes (claro/oscuro) → el claro se expande exactamente el ancho, solo bajo el oscuro.

### 11.2 Step & repeat / imposición / marcas
- [ ] Entrada: un PDF de etiqueta/diseño (usa TrimBox/BleedBox).
- [ ] Parámetros: hoja o banda (ancho × repetición o largo en mm), filas × columnas (o "rellenar"), separación
      horizontal/vertical (gap), **sangrado compartido** o no, rotación por fila/columna (0/90/180/270),
      **desfase** (stagger) por fila/columna, márgenes.
- [ ] Implementación: PyMuPDF `show_pdf_page` (reutiliza el contenido como Form XObject; el archivo no crece por copia).
- [ ] **Marcas dinámicas**: registro (cruz, en la tinta de registro `All`), corte, **barra de control de color** con
      parches sólidos de cada tinta del trabajo y 50%, **microdots** (flexo), texto de identificación (trabajo, fecha,
      tinta: en cada placa sale su nombre con el color de esa tinta), guías de troquel.
- [ ] Exportar PDF + reporte (nº de repeticiones, aprovechamiento %).
- [ ] Tests: 3×4 con gap 3 mm → posiciones exactas (± 0.01 mm); las marcas aparecen en todas las placas (verificar con S2).

### 11.3 Distorsión flexo
- [ ] Compensación del alargamiento del cliché al montarlo en el cilindro:
      `D% = (2π · k / R) · 100`, con `k` = espesor del cliché − espesor de la base de poliéster (factor k de la tabla del
      fabricante, **introducido por el usuario**) y `R` = repetición (desarrollo del cilindro) en mm. Documentar la
      fórmula y permitir introducir **D% directamente** (lo que da el fabricante).
- [ ] Escalar el PDF solo en la dirección de impresión (elegir horizontal/vertical) con PyMuPDF (matriz), por página.
- [ ] Añadir una nota con la distorsión aplicada en el margen. Test: 100 mm con D = 2% → 98 mm.

### 11.4 Braille
- [ ] Traducción de texto a braille español (grado 1) con liblouis (`es-g1.ctb`). Si `louis` no está disponible en
      Windows, implementar una **tabla propia de grado 1 español** (alfabeto, acentos, números con signo numérico,
      mayúsculas) y documentarla.
- [ ] Geometría **Marburg Medium** (usada en farmacéutica, EN 15823): diámetro de punto ≈ 1.6 mm, distancia entre
      puntos 2.5 mm, entre caracteres 6.0 mm y entre líneas 10.0 mm (**verificar** los valores con la norma o con la
      referencia disponible y hacerlos configurables).
- [ ] Salida: capa vectorial en la tinta técnica "Braille" (sobreimpresión) + vista previa. Aviso de la zona libre de
      pliegues/solapas.
- [ ] Test: "Paracetamol 500 mg" → celdas esperadas (tabla de referencia en el test).

### 11.5 Gama extendida (tipo Equinox)
- [ ] Juego de tintas fijo (p. ej. CMYK+OGV) con Lab de sus sólidos (biblioteca del usuario).
- [ ] Para cada tinta directa del trabajo: buscar coberturas (≤ 3 tintas activas, preferir 2) que minimicen ΔE2000
      usando el modelo 7.3 (o el perfil calibrado 7.6) con `least_squares` + búsqueda combinatoria de subconjuntos.
- [ ] Tabla: tinta directa → receta (%), ΔE estimado y semáforo (≤ 2 verde, ≤ 4 amarillo, > 4 rojo = "no reproducible
      con este juego").
- [ ] Aplicar al PDF: reemplazar cada `Separation` convertible por un `DeviceN` de las tintas fijas con la función de
      tinte correspondiente (lineal por tramo). Comparar el render antes/después (simulado).
- [ ] Nota honesta en la UI: "estimación basada en un modelo; confirmar con prueba impresa".

### 11.6 Prueba en pantalla (soft proof)
- [ ] Simulación del trabajo con: tintas reales (Lab), sustrato (color + textura opcional kraft/cartón/prenda),
      ganancia de punto (curva simple por tinta) y opción "ver sin blanco".
- [ ] Siempre con la etiqueta "Vista orientativa, no es una prueba contractual".

**Criterios S7:** cada herramienta con sus tests y una sección en el manual con capturas.

---

## 12. S8 – Automatización ("recetas")

- [ ] **Receta** = JSON con una lista de pasos, cada uno `{modulo, accion, parametros}`, p. ej.:
      `preflight(perfil=Flexo) → separar.unir_duplicadas → separar.exportar_placas(dpi=1200) → tools.step_repeat(…) → reporte`.
- [ ] Editor visual simple en la UI (lista de pasos con parámetros; arrastrar para reordenar) + importar/exportar JSON.
- [ ] Ejecutar una receta sobre: un archivo, una **carpeta** o una **carpeta vigilada** (watchdog: `entrada/` →
      `salida/` + `errores/` + `reportes/`).
- [ ] Condiciones: "si el preflight tiene errores → detener y mover a `errores/`".
- [ ] Registro por archivo (log legible en español) y resumen del lote (reutiliza los lotes de v2).
- [ ] Recetas de ejemplo incluidas: "Revisión rápida", "Preparar etiqueta flexo", "Separar logo para serigrafía".
- [ ] Tests: receta de 3 pasos sobre 5 archivos sintéticos → 5 salidas + 1 archivo con error en `errores/`.

---

## 13. Requisitos transversales

### 13.1 Rendimiento y memoria
- Procesar por **mosaicos** todo lo que se haga a más de 600 dpi (tramado, trapping, placas).
- Límite global de megapíxeles por operación (`max_render_mpx`) con un aviso claro en español.
- Operaciones > 1 s en segundo plano con progreso; botón **Cancelar** (bandera de cancelación comprobada entre etapas y
  mosaicos; matar el proceso de Ghostscript si está en curso).

### 13.2 Calidad
- Tests unitarios por módulo (pytest) + casos sintéticos + **bancos de pruebas** (Comparar, Separación, Vectorizador) con
  línea base y comparación. Cobertura ≥ 80% en `app/modules/*` (medir con `pytest-cov`, dependencia dev).
- CI: pytest + los 3 bancos en modo `--ci` (umbrales versionados en `bench/*/umbral_ci.json`). Tiempo total de CI
  ≤ 40 min (usar subconjuntos en CI si hace falta).

### 13.3 UX
- Todas las pestañas con: soltar/pegar archivos, visor compartido, historial del módulo y botón "Enviar a…"
  (p. ej. Separar → Vectorizar → Preflight) para encadenar módulos sin volver a subir el archivo.
- Accesibilidad básica: contraste, foco con teclado y textos alternativos.
- Atajos: `Espacio` + arrastrar = paneo, `Ctrl+0` = ajustar, `Ctrl+1` = 100%.

### 13.4 Documentación
- Manual de usuario (el PDF existente) ampliado con un capítulo por módulo, capturas y ejemplos.
- `README.md`: instalación (con Ghostscript), módulos y enlaces.
- Glosario de preprensa en español (TAC, trapping, sobreimpresión, tinta directa, BWR, lpi…) dentro del manual.
- **Obligatorio en el manual y en el `README.md`** (en S1, cuando Ghostscript pase a ser necesario):
  - **Instalar Ghostscript:** no está en winget. Incluir este comando de PowerShell (descarga el release oficial más
    reciente de Artifex, verifica la firma Authenticode y lo instala en silencio):
    ```
    $r = Invoke-RestMethod https://api.github.com/repos/ArtifexSoftware/ghostpdl-downloads/releases/latest; $a = $r.assets | ? name -like '*w64.exe'; $f = "$env:TEMP\$($a.name)"; Invoke-WebRequest $a.browser_download_url -OutFile $f; $s = Get-AuthenticodeSignature $f; if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'Artifex') { Start-Process $f -ArgumentList '/S' -Verb RunAs -Wait; Write-Host 'Ghostscript instalado' } else { Write-Host "Firma NO valida: $($s.Status). No se instalo." }
    ```
    más la verificación: `& (Get-ChildItem "C:\Program Files\gs\*\bin\gswin64c.exe" | Select -Last 1).FullName --version`
    y la tabla "Si algo falla" (sin permisos de administrador, antivirus, firma no válida → no instalar).
  - **Bibliotecas de tintas (Pantone y otras):** capítulo "Cómo obtener tus bibliotecas de tintas de forma legal":
    - explicar que Pantone, HKS, RAL, TOYO y DIC son bibliotecas comerciales con licencia, que FAVERVIEW **no** las incluye y
      que no se deben usar copias no autorizadas;
    - paso a paso para **exportar desde Illustrator** (con Pantone Connect): Panel Muestras → seleccionar → menú ☰ →
      "Guardar biblioteca de muestras como ASE";
    - **Pantone Connect Premium**: crear paletas y exportarlas como ASE/CxF;
    - **tintas medidas** con espectrofotómetro → CxF/CSV (formato CSV `nombre,L,a,b[,tipo][,opacidad]` con un ejemplo);
    - pedir las **CxF al proveedor de tintas** (Siegwerk, Sun Chemical, Flint, etc.);
    - cómo **importarlas** en FAVERVIEW (pantalla "Tintas") y dónde se guardan (`datos_locales/tintas/`, privado,
      nunca se sube a GitHub);
    - qué trae la app gratis: CMYK de referencia ISO/Fogra, blanco, barniz, tintas técnicas y tintas creadas por el
      usuario con su Lab.

### 13.5 Versionado
- Cada etapa terminada → versión `3.0.0-sN` en `pyproject.toml` y una etiqueta git `v3.0.0-sN`.
  Al terminar S8 → `3.0.0`.

---

## 14. Orden, dependencias y entregables

| Etapa | Depende de | Entregable verificable |
|---|---|---|
| S0 Refactor | — | Misma app, estructura nueva, tests y banco v2 en verde |
| S1 Núcleo | S0 | `core/` probado, bibliotecas de tintas, Ghostscript detectado |
| S2 Separar PDF | S1 | Placas, TAC, densitómetro, chequeos, edición de tintas, exportación |
| S3 Separar imagen | S1 (S2 para el visor de placas) | 4 modos, base blanca, tramado, banco de separación |
| S4 Vectorizador v1 | S3 (cuantización) | Vectores sin huecos con tintas + banco vs VTracer/Potrace |
| S5 Vectorizador v2 | S4 | Primitivas, simetría, texto; comparación con Image Trace/PowerTRACE |
| S6 Preflight + códigos | S2 | Perfiles, reglas, correcciones seguras, generador y verificador |
| S7 Herramientas | S2, S3 | Trapping, step & repeat, distorsión, braille, gama extendida, soft proof |
| S8 Automatización | S2–S7 | Recetas, carpetas vigiladas, lotes |

### Definición de "terminado" (para cada etapa)
1. Todas las casillas de la etapa marcadas.
2. `uv run pytest` en verde; bancos de pruebas sin regresiones (≤ tolerancia).
3. CI en verde (si el usuario hizo push).
4. Prueba manual en el navegador con los archivos sintéticos de la etapa (describir en el commit qué se probó).
5. `CHANGELOG.md`, manual y `DECISIONES.md` actualizados.
6. Commit `S<n>: …` + etiqueta de versión.

---

## 15. Tareas para el usuario (el agente no puede hacerlas)

- [ ] Instalar Ghostscript en los equipos con el comando del README (instalador oficial firmado de Artifex; no está en winget).
- [ ] Aportar sus **bibliotecas de tintas** (exportadas de su software con licencia, en CxF/ASE/CSV) y los Lab de sus
      prendas o sustratos.
- [ ] Aportar **10–20 imágenes reales** para el banco del vectorizador (`datos_locales/vector_bench/reales/`) y generar las
      versiones de **Illustrator Image Trace** y **CorelDRAW PowerTRACE** siguiendo la guía del manual.
- [ ] Aportar 5–10 PDF reales de trabajos con tintas directas para validar el separador (`datos_locales/casos_separacion/`).
- [ ] Si quiere calibración (S3.6): imprimir el gráfico de prueba y medir con su espectrofotómetro.
- [ ] Revisar y aprobar cada etapa en el navegador antes de pasar a la siguiente.
