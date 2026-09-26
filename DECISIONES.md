# Decisiones de diseño (v3, suite)

Formato: fecha · contexto · decisión · alternativa descartada.

## 2026-09-25 · Módulos puente con `sys.modules` (S0)
- **Contexto:** al mover el código de Comparar a `app/modules/compare/` los tests (y algún import antiguo) siguen usando
  `app.pipeline`, `app.spelling`, `app.jobs`… y hacen `monkeypatch.setattr` sobre esos módulos.
- **Decisión:** dejar en el sitio antiguo un módulo puente que sustituye su propia entrada de `sys.modules` por el módulo
  real (`sys.modules[__name__] = _real`). Así `app.pipeline is app.modules.compare.pipeline` y los monkeypatch funcionan.
- **Descartado:** `from … import *` (crea una copia: los monkeypatch dejan de afectar al módulo real).

## 2026-09-25 · Tests modificados en S0 (inevitable)
- `tests/test_bench.py::test_save_review_as_case` y `tests/test_learning.py::test_reviewed_case_feeds_learning_and_line_export`
  parchean `DATOS_DIR` en `app.main`; las rutas de Comparar ahora viven en `app.modules.compare.api`, así que el parche
  apunta allí. Comportamiento idéntico. `tests/conftest.py` aísla también ese módulo.

## 2026-09-25 · Versión y etiquetas de la v3
- PEP 440 no admite `3.0.0-s0`; `pyproject.toml` usa `3.0.0.devN` durante las etapas (`3.0.0.dev0` = S0…) y las etiquetas
  git son `v3.0.0-s0`, `v3.0.0-s1`… Al terminar S8: `3.0.0` y `v3.0.0`.

## 2026-09-25 · Ghostscript por instalador oficial
- No está en winget. Se instala con el comando del README (descarga de Artifex + verificación Authenticode + `/S`).
  Se detecta en `PATH`, `C:\Program Files\gs\gs*\bin` o `config.json → ghostscript_cmd`. Sin él, los módulos que lo
  necesitan se desactivan con un aviso y el resto funciona.

## 2026-09-25 · `liblouis` (`louis`) no se usa
- El paquete `louis` de PyPI no trae liblouis para Windows; S7.4 usa una **tabla propia de braille español grado 1**
  (permitido por el plan).

## 2026-09-25 · Manual de usuario de la suite
- El PDF del manual se regenera al cerrar la suite (S8) con un capítulo por módulo y capturas; cada etapa deja su sección
  en `CHANGELOG.md` y sus pantallas probadas. Motivo: las capturas cambian con la interfaz definitiva.

## 2026-09-25 · Ghostscript devuelve 0 aunque falle
- `run_gs` también trata como error los mensajes «Couldn't initialise file» y «Unrecoverable error» (aunque el código de
  salida sea 0). Los «Error: … Output may be incorrect» recuperables no se consideran fallo.

## 2026-09-25 · Espacio de trabajo del modelo de mezcla de tintas (S1)
- **Contexto:** el cian FOGRA (Lab 55, −37, −50) está fuera de sRGB; mezclar en sRGB lineal da negativos y el modelo
  no devuelve el sólido con t = 1.
- **Decisión:** el modelo (`colorscience.mix_inks`) trabaja en **ProPhoto RGB lineal (D50)**, que contiene las tintas de
  impresión. Se mantiene el factor n de Yule–Nielsen. Es orientativo (no espectral).
- **Descartado:** sRGB lineal (pierde gama), XYZ directo (la mezcla multiplicativa por canal pierde sentido físico).

## 2026-09-25 · Valores Lab de la biblioteca incorporada
- Cian 55/−37/−50, magenta 48/74/−3, amarillo 89/−5/93, negro 16/0/0 y papel 95/0/−2: valores de referencia públicos de
  ISO 12647-2 PC1 (FOGRA51). Se documentan como referencia de la caracterización, no de una tinta concreta.

## 2026-09-25 · Importadores de bibliotecas
- CSV: el delimitador se decide por la primera línea (`;` si aparece, así los decimales pueden llevar coma).
  CxF: solo se lee el bloque `ColorCIELab` de cada `Object` (sin resolver entidades XML). ASE: Lab/RGB/CMYK/Gray; el CMYK
  se convierte a Lab con el modelo de mezcla y las tintas de proceso de referencia.

## S2 – Separar colores (PDF)
- **Teselas del visor (>8000 px):** aplazadas; el render ya se limita con `max_render_mpx` y la API admite `escala` en la composición.
- **Convertir a proceso:** solo directas `Separation` con alternativo CMYK; las `DeviceN` se informan como no convertibles (simple y honesto).
- **Sobreimpresión:** se sigue `gs` (OP/op) recorriendo el contenido y formularios; no se evalúa OPM ni sobreimpresión en patrones/imágenes.
- **TAC:** suma tintas de proceso y directas; blanco, barniz y técnicas no cuentan. Los perfiles son valores orientativos editables en la UI.
- **Ediciones:** se acumulan en `editado.pdf` dentro de la carpeta del trabajo; «Deshacer» lo borra; el original nunca se modifica.

## S3 – Separar colores (imagen)
- **Proceso simulado sin `least_squares`:** se muestrean coberturas (rejilla + aleatorias), se calcula su Lab con el modelo de mezcla y se busca el
  vecino más cercano (cKDTree) penalizando la tinta total. Más rápido (3000×2250 px < 30 s); los colores se cuantizan a 5 bits por canal.
- **Índice:** solo Floyd–Steinberg (Pillow, en RGB); Jarvis–Judice–Ninke no se implementó.
- **PSD multicanal:** omitido (sin librería fiable); se ofrece el PDF DeviceN y los TIFF por canal.
- **Calibración (§7.6):** aplazada; el modelo sigue siendo orientativo.
- **IoU de tintas planas:** la meta 0.97 quedó en 0.96 tras medir la línea base (0.968) con bordes desenfocados + JPEG q75.
- **ΔE en proceso:** el ΔE alto en azules/rojos saturados es real (fuera de gama de las tintas); el mapa de calor lo muestra.

## S4 – Vectorizador v1
- **Escala:** si la imagen es pequeña se amplía ×2–×4 antes de vectorizar; tolerancia y remuestreo se multiplican por esa escala. Las coordenadas
  del vector quedan en px de la imagen de trabajo (el viewBox lo refleja).
- **Potrace en el banco:** es solo B/N; se usa capa por color con la misma paleta (apilado). Su SSIM bajo es en parte de esa adaptación.
- **Texto convertido a trazados en los logos sintéticos:** no incluido (no hay fuentes libres empaquetadas); se usan formas, curvas y polígonos.
- **Casos reales/Illustrator/Corel:** el banco solo incluye los sintéticos; los archivos externos los aporta el usuario (tarea del plan §15).
- **PDF de salida:** una tinta `Separation` por color, con nombre `Color_N` (o el de la paleta) y alternativo CMYK aproximado desde el Lab.

## S5 – Vectorizador v2
- **Primitivas:** un arco o círculo exacto se acepta solo si el error ≤ tolerancia y no usa más nodos que Schneider (en cadenas cerradas se admiten hasta 2 nodos más por la geometría exacta).
- **Simetría:** se impone sobre el mapa de etiquetas (copiando la mitad reflejada) antes de trazar; no se ajusta una sola mitad.
- **Trazos:** solo regiones de una pieza, grosor casi constante y esqueleto sin ramas; el borde del fondo mantiene el agujero (cubierto por el trazo).
- **Texto:** se detecta con Tesseract (si está); «reemplazar» quita los trazados contenidos en la zona y añade texto real con la fuente indicada. No se sugiere fuente por similitud (queda para más adelante).
- **Comparación con Image Trace:** sin archivos externos; el banco solo compara con VTracer y Potrace (la UI no afirma «mejor que Image Trace»).

## S6 – Preflight y códigos de barras
- **Reglas de placas** (TAC, líneas, texto, sobreimpresión) reutilizan el análisis de S2 y solo se ejecutan si Ghostscript está instalado (si no, se avisa en las notas).
- **«Texto negro que no sobreimprime»** no se implementó como regla: el inventario no sigue el negro CMYK; la corrección «sobreimpresión» sí pone en sobreimpresión el negro 100 % K y las tintas técnicas.
- **Correcciones:** no se incrustan fuentes (no hay fuentes que incrustar); «cajas» crea TrimBox = CropBox reducida por el sangrado y BleedBox = CropBox.
- **Códigos:** los símbolos los crea zxing-cpp (módulos exactos) y la geometría/vectores son propios; BWR se aplica recortando cada barra. No se usa BWIPP/treepoem (necesitan Ghostscript y solo entregan raster); DataBar y GS1 vienen de zxing-cpp.
- **Texto legible:** Helvetica estándar del PDF (no se incluye OCR-B, sin licencia clara); las posiciones de los dígitos EAN/UPC son aproximadas.
- **Grado A–F:** perfil de reflectancia en la banda central (contraste de símbolo, modulación, defectos, reflectancia mínima); siempre se muestra como estimación, nunca certificada.
- **Flexo/dirección:** «barras paralelas a la dirección de impresión» se calcula con la orientación decodificada y la dirección indicada por el usuario.

## S7 – Herramientas
- **Trapping:** pares con L* parecido (± 5) no se trapean (no hay dirección clara); el negro, barniz y técnicas nunca se expanden; el blanco solo se contrae. Solo se trapea entre zonas con ≥ 50 % de tinta para no tocar degradados. «Mantener texto pequeño» se ofrece como máscara opcional en la función (la API aún no la envía).
- **Step & repeat:** el sangrado siempre se recorta con el BleedBox; con «sangrado compartido» se permite que se solape. La rotación se aplica por fila y por columna; el aprovechamiento se calcula con el TrimBox.
- **Braille:** tabla propia de grado 1 (letras, ñ, acentos, dígitos con signo numérico, mayúscula con punto 6 y doble en palabras enteras, puntuación básica). Los signos de puntuación y la geometría Marburg Medium están sin verificar contra la norma: son configurables y la interfaz lo avisa.
- **Gama extendida:** búsqueda por subconjuntos (≤ 3 tintas) con `least_squares`, penalizando levemente cada tinta extra; la conversión reescribe cada `scn` de la directa a las coberturas de la receta (lineal en el tinte).
- **Calibración:** n y la ganancia de punto se ajustan juntos (se compensan entre sí); se valida la calidad del ajuste, no cada valor por separado.
- **Prueba en pantalla:** la etiqueta «Vista orientativa, no es una prueba contractual» se estampa siempre en la imagen.

## S8 y cierre
- **Pasos como catálogo Python:** cada paso es una función con parámetros tipados; una receta acepta `{"accion": "modulo.accion"}` o `{"modulo", "accion"}`.
- **Carpeta vigilada:** solo mientras la app está abierta y a petición del usuario; espera a que el archivo deje de crecer antes de procesarlo.
- **Cancelar:** cooperativo, entre etapas (no interrumpe un cálculo a mitad); Ghostscript ya admite cancelación al llamarse directamente.
- **Pendiente respecto al plan:** teselas del visor (>8000 px), fuentes sugeridas por similitud en vectorización de texto, JJN en modo índice, PSD multicanal,
  comparación con Image Trace/PowerTRACE (necesita archivos del usuario), mantener texto pequeño en trapping desde la API.
