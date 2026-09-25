# FAVERVIEW v2 – Plan de mejoras (para agente ejecutor)

> **Instrucciones para el agente**
> - Este plan continúa `PLAN.md` (v1, ya implementada y publicada). Léelo primero junto con `README.md`.
> - Ejecuta las fases **en orden**. Marca `[x]` al terminar cada casilla y ejecuta `uv run pytest` tras cada fase.
> - Reglas que no cambian: 100% local, gratis, sin APIs ni IA en la nube, interfaz en **español**,
>   sin `.exe`/`.bat`/`.ps1` propios, distribución con GitHub + winget + uv.
> - **Privacidad:** los archivos reales de clientes y todo lo aprendido de ellos viven en `datos_locales/`, que
>   **nunca** se sube a git. Verifica `.gitignore` antes de cada commit.
> - Cada cambio de precisión se valida con el banco de pruebas (Fase 5). **No se acepta una mejora que empeore las métricas.**
> - Haz commits pequeños por fase: `git commit -m "Fase N: …"`.

---

## 0. Objetivos de la v2

1. **Medir** la precisión con **20 casos reales** + casos sintéticos → saber qué falla, con números.
2. **Precisión:** OCR guiado, menos falsos positivos, alineación robusta, colores CMYK correctos, ortografía con tildes.
3. **OCR que aprende** poco a poco con cada caso revisado (Fase 7).
4. **Flujo de trabajo:** zonas a ignorar, pegar con Ctrl+V, comparar versiones, lotes de páginas, checklist.
5. **Mantenimiento:** pruebas automáticas en GitHub y aviso de actualización.

### Metas de aceptación (medidas sobre los 20 casos reales)
| Métrica | Meta |
|---|---|
| Recall de errores de **texto** (errores reales encontrados / errores reales) | ≥ 95% |
| Precisión de **texto** (marcas correctas / marcas totales) | ≥ 90% |
| Recall de **color / elemento visual** | ≥ 90% |
| **Falsos positivos** promedio por caso (todas las categorías) | ≤ 1 |
| **CER** del OCR (tasa de error por carácter) en zonas de texto | ≤ 3% |
| Casos idénticos → "Aprobado" | 100% |
| Tiempo por página (200 dpi, PC común) | ≤ 15 s |

---

## 1. Problemas conocidos de la v1 (corregir en Fase 6)

- [x] **Falso positivo de fuente:** en `samples/cliente_errores.png` se reporta "tamaño aprox. 42pt vs 34pt" sin
      que haya cambio de fuente. Causa probable: `fonts.compare_fonts` estima el tamaño sobre palabras ya marcadas
      como cambiadas (el precio), o sobre una línea con una palabra de menos.
      _Nota de la implementación: el cambio de 34→42 pt en esa muestra era REAL (la muestra lo incluía a propósito);
      se regeneró `samples/cliente_errores.png` sin ese cambio y la prueba de regresión pasó a comprobar 0 diferencias
      de fuente, más otra prueba que sí exige detectar un cambio de tamaño real._
- [x] **OCR con umbral global (Otsu)** en `compare_text.ocr_words`: falla con fondos de color, degradados y
      texto claro sobre fondo oscuro en solo una parte de la imagen.
- [x] **Mensaje obsoleto:** `compare_text.py` dice "Ejecuta instalar.bat". Debe decir
      "Instálalo con: winget install UB-Mannheim.TesseractOCR".
- [x] El OCR lee toda la página con `--psm 11` sin aprovechar que el PDF del diseño dice dónde está cada texto.

---

## 2. Nuevas carpetas y archivos

```
FAVERVIEW/
├── PLAN_V2.md
├── bench/                         # banco de pruebas (sí va a git)
│   ├── __init__.py
│   ├── run.py                     # `uv run python -m bench.run`
│   ├── metrics.py                 # emparejar detectado vs esperado, precisión/recall/CER
│   ├── report.py                  # genera bench_report.md + .html
│   └── synth.py                   # generador de casos sintéticos con errores conocidos
├── tests/sinteticos/              # casos sintéticos generados (sí va a git, son inventados)
├── app/
│   ├── ocr_guided.py              # OCR por zona guiado por el PDF
│   ├── color_mgmt.py              # CMYK/ICC → sRGB
│   ├── learning/                  # aprendizaje del OCR (Fase 7)
│   │   ├── __init__.py
│   │   ├── store.py               # lee/escribe datos_locales/aprendizaje/
│   │   ├── vocab.py               # nivel 1: vocabulario y patrones
│   │   ├── confusions.py          # nivel 2: confusiones aprendidas
│   │   ├── tuning.py              # nivel 3: auto-ajuste del preprocesado
│   │   └── finetune.py            # nivel 4: re-entrenamiento de Tesseract (opcional)
│   ├── ignore_zones.py            # zonas a ignorar y plantillas por cliente
│   └── updates.py                 # aviso de nueva versión
├── tools/hunspell/                # es_ES.dic/.aff (+ es_CO, es_MX opcional) de LibreOffice
├── .github/workflows/tests.yml    # CI
└── datos_locales/                 # NUNCA a git (añadir a .gitignore)
    ├── casos/                     # los 20+ casos reales
    │   └── caso_001/
    │       ├── cliente.<ext>
    │       ├── diseno.pdf
    │       └── esperado.json      # errores reales anotados (verdad de referencia)
    ├── aprendizaje/
    │   ├── vocabulario.txt
    │   ├── patrones.txt
    │   ├── confusiones.json
    │   ├── ajustes_ocr.json
    │   ├── lineas/                # recortes + texto correcto para el nivel 4
    │   └── modelos/               # spa_fv.traineddata (si se entrena)
    ├── plantillas/                # zonas a ignorar por cliente
    └── bench_resultados/          # reportes históricos del banco de pruebas
```

`.gitignore` → agregar `datos_locales/`.

---

## 3. Fase 5 – Banco de pruebas (20 casos reales + sintéticos)

**Hacer primero.** Sin medición no se puede saber si una mejora ayuda.

### 3.1 Los 20 casos reales
El usuario reúne los archivos. El agente prepara la herramienta y la guía. La mezcla recomendada cubre lo que
llega en la vida real:

| # | Tipo de arte del cliente | Casos |
|---|---|---|
| 1 | PNG/JPG exportado limpio (sin errores) | 3 |
| 2 | PNG/JPG exportado con errores de texto (precio, fecha, nombre, teléfono) | 3 |
| 3 | Captura de **WhatsApp** (comprimida) | 3 |
| 4 | **Foto** con celular de pantalla o impreso (torcida, con luz) | 3 |
| 5 | **Escaneo** | 2 |
| 6 | PDF del cliente en **CMYK** | 2 |
| 7 | Texto pequeño / fondo de color / texto claro sobre oscuro | 2 |
| 8 | PDF de **varias páginas** | 1 |
| 9 | Diseño con **texto convertido a curvas** | 1 |
| | **Total** | **20** |

Cada caso real debe tener entre 0 y 8 errores conocidos, idealmente de categorías variadas.

### 3.2 Formato `esperado.json`
```json
{
  "caso": "caso_007",
  "tipo": "whatsapp",
  "cliente": "cliente.jpg",
  "diseno": "diseno.pdf",
  "pagina_cliente": 1,
  "pagina_diseno": 1,
  "errores": [
    {"categoria": "text", "subtipo": "cambiada", "bbox": [812, 440, 210, 60],
     "cliente_dice": "$12.000", "diseno_dice": "$10.000"},
    {"categoria": "spelling", "bbox": [300, 900, 180, 40], "diseno_dice": "informacion"},
    {"categoria": "color", "bbox": [0, 0, 1654, 200]},
    {"categoria": "visual", "subtipo": "elemento_faltante", "bbox": [1400, 60, 180, 180]}
  ],
  "texto_cliente": "opcional: transcripción exacta del texto del cliente, para medir CER",
  "notas": ""
}
```
- `bbox` en píxeles del **diseño renderizado** (200 dpi): `[x, y, ancho, alto]`.

### 3.3 Modo "Revisión" en la UI (para anotar sin escribir JSON)
Botón **"Guardar como caso de prueba"** en la pantalla de resultados:
- [x] Cada error detectado muestra ✔ **Real** / ✘ **Falso positivo**.
- [x] Herramienta **"Marcar error no detectado"**: dibujar un rectángulo, elegir la categoría y escribir el texto
      correcto si aplica.
- [x] Campo opcional "Texto del cliente" para medir el CER.
- [x] Al guardar, se crea `datos_locales/casos/caso_NNN/` con los dos archivos y `esperado.json`
      (= errores ✔ + errores marcados a mano).
- [x] Esta misma revisión alimenta el aprendizaje (Fase 7). Es el ciclo central: **comparar → revisar → aprende**.

### 3.4 Casos sintéticos (`bench/synth.py`)
- [x] Generar **≥ 60 casos** reproducibles (semilla fija) a partir de 6 diseños PDF sintéticos con fuentes libres:
      fondos de color, texto pequeño (7–9 pt), texto blanco sobre oscuro, tablas de precios y logos.
- [x] Errores inyectados con verdad conocida: número cambiado, palabra quitada o agregada, tilde quitada, color
      ΔE 5–40, logo removido o movido, tamaño de fuente ±20%, negrita.
- [x] Degradaciones: JPEG calidad 40–90, rotación ±5°, perspectiva, desenfoque, ruido, iluminación irregular,
      recorte de bordes, escala 50–150%, conversión CMYK y un "marco" de captura de pantalla.
- [x] Guardar en `tests/sinteticos/` con el mismo formato `esperado.json`.

### 3.5 `bench/metrics.py` y `bench/run.py`
- Emparejamiento detectado ↔ esperado: misma categoría y **IoU ≥ 0.3** (o el centro del esperado dentro del
  detectado). Emparejamiento húngaro (`scipy.optimize.linear_sum_assignment`) o greedy por IoU.
- Por categoría: TP, FP, FN, **precisión**, **recall** y **F1**.
- **CER** con distancia de Levenshtein (`rapidfuzz.distance.Levenshtein`) cuando hay `texto_cliente`.
- Tiempo por caso y por etapa (cargar, alinear, OCR, color, fuentes).
- Comando: `uv run python -m bench.run [--real] [--sinteticos] [--caso caso_007] [--etiqueta "antes de F6"]`
- Salida: `datos_locales/bench_resultados/<fecha>_<etiqueta>.md` + `.json`, con una tabla comparativa contra
  la corrida anterior (↑ mejoró / ↓ empeoró en cada métrica) y la lista de FP/FN de cada caso con miniaturas.

### Checklist Fase 5
- [x] `datos_locales/` en `.gitignore`
- [x] Modo Revisión + "Guardar como caso de prueba"
- [x] `bench/` (synth, metrics, run, report)
- [x] ≥ 60 casos sintéticos en `tests/sinteticos/`
- [x] **Guía para el usuario** en `README.md` → sección "Cómo crear casos de prueba"
- [ ] El usuario carga los **20 casos reales** (tarea del usuario; el agente espera o sigue con los sintéticos)
- [x] **Línea base:** `bench.run --etiqueta "v1 linea base"` sobre sintéticos + reales, guardada

---

## 4. Fase 6 – Precisión

Tras **cada** punto: correr el banco de pruebas y comparar con la corrida anterior. Si una métrica empeora,
ajustar o revertir.

### 6.1 OCR guiado por el PDF (`app/ocr_guided.py`)
1. Por cada **línea** del PDF del diseño (agrupar spans por `line` de PyMuPDF), tomar su bbox + 25% de margen
   (+ un margen extra proporcional a la calidad de alineación) y **recortar la imagen del cliente alineada**.
2. Preprocesar el recorte localmente:
   - reescalar para que la altura de las letras sea de unos 30–40 px,
   - convertir a gris con el canal de más contraste (no siempre la luminancia; probar L de LAB y el canal RGB
     de máximo contraste),
   - umbral **adaptativo** (Sauvola: `skimage.filters.threshold_sauvola`) o Otsu local,
   - invertir si el fondo es oscuro,
   - borde blanco de 10 px.
3. OCR del recorte con `--psm 7` (una línea). Si la confianza es < 60, reintentar con `--psm 6` y con otra
   variante de preprocesado, y quedarse con el mejor resultado (el de mayor confianza y mayor similitud con el
   texto esperado, **sin forzarlo**: la similitud solo desempata).
4. Comparar el texto leído con el texto del PDF de esa línea (diff por palabra, ya existe en `compare_words`).
5. **Texto extra del cliente:** además, OCR de página completa (`--psm 11`) **excluyendo** las zonas ya leídas,
   para detectar texto que el cliente tiene y el diseño no ("falta en tu diseño").
6. Si el diseño no tiene texto vectorial, mantener el camino actual (OCR de ambas imágenes a página completa).
- [x] Implementado y usado por defecto; el camino anterior queda como alternativa (`"ocr_mode": "guiado" | "pagina"`
      en `config.json`)
- [x] Mejora medida en CER y en recall/precisión de texto (sintéticos; los 20 casos reales cuando el usuario los cargue)

### 6.2 Falsos positivos de fuente (`fonts.py`)
- [x] No estimar la fuente en palabras marcadas como `cambiada`/`faltante`/`sobrante`.
- [x] Estimar el tamaño con la **altura x** (altura de minúsculas sin ascendentes/descendentes) o la altura de
      mayúsculas por línea, usando la mediana de ≥ 3 palabras. Si hay menos palabras, no concluir.
- [x] Normalizar por la escala de la homografía (si la imagen del cliente estaba escalada).
- [x] Solo reportar con una diferencia ≥ `font_size_tolerance_pct` **y** consistente en toda la línea.
- [x] Prueba de regresión: `samples/cliente_errores.png` → 0 diferencias de fuente.

### 6.3 Alineación robusta (`align.py`)
- [x] Intento 1: ORB (actual). Intento 2: **SIFT** (`cv2.SIFT_create`, libre desde OpenCV 4.4) si hay
      < 15 inliers o la calidad es < 0.3.
- [x] **Refinamiento ECC** (`cv2.findTransformECC`, `MOTION_HOMOGRAPHY`) partiendo de la homografía encontrada
      y a resolución reducida, para precisión sub-píxel.
- [x] Detectar el "marco" de capturas de pantalla (barras de WhatsApp o del navegador) y recortarlo antes de alinear.
- [x] Validar la homografía: rechazar si el determinante o la escala son absurdos (escala < 0.2 o > 5,
      perspectiva extrema).
- [x] Mostrar la calidad de alineación en la UI (buena / regular / mala) y un botón **"Alinear manualmente"**:
      el usuario marca 4 puntos equivalentes en cada imagen.

### 6.4 Colores CMYK y perfiles ICC (`app/color_mgmt.py`)
- [x] PDF (diseño y cliente): activar la gestión de color de PyMuPDF (`pymupdf.TOOLS.set_icc(True)`) antes de
      renderizar, para convertir CMYK → sRGB con el perfil del PDF.
- [x] Imágenes: si traen un perfil ICC incrustado (`img.info.get("icc_profile")`), convertir a sRGB con
      `PIL.ImageCms`. Si son CMYK sin perfil, usar un perfil CMYK por defecto configurable
      (`"cmyk_profile"` en `config.json`; si está vacío, usar la conversión estándar de Pillow y avisar en la UI).
- [x] Colores de texto del PDF: PyMuPDF entrega RGB; si el span original es CMYK, convertirlo igual que el render.
- [x] Mostrar en la UI el espacio de color de cada archivo ("Diseño: CMYK (FOGRA39) · Cliente: sRGB").
- [x] Caso sintético CMYK: 0 falsos positivos de color.

### 6.5 Ortografía con Hunspell (`spelling.py`)
- [x] Añadir `spylls` (Hunspell en Python puro, licencia MPL-2.0) a `pyproject.toml`.
- [x] Diccionarios `es_ES` (y `es_CO` / `es_MX` opcionales) de LibreOffice (github.com/LibreOffice/dictionaries,
      licencia LGPL/GPL/MPL) en `tools/hunspell/`. Idioma configurable: `"spell_lang": "es_CO"`.
- [x] Mantener el diccionario personal y la lista `palabras_es.txt` como complemento.
- [x] **Tildes:** si una palabra no existe pero su versión con tilde sí ("informacion" → "información"),
      subtipo `tilde_faltante` con severidad alta y una sugerencia única.
- [x] Ignorar marcas y nombres propios del vocabulario aprendido (Fase 7, nivel 1).
- [x] Comparar la velocidad: si Hunspell es lento, usar una caché LRU por palabra.

### 6.6 Otros
- [x] Corregir el mensaje obsoleto "Ejecuta instalar.bat".
- [x] Barra de progreso por etapas en la UI (endpoint de estado o Server-Sent Events).
- [x] Revisar que `_dedupe` no oculte errores reales al cambiar el OCR (validar con el banco).

### Checklist Fase 6
- [x] 6.1 · [ ] 6.2 · [ ] 6.3 · [ ] 6.4 · [ ] 6.5 · [ ] 6.6
- [x] Corrida `--etiqueta "F6 precision"` guardada y comparada con la línea base

---

## 5. Fase 7 – OCR que aprende con los ejemplos

**Idea central:** el PDF del diseño contiene el texto **correcto y exacto**. Cada vez que el usuario revisa un
resultado (✔ real / ✘ falso positivo, Fase 5.3), obtenemos ejemplos etiquetados **gratis**: el recorte de la imagen
del cliente + el texto que realmente dice. Con eso, el sistema mejora en 4 niveles, del más simple y seguro al más
potente. Todo es local y se guarda en `datos_locales/aprendizaje/`.

> ⚠️ **Regla de seguridad:** el aprendizaje nunca debe ocultar un error real. En concreto:
> - una sustitución **dígito ↔ dígito** (`10.000` → `12.000`) nunca se considera "error de lectura",
> - el aprendizaje solo **baja la severidad** o **reintenta el OCR**; no borra diferencias,
> - cualquier cambio de modelo o de ajustes se adopta solo si mejora el banco de pruebas.

### Nivel 1 – Vocabulario y patrones (inmediato)
- [ ] Cada caso revisado agrega las palabras del diseño confirmadas (marcas, nombres, productos, direcciones) a
      `vocabulario.txt`, con conteo de frecuencia.
- [ ] Se pasa a Tesseract como `--user-words` y `--user-patterns` (patrones: precios `\$\d+.\d\d\d`, teléfonos,
      fechas, porcentajes, correos). Usar `-c load_system_dawg=1` y `-c user_words_suffix` según haga falta.
- [ ] El corrector ortográfico no marca palabras del vocabulario aprendido.

### Nivel 2 – Confusiones aprendidas
- [ ] Cuando el usuario marca ✘ un error de texto (el OCR leyó mal), se guarda el par
      `(leído, correcto)` y se extraen las confusiones de caracteres (`rn→m`, `O→0`, `l→1`, `é→e`, `,→.`) con
      su contexto (fuente, tamaño y tipo de imagen). Guardar en `confusiones.json` con conteos.
- [ ] Al comparar: si la diferencia entre el texto leído y el esperado se explica **solo** por confusiones vistas
      ≥ 3 veces (y no incluye dígito↔dígito), entonces:
      1. reintentar el OCR de ese recorte con más escala u otro preprocesado,
      2. si persiste, reportar como **"posible error de lectura"** (severidad baja, categoría `text`,
         subtipo `ocr_dudoso`), no como error.
- [ ] Panel "Aprendizaje" en la UI: lista de confusiones aprendidas, con la opción de borrar una.

### Nivel 3 – Auto-ajuste del preprocesado por tipo de imagen
- [ ] Clasificar el arte del cliente con reglas simples (sin IA): `exportado`, `whatsapp` (JPEG con dimensiones
      típicas de WhatsApp y calidad baja), `foto` (EXIF de cámara, perspectiva, iluminación irregular), `escaneo`
      (EXIF de escáner o dpi 150–600 con fondo gris) y `captura` (marco de UI detectado).
- [ ] `uv run faverview-aprender --ajustar`: búsqueda en rejilla sobre los casos revisados de cada tipo, variando
      la escala objetivo, el tipo de umbral, el tamaño de la ventana Sauvola, el desenfoque previo, el psm y el
      margen del recorte. Elegir la combinación con el menor CER + mejor F1 de texto.
- [ ] Guardar en `ajustes_ocr.json` por tipo y usarlo automáticamente.
- [ ] Se ejecuta automáticamente cada 5 casos nuevos revisados (en segundo plano, con un aviso en la UI).

### Nivel 4 – Re-entrenamiento de Tesseract (opcional, con ≥ 300 líneas revisadas)
- [ ] Por cada línea con OCR confirmado o corregido, guardar en `aprendizaje/lineas/` el recorte `.png` + `.gt.txt`
      (texto correcto sacado del PDF). Solo de casos que el usuario revisó.
- [ ] `uv run faverview-aprender --entrenar`: *fine-tuning* del modelo `spa` (tessdata_best) con
      `lstmtraining` (herramientas de entrenamiento incluidas en el instalador UB-Mannheim de Tesseract;
      **verificar** que `lstmtraining.exe` y `combine_tessdata.exe` existen; si no, documentar la alternativa con
      WSL + tesstrain).
  - 90% entrenamiento / 10% validación, pocas iteraciones (≈ 400–1000) y tasa de aprendizaje baja para no
    "olvidar" el español general.
  - Resultado: `datos_locales/aprendizaje/modelos/spa_fv.traineddata`.
- [ ] **Prueba A/B** automática con el banco de pruebas: si el CER y el F1 de texto mejoran respecto al modelo
      base, se activa (`"ocr_lang": "spa_fv+spa+eng"`). Si no, se descarta y se informa.
- [ ] Botón "Volver al modelo original".

### Portabilidad del aprendizaje
- [ ] **Exportar/Importar aprendizaje** (ZIP) desde la UI, para llevarlo a otro equipo. Por defecto incluye solo el
      vocabulario, los patrones, las confusiones, los ajustes y el modelo entrenado; **no** incluye imágenes de
      clientes (casilla opcional "incluir recortes de entrenamiento", con aviso de privacidad).

### Checklist Fase 7
- [ ] Nivel 1 · [ ] Nivel 2 · [ ] Nivel 3 · [ ] Nivel 4 (opcional)
- [ ] Exportar/Importar
- [ ] Pruebas: una confusión aprendida no oculta `10.000 → 12.000`; el vocabulario evita la marca ortográfica
      de una marca registrada
- [ ] Corrida `--etiqueta "F7 aprendizaje"`, con la curva de CER vs número de casos revisados (5, 10, 15, 20)

---

## 6. Fase 8 – Funciones para el trabajo diario

### 8.1 Zonas a ignorar y plantillas por cliente (`ignore_zones.py`)
- [ ] En el visor: herramienta **"Ignorar zona"** (dibujar un rectángulo). Las diferencias dentro de la zona se
      ocultan y no cuentan en el %.
- [ ] Guardar las zonas como **plantilla** con nombre (p. ej. "Cliente Pérez – volante"), en coordenadas
      relativas (0–1) al diseño, en `datos_locales/plantillas/<nombre>.json`.
- [ ] Selector de plantilla antes de comparar; sugerencia automática si el nombre del archivo o el tamaño coinciden.
- [ ] Opción por zona: ignorar todo / solo color / solo texto.

### 8.2 Pegar con Ctrl+V y arrastrar desde el navegador
- [ ] `paste` en la página: si el portapapeles trae una imagen, cargarla como **arte del cliente** (o preguntar
      si es para A o B).
- [ ] Aceptar imágenes arrastradas desde WhatsApp Web o el correo (`dataTransfer` con `image/*` o URL `blob:`).

### 8.3 Comparar versiones de mi diseño (v1 vs v2)
- [ ] Modo "Versiones": subir `diseno_v1.pdf` y `diseno_v2.pdf`. Como ambos son vectoriales, comparar el texto
      exacto (sin OCR), las fuentes, los colores de los spans y el render visual.
- [ ] Opción "verificar correcciones": cargar el resultado anterior y mostrar cuáles errores quedaron
      **corregidos** ✔ y cuáles **siguen** ✘.

### 8.4 Lote de páginas
- [ ] Si ambos PDF tienen varias páginas: "Comparar todas", emparejando por orden (o por similitud visual si el
      número de páginas difiere).
- [ ] Resumen por página (%, estado) y reporte PDF único con todas las páginas.
- [ ] Procesar en segundo plano con progreso por página.

### 8.5 Checklist de aprobación
- [ ] En cada error: **Pendiente / Corregido / No aplica**, con un comentario opcional.
- [ ] Estado global: "Listo para enviar" cuando no queda ningún error pendiente.
- [ ] El reporte PDF incluye el estado y los comentarios de cada error.
- [ ] Se guarda en el historial.

### Checklist Fase 8
- [ ] 8.1 · [ ] 8.2 · [ ] 8.3 · [ ] 8.4 · [ ] 8.5

---

## 7. Fase 9 – Mantenimiento

### 9.1 GitHub Actions (`.github/workflows/tests.yml`)
- [ ] En cada `push` y pull request: runner `windows-latest`, instalar uv (`astral-sh/setup-uv`), instalar Tesseract
      (`choco install tesseract` o descarga del instalador UB-Mannheim), `uv sync`, `uv run pytest` y
      `uv run python -m bench.run --sinteticos --ci`.
- [ ] `--ci` falla si el F1 de alguna categoría baja más de 2 puntos respecto a `bench/umbral_ci.json`
      (versionado).
- [ ] Insignia de estado de las pruebas en el `README.md`.

### 9.2 Aviso de actualización (`app/updates.py`)
- [ ] Al iniciar (máximo 1 vez al día y solo si hay internet, con un timeout de 3 s): `git fetch` y comparar con
      `origin/main`. Si hay commits nuevos, mostrar un aviso en la UI: "Hay una versión nueva. Cierra la app y
      ejecuta `git pull`." (o un botón "Actualizar" que ejecute `git pull` y pida reiniciar).
- [ ] Nunca bloquear el arranque si no hay red.

### 9.3 Versionado
- [ ] `version` en `pyproject.toml` (1.x → 2.0.0 al terminar la v2), `CHANGELOG.md` en español y etiquetas git `v2.0.0`.
- [ ] La versión se muestra en el pie de la UI.

### Checklist Fase 9
- [ ] 9.1 · [ ] 9.2 · [ ] 9.3

---

## 8. Fase 10 – Evaluación final y ajuste

- [ ] Corrida final sobre los 20 casos reales + sintéticos: `--etiqueta "v2 final"`.
- [ ] Tabla **antes (v1) vs después (v2)** por métrica y por tipo de imagen (exportado, WhatsApp, foto, escaneo, CMYK).
- [ ] Revisar a mano cada FP y FN restante y clasificar su causa (OCR, alineación, color, umbral, dedupe).
      Crear una tarea por causa con ≥ 2 apariciones.
- [ ] Ajustar los valores por defecto de `config.json` con los resultados (el nivel 3 ya lo hace por tipo;
      aquí se ajustan los globales).
- [ ] Verificar todas las metas de la sección 0. Las que no se cumplan quedan documentadas en
      `CHANGELOG.md` → "Limitaciones conocidas", con un plan.
- [ ] Probar la instalación limpia en otro equipo siguiendo el `README.md`.
- [ ] Publicar: `git tag v2.0.0; git push --tags`.

---

## 9. Cambios en el modelo de datos

```python
class Difference(BaseModel):
    # ... campos v1 ...
    review: Literal["pendiente", "real", "falso_positivo"] = "pendiente"   # Fase 5.3 / 7
    status: Literal["pendiente", "corregido", "no_aplica"] = "pendiente"   # Fase 8.5
    comment: str | None = None
    ocr_confidence: float | None = None
    ignored_by_zone: bool = False

class Result(BaseModel):
    # ... campos v1 ...
    image_type: str | None = None          # exportado / whatsapp / foto / escaneo / captura
    color_spaces: dict[str, str] = {}      # {"design": "CMYK", "client": "sRGB"}
    alignment_method: str | None = None    # orb / sift / ecc / manual
    template: str | None = None
    timings: dict[str, float] = {}         # segundos por etapa
    learning_version: str | None = None    # huella del aprendizaje usado
```

## 10. Nuevos valores en `config.json`
```json
{
  "ocr_mode": "guiado",
  "spell_lang": "es_CO",
  "cmyk_profile": "",
  "learning_enabled": true,
  "learning_min_confusion_count": 3,
  "learning_autotune_every": 5,
  "update_check": true
}
```

## 11. Nuevas dependencias (todas gratis)
| Paquete | Uso | Licencia |
|---|---|---|
| `spylls` | Hunspell en Python puro | MPL-2.0 |
| `scipy` | emparejamiento húngaro en el banco de pruebas (ya viene con scikit-image) | BSD |
| Diccionarios LibreOffice `es_*` | ortografía | LGPL/GPL/MPL |
| Herramientas de entrenamiento de Tesseract | nivel 4 (incluidas en UB-Mannheim) | Apache 2.0 |

## 12. Orden de trabajo resumido
1. **F5** banco de pruebas + modo Revisión → línea base (sintéticos ya; reales cuando el usuario los cargue)
2. **F6** precisión (6.2 y 6.6 primero, que son rápidos; luego 6.1, 6.3, 6.4 y 6.5), midiendo tras cada uno
3. **F7** aprendizaje, niveles 1 → 2 → 3 (→ 4 cuando haya ≥ 300 líneas)
4. **F8** funciones diarias
5. **F9** CI + actualizaciones + versión
6. **F10** evaluación final y publicación v2.0.0
