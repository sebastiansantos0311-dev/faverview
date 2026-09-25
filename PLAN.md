> **Continuación:** las mejoras de la versión 2 están en [PLAN_V2.md](PLAN_V2.md).

# FAVERVIEW – Plan de implementación (para agente ejecutor)

> **Instrucciones para el agente:** este documento es la especificación completa.
> Ejecútalo fase por fase, en orden. Marca cada casilla `[x]` al terminar.
> No agregues servicios en la nube, IA ni APIs de pago. Todo debe correr **local en Windows** y verse en el **navegador**.
> Idioma de la interfaz y de los mensajes: **español**.

---

## 0. Resumen del producto

Aplicación web local que compara:
- **A = Arte del cliente:** JPG, JPEG, PNG, WEBP, BMP, TIFF o PDF
- **B = Mi diseño:** PDF exportado

Y muestra:
1. Las dos imágenes **lado a lado**, un modo **superpuesto con deslizador** y un modo **"diferencia"**
2. **Recuadros** sobre las zonas con diferencias, con color según la categoría:
   - 🔴 Texto (palabra faltante, sobrante o cambiada)
   - 🟡 Ortografía
   - 🟠 Color
   - 🔵 Elemento visual faltante o movido (logo, imagen, forma)
   - 🟣 Fuente (tamaño o estilo distinto)
3. **% de similitud** total y % por categoría
4. Una **lista de errores** clicable (al hacer clic se hace zoom a la zona)
5. Un **reporte PDF** descargable

**Restricciones:**
- 100% local y offline después de la instalación
- 100% gratuito y open source
- Sin IA generativa ni APIs externas
- **Sin `.exe`, `.bat` ni `.ps1` propios** (los antivirus los marcan). La distribución es: **GitHub + winget + uv**.
  Instalación: `winget install astral-sh.uv Git.Git UB-Mannheim.TesseractOCR` → `git clone` → `uv run faverview`.

---

## 1. Stack tecnológico (todo gratis)

| Función | Tecnología | Paquete pip / instalador | Licencia |
|---|---|---|---|
| Lenguaje | Python **3.11** (lo descarga `uv` según `.python-version`) | winget `astral-sh.uv` | PSF |
| Gestor de entorno y arranque | uv (Astral) | winget `astral-sh.uv` | MIT/Apache |
| Distribución | Git + GitHub | winget `Git.Git` | GPL / gratis |
| Servidor web | FastAPI + Uvicorn | `fastapi`, `uvicorn[standard]`, `python-multipart` | MIT/BSD |
| Leer y renderizar PDF (texto, fuentes, colores, posiciones) | PyMuPDF | `pymupdf` | AGPL (uso propio OK) |
| Imágenes | Pillow | `pillow` | HPND |
| Procesamiento de imagen, alineación, contornos | OpenCV | `opencv-python-headless` | Apache 2.0 |
| SSIM, espacio LAB, Delta E | scikit-image | `scikit-image` | BSD |
| Cálculo numérico | NumPy | `numpy` | BSD |
| OCR (texto en imágenes) | Tesseract 5 + idioma español | winget `UB-Mannheim.TesseractOCR` + `spa.traineddata`; pip `pytesseract` | Apache 2.0 |
| Comparar textos | difflib (incluido) + RapidFuzz | `rapidfuzz` | MIT |
| Ortografía (sin Java) | pyspellchecker con diccionario español | `pyspellchecker` | MIT |
| Hash perceptual (logos/imágenes) | imagehash | `imagehash` | BSD |
| Reporte PDF | PyMuPDF | (ya incluido) | AGPL |
| Frontend | HTML + CSS + JavaScript puro (sin frameworks ni build) | — | — |

**Decisiones tomadas para facilitar la instalación:**
- **No usar LanguageTool**, porque requiere Java. Se usa `pyspellchecker` (Python puro).
- **No usar Node.js**: el frontend son archivos estáticos que sirve FastAPI.
- **Tesseract:** se instala con winget. El idioma español (`spa.traineddata`) se guarda **dentro del proyecto** en `tools/tessdata/`, para no depender de lo que traiga el instalador.
- `opencv-python-headless` evita dependencias gráficas innecesarias.

---

## 2. Estructura del proyecto

```
FAVERVIEW/
├── PLAN.md
├── README.md                 # guía paso a paso para el usuario final
├── PUBLICAR_EN_GITHUB.md     # guía para el dueño: subir el repo
├── pyproject.toml            # dependencias + comando `faverview`
├── uv.lock                   # versiones exactas (lo genera uv)
├── .python-version           # versión de Python que usa uv
├── .gitignore
├── config.json               # tolerancias y rutas (editable)
├── app/
│   ├── __init__.py
│   ├── launcher.py           # `uv run faverview`: puerto libre, abre navegador, --acceso-directo
│   ├── main.py               # FastAPI: rutas y servidor de archivos estáticos
│   ├── config.py             # carga config.json y ubica Tesseract
│   ├── loaders.py            # PDF/imagen -> imagen RGB normalizada + texto del PDF
│   ├── align.py              # alineación ORB + homografía
│   ├── compare_visual.py     # diferencia absoluta + SSIM + contornos
│   ├── compare_text.py       # OCR + diff de palabras
│   ├── spelling.py           # ortografía
│   ├── compare_color.py      # Delta E por región
│   ├── fonts.py              # fuentes del PDF + estimación en la imagen
│   ├── scoring.py            # porcentajes por categoría y total
│   ├── report.py             # generación del reporte PDF
│   └── models.py             # esquemas Pydantic (Difference, Result)
├── web/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── data/
│   ├── uploads/              # entradas (se limpian al iniciar)
│   └── results/              # imágenes resultado y reportes por id de trabajo
├── tools/
│   └── tessdata/             # spa.traineddata, eng.traineddata, osd.traineddata
├── samples/                  # archivos de prueba (cliente/diseño)
└── tests/
    ├── test_loaders.py
    ├── test_visual.py
    ├── test_text.py
    └── test_color.py
```

---

## 3. Fase 0 – Distribución y arranque (GitHub + winget + uv)

> Decisión: **no** se distribuyen `.exe`, `.bat` ni `.ps1` propios, porque Windows SmartScreen y los antivirus los
> marcan como sospechosos. Todo lo que se instala viene de **winget** (paquetes oficiales firmados) y el código
> se descarga de **GitHub**. Los scripts antiguos están en `_antiguo/` (excluido de git).

### 3.1 `pyproject.toml`
- Contiene las dependencias de la app (las antiguas de `requirements.txt`) y un grupo `dev` con `pytest` y `httpx`.
- Define el comando `faverview = "app.launcher:main"`.
- Build con `hatchling`, paquete `app`.
- `.python-version` = `3.11`: `uv` descarga esa versión de Python si el equipo no la tiene.
- `uv.lock` se versiona en git para que todos los equipos usen exactamente las mismas versiones.

### 3.2 `app/launcher.py`
- `uv run faverview`:
  - avisa si falta Tesseract (con el comando winget para instalarlo),
  - busca un puerto libre desde el 8000,
  - abre el navegador,
  - arranca uvicorn en `127.0.0.1`.
- `uv run faverview --acceso-directo` crea `FAVERVIEW.lnk` en el Escritorio, apuntando a `uv run faverview` en la carpeta del proyecto.

### 3.3 Tesseract e idiomas
- Tesseract se instala con `winget install UB-Mannheim.TesseractOCR`. `app/config.py` lo busca en el PATH y en las rutas típicas.
- `tools/tessdata/*.traineddata` (spa, eng, osd; unos 38 MB) **se versionan en git**, así que no hay descargas extra.
- `config.json` se deja con `"tesseract_cmd": ""` (la ruta se detecta en cada equipo).

### 3.4 `.gitignore`
Excluye `.venv/`, `build/`, `dist/`, `_antiguo/`, `data/uploads/`, `data/results/`, `data/historial.json` y `data/diccionario_personal.txt`.

### Checklist Fase 0
- [x] `pyproject.toml` + `.python-version` + `uv.lock`
- [x] `app/launcher.py` con `--acceso-directo`
- [x] `.gitignore` y el repositorio git local con el primer commit
- [x] `README.md` con la guía paso a paso y `PUBLICAR_EN_GITHUB.md`
- [x] Verificado: `uv sync`, `uv run pytest` (13 pruebas) y `uv run faverview` responde HTTP 200
- [x] Publicado en https://github.com/sebastiansantos0311-dev/faverview (público, AGPL-3.0)
- [ ] Probar en un equipo limpio siguiendo el `README.md`

---

## 4. Fase 1 – Carga, alineación y diferencia visual

### 4.1 `loaders.py`
- `load_as_image(path, dpi) -> np.ndarray (RGB)`
  - PDF: renderizar la página 1 con PyMuPDF (`page.get_pixmap(dpi=dpi)`). El soporte multipágina llega en la Fase 4.
  - Imagen: abrir con Pillow, aplicar `ImageOps.exif_transpose`, convertir a RGB y aplanar la transparencia sobre fondo blanco.
- `extract_pdf_layout(path, dpi) -> list[TextSpan]`
  - Usar `page.get_text("dict")` y recorrer bloques → líneas → spans.
  - Por cada span guardar: `text`, `bbox` (escalado a píxeles con `dpi/72`), `font`, `size`, `color` (entero → RGB hex) y `flags` (negrita/cursiva).
- Validar la extensión y el tamaño máximo. Si el archivo no es válido, devolver un error en español.

### 4.2 `align.py`
- Entrada: `design_img` (B, referencia) y `client_img` (A).
- Pasos:
  1. Escalar A para que su ancho sea igual al de B, manteniendo la proporción.
  2. Convertir ambas a escala de grises y detectar puntos con **ORB** (`nfeatures=5000`).
  3. Emparejar con `BFMatcher(NORM_HAMMING)` + ratio test de Lowe (0.75).
  4. Si hay ≥ 15 coincidencias: `findHomography(RANSAC, 5.0)` y luego `warpPerspective` de A al tamaño de B, con relleno blanco.
  5. Si falla: usar solo el redimensionado de A al tamaño de B y devolver `aligned=False` para mostrar una advertencia en la UI.
- Devolver: `aligned_client`, `homography` (o `None`) y `alignment_quality` (proporción de inliers).

### 4.3 `compare_visual.py`
1. Aplicar un desenfoque gaussiano leve (3×3) a ambas imágenes para reducir el ruido de compresión JPG.
2. Calcular **SSIM** en gris con `skimage.metrics.structural_similarity(full=True)` → `score` y `diff_map`.
3. Calcular la diferencia absoluta por píxel (`cv2.absdiff`) y umbralizar con `pixel_diff_threshold`.
4. Combinar: una zona es diferente si `diff_map < ssim_threshold` **o** si supera el umbral de píxeles.
5. Aplicar morfología (dilatar y cerrar) para unir zonas cercanas y luego `findContours`.
6. Descartar áreas menores a `min_region_area`. Cada contorno se convierte en una `Difference(category="visual", bbox, severity)`.
7. Generar las imágenes de salida en `data/results/<job_id>/`:
   - `design.png`, `client_aligned.png`
   - `diff_heatmap.png` (mapa de calor de la diferencia)
   - `overlay.png` (mezcla al 50%)

### 4.4 API mínima
- `POST /api/compare` (multipart: `client_file`, `design_file`) → `{ job_id, result }`
- `GET /api/results/{job_id}/{archivo}` → sirve las imágenes
- `GET /` → sirve `web/index.html`
- El procesamiento es síncrono; está bien para archivos de ≤ 50 MB en local.

### 4.5 UI mínima (`web/`)
- Dos zonas de "arrastrar y soltar" (Cliente / Mi diseño) y el botón **Comparar**.
- Indicador de "Procesando…".
- Visor con pestañas: **Lado a lado** | **Deslizador** | **Diferencia** | **Superpuesto**.
- Recuadros dibujados con un `<canvas>` o con `<div>` posicionados en absoluto, en coordenadas relativas a la imagen para que se escalen con el zoom.
- Zoom con la rueda del ratón y paneo arrastrando; ambos lados se mueven sincronizados.

### Checklist Fase 1
- [x] loaders (PDF + imágenes + transparencia + EXIF)
- [x] alineación con fallback y advertencia
- [x] SSIM + contornos + imágenes de salida
- [x] endpoint `/api/compare`
- [x] UI con 4 modos de vista, recuadros y % de similitud visual
- [x] tests `test_loaders.py` y `test_visual.py`: una imagen idéntica da ≥ 99%; una imagen con un rectángulo agregado detecta 1 región

---

## 5. Fase 2 – Texto y ortografía

### 5.1 `compare_text.py`
1. **Texto del diseño:** tomarlo de `extract_pdf_layout` (es exacto y no necesita OCR).
   - Si el PDF del diseño no tiene texto (texto convertido a curvas), hacer OCR también sobre B y avisarlo en la UI.
2. **Texto del cliente:** OCR con `pytesseract.image_to_data(aligned_client, lang=cfg.ocr_lang, config="--oem 1 --psm 11", output_type=DICT)`.
   - Preprocesado: escala de grises, reescalar ×2 si la imagen tiene menos de 1500 px de ancho, y umbral Otsu.
   - Descartar palabras con confianza < 50.
3. **Normalización** para comparar: pasar a minúsculas solo para el emparejamiento (conservando el original para reportar mayúsculas), unificar comillas y guiones, y colapsar espacios.
4. **Emparejamiento por posición y contenido:**
   - Como las imágenes ya están alineadas, emparejar cada palabra de B con la palabra de A cuyo bbox tenga mayor IoU y, en caso de empate, mayor `rapidfuzz.fuzz.ratio`.
   - Además, aplicar `difflib.SequenceMatcher` sobre las secuencias de palabras por línea para detectar operaciones `insert`, `delete` y `replace`.
5. Generar una `Difference(category="text")` con `subtype` de uno de estos tipos:
   - `faltante`: está en el diseño y no en el cliente, o al revés
   - `cambiada`: por ejemplo, "Precio $10.000" → "Precio $12.000"
   - `mayusculas`: cambia solo el uso de mayúsculas
   - `puntuacion`: cambia solo la puntuación
   - Incluir `expected` (texto del cliente), `found` (texto del diseño) y `bbox`.

> Nota: el arte del **cliente** es la referencia de lo que *debería* decir; el **diseño** es lo que hay que corregir. Mostrar siempre "Cliente dice: X · Tu diseño dice: Y".

### 5.2 `spelling.py`
- `SpellChecker(language="es")`, más un **diccionario personalizado** en `data/diccionario_personal.txt` (marcas, nombres o términos del cliente) que el usuario puede ampliar desde la UI con el botón "Agregar al diccionario".
- Revisar las palabras del **diseño** (y opcionalmente las del cliente).
- Ignorar números, correos, URLs, palabras de ≤ 2 letras y palabras en MAYÚSCULAS de ≤ 4 letras (siglas).
- Generar `Difference(category="spelling", word, suggestions[:3], bbox)`.

### 5.3 UI
- Panel lateral **Lista de errores**, agrupado por categoría, con un contador en cada grupo.
- Al hacer clic en un error: centrar y hacer zoom en el bbox de ambos lados, y resaltar el recuadro con un parpadeo.
- Filtros por categoría (casillas de verificación).
- Botón "Ignorar" en cada error (solo afecta a la sesión actual).

### Checklist Fase 2
- [x] extracción de texto del PDF con posiciones
- [x] OCR con preprocesado y filtrado por confianza
- [x] emparejamiento y diff por palabra
- [x] ortografía + diccionario personal
- [x] lista de errores clicable con filtros
- [x] `test_text.py`: un PDF con "Precio 10.000" contra una imagen con "Precio 12.000" detecta 1 `cambiada`

---

## 6. Fase 3 – Colores, fuentes, puntuación y reporte

### 6.1 `compare_color.py`
- Convertir ambas imágenes a **LAB** (`skimage.color.rgb2lab`).
- **Por región:**
  - Regiones de texto: usar el color exacto del span del PDF contra el color mediano de los píxeles de tinta en A (píxeles más oscuros que el fondo local dentro del bbox).
  - Resto de la imagen: dividir en una rejilla de 32×32 px y comparar el color mediano de cada celda.
- Calcular **Delta E (CIEDE2000)** con `skimage.color.deltaE_ciede2000`.
- Si `ΔE > delta_e_tolerance`, crear `Difference(category="color", expected_hex, found_hex, delta_e, bbox)`. Unir celdas vecinas con el mismo problema en un solo recuadro.
- En la UI, mostrar dos muestras de color con el HEX al lado de cada error.

### 6.2 `fonts.py`
- **Diseño:** la fuente real sale de PyMuPDF (`font`, `size`, `flags`), así que es exacta.
- **Cliente (estimación):**
  - Tamaño: alto del bbox de OCR en la línea, comparado con el alto esperado a partir del `size` del PDF.
  - Grosor: proporción de píxeles de tinta y ancho medio del trazo (transformada de distancia), para estimar negrita o normal.
  - Cursiva: inclinación media de los bordes verticales.
- Si la diferencia de tamaño supera `font_size_tolerance_pct` o cambian el grosor o la cursiva, crear `Difference(category="font", detail="Tamaño aprox. 14pt vs 18pt en diseño")`.
- La UI debe decir "**posible** diferencia de fuente": nunca afirmar la fuente exacta del cliente.
- En la UI, listar todas las fuentes usadas en el PDF del diseño (útil para verificar que la tipografía es la correcta).

### 6.3 `scoring.py`
- **% similitud visual** = SSIM × 100
- **% texto** = palabras coincidentes / total de palabras × 100
- **% color** = área sin errores de color / área total × 100
- **% ortografía** = palabras correctas / total × 100
- **% fuente** = spans sin diferencia / total de spans × 100
- **Total** = promedio ponderado (visual 0.30, texto 0.35, color 0.15, ortografía 0.10, fuente 0.10), con los pesos definidos en `config.json`.
- Mostrar tanto **% de similitud** como **% de diferencia** (100 − similitud).
- Semáforo: ≥ 98% verde "Aprobado", 90–98% amarillo "Revisar", < 90% rojo "Con errores".

### 6.4 `report.py`
- `GET /api/report/{job_id}` → PDF generado con PyMuPDF que contiene:
  - Portada: fecha, nombres de archivo, % total, semáforo y % por categoría.
  - Página con las dos imágenes lado a lado con los recuadros dibujados.
  - Tabla de errores: número, categoría, "Cliente dice", "Diseño dice" y una miniatura recortada de la zona.

### 6.5 Ajustes en la UI
- Panel "Sensibilidad" con deslizadores para `ssim_threshold`, `delta_e_tolerance` y `min_region_area`, y el botón "Recalcular" (vuelve a llamar a la API con esos parámetros).
- Botón **Descargar reporte PDF**.

### Checklist Fase 3
- [x] Delta E por texto y por rejilla
- [x] estimación de fuente + lista de fuentes del PDF
- [x] puntuación ponderada + semáforo
- [x] reporte PDF
- [x] controles de sensibilidad
- [x] `test_color.py`: un rojo #FF0000 contra #CC0000 se detecta; #FF0000 contra #FE0101 no

---

## 7. Fase 4 – Extras

- [x] **Multipágina:** selector de página cuando algún archivo es PDF de varias páginas, emparejando las páginas por orden.
- [x] **Historial:** `data/historial.json` con las últimas 50 comparaciones (fecha, archivos, %, enlace al resultado).
- [x] **Limpieza:** al iniciar, borrar `data/uploads/` y los resultados de más de 30 días.
- [x] **Detección de logos/imágenes:** con `imagehash.phash` por región para decir "logo cambiado" en vez de "diferencia visual".
- [ ] ~~**Versión portable:**~~ descartada (un .exe sin firma genera falsos positivos). Empaquetar con PyInstaller (`--onedir`) incluyendo `web/` y `tools/tessdata/`, más el ejecutable de Tesseract copiado a `tools/tesseract/`, para correr sin instalar nada.

---

## 8. Modelo de datos (`models.py`)

```python
class Difference(BaseModel):
    id: int
    category: Literal["visual", "text", "spelling", "color", "font"]
    subtype: str | None = None
    bbox: tuple[int, int, int, int]      # x, y, w, h en píxeles del diseño
    severity: Literal["alta", "media", "baja"]
    message: str                          # texto en español para la UI
    expected: str | None = None           # lo que dice/tiene el cliente
    found: str | None = None              # lo que dice/tiene el diseño
    suggestions: list[str] = []
    expected_hex: str | None = None
    found_hex: str | None = None
    delta_e: float | None = None

class Result(BaseModel):
    job_id: str
    width: int
    height: int
    aligned: bool
    alignment_quality: float
    scores: dict[str, float]              # visual, text, color, spelling, font, total
    status: Literal["aprobado", "revisar", "con_errores"]
    differences: list[Difference]
    fonts_in_design: list[dict]
    images: dict[str, str]                # rutas a design.png, client_aligned.png, etc.
    warnings: list[str]
```

---

## 9. Instalación en otro equipo

Ver **`README.md`** (guía paso a paso para el usuario). Resumen:
```
winget install -e --id astral-sh.uv; winget install -e --id Git.Git; winget install -e --id UB-Mannheim.TesseractOCR
# cerrar y reabrir PowerShell
git clone https://github.com/sebastiansantos0311-dev/faverview.git $HOME\FAVERVIEW
cd $HOME\FAVERVIEW; uv run faverview
uv run faverview --acceso-directo   # opcional
```
Actualizar: `git pull`.

**Futuro (opcional, de pago):** instalador con Inno Setup firmado con Azure Trusted Signing o un certificado
OV/EV, o un MSIX en Microsoft Store. Ver `PUBLICAR_EN_GITHUB.md`.

---

## 10. Criterios de aceptación finales

- [ ] En un equipo limpio con Windows, los pasos del `README.md` (winget → git clone → `uv run faverview`) funcionan sin avisos de antivirus.
- [x] Funciona sin internet después de instalar.
- [x] Acepta JPG, PNG, WEBP, BMP, TIFF y PDF del cliente, y PDF del diseño.
- [x] Un diseño idéntico al del cliente da ≥ 98% y queda "Aprobado".
- [x] Detecta: una palabra cambiada, una palabra faltante, una falta de ortografía, un color cambiado (ΔE > 10), un logo removido y un tamaño de fuente distinto (> 12%).
- [x] Cada error aparece con un recuadro en ambas imágenes y en la lista; al hacer clic, se hace zoom en la zona.
- [x] Muestra el % total, el % por categoría y el semáforo.
- [x] El reporte PDF se descarga correctamente.
- [x] Una comparación de 1 página a 200 dpi tarda < 20 s en un PC común.
- [x] Todos los mensajes están en español.
- [x] `pytest` pasa.

---

## 11. Datos de prueba

El agente debe generar datos sintéticos en `samples/` con un script `tests/make_samples.py`:
- `diseno.pdf`: creado con PyMuPDF, con un título, un precio, un párrafo, un rectángulo de color y un "logo" (círculo).
- `cliente_ok.png`: el mismo PDF renderizado, con compresión JPG al 85%.
- `cliente_errores.png`: una copia con un precio distinto, una palabra quitada, un color de rectángulo cambiado, el logo removido y una rotación de 2°.

Si el usuario coloca archivos reales en `samples/`, usarlos también para validar.
