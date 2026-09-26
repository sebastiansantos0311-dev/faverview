# Cambios de FAVERVIEW

## 3.0.0 (suite) — en desarrollo
- **S0 – Preparación:** código de Comparar movido a `app/modules/compare/` y `app/core/`, rutas repartidas en routers
  (`app/main.py` ≤ 80 líneas), `GET /api/status`, detección de Ghostscript, nuevas dependencias y interfaz con pestañas.
- **S1 – Núcleo compartido:** `core/units`, `core/colorscience` (Lab D50, ΔE2000 validada con los 34 pares de Sharma, densidad
  orientativa, modelo de mezcla de tintas), `core/inks` (modelo, normalización de nombres, importadores CxF3/ASE/CSV,
  bibliotecas del usuario), `core/ghostscript` (SAFER, tiempo límite, cancelación, errores en español), `core/pdfinfo`
  (cajas en mm, OutputIntent, PDF/X, transparencias, capas) y la pantalla **Tintas**. Cobertura de `app/core`: 88 %.
- **S2 – Separar colores (PDF):** inventario de tintas (Separation/DeviceN con funciones PDF tipos 0/2/3/4, duplicadas, sin uso),
  placas por tinta con Ghostscript `tiffsep` (caché, límite de megapíxeles), vista compuesta simulada, densitómetro y mapa de
  cobertura total (TAC) con perfiles, 7 chequeos de separación (negro enriquecido, texto pequeño multitinta, barniz/blanco/
  técnicas y sobreimpresión, registro, RGB/Lab sin convertir, líneas finas, TAC), edición sobre copia (unir, renombrar,
  convertir a proceso, eliminar sin uso) y exportación de placas (TIFF 8/1 bit, PDF, informe). Pestaña «Separar colores → PDF».

## 2.0.0 — 2026-09-25

### Medición
- **Banco de pruebas** (`uv run python -m bench.run`): 78 casos sintéticos reproducibles (`tests/sinteticos/`) con errores
  conocidos (número cambiado, palabra quitada/agregada, tilde, color ΔE 5–40, logo removido, fuente, negrita) y
  degradaciones (JPEG 40–90, rotación, perspectiva, desenfoque, ruido, iluminación irregular, recorte, escala, CMYK,
  marco de captura). Mide precisión, recall, F1, falsos positivos por caso, CER del OCR y tiempos, y compara contra la
  corrida anterior.
- **Modo revisión** en la interfaz: ✔ Real / ✘ Falso positivo por error, «Marcar error no detectado», y «Guardar como caso
  de prueba» (`datos_locales/casos/`, nunca se sube a git).

### Precisión
- **OCR guiado por el PDF**: se lee cada línea del diseño por separado (canal de más contraste, umbral adaptativo
  Sauvola, escala de ~40 px por letra, `--psm 7`) con relecturas de verificación y una pasada para el texto que solo
  tiene el cliente.
- **Alineación robusta**: ORB → SIFT, validación de la homografía, refinamiento ECC, recorte del marco de capturas de
  pantalla, máscara de píxeles válidos y **alineación manual** (4 puntos).
- **Comparación visual tolerante** a desajustes de 1–2 px, desenfoque, ruido y **corrección de iluminación irregular**.
- **Colores CMYK y perfiles ICC** → sRGB; la interfaz muestra el espacio de color de cada archivo.
- **Ortografía con Hunspell** (LibreOffice, `es_CO` por defecto) + tildes faltantes con sugerencia única.
- **Fuentes**: ya no se estima sobre palabras con errores de texto; se exige consistencia en la línea y ≥ 3 palabras.
- Barra de progreso por etapas.

### OCR que aprende
- Vocabulario y patrones, confusiones aprendidas (sin ocultar jamás un cambio de dígitos), ajuste automático del
  preprocesado por tipo de imagen y re-entrenamiento opcional de Tesseract con prueba A/B. Exportar / importar el
  aprendizaje. Comando `faverview-aprender`.

### Trabajo diario
- Zonas a ignorar y plantillas por cliente, pegar con Ctrl+V, comparar versiones de mi diseño, verificar correcciones,
  comparar todas las páginas con un solo reporte y checklist de aprobación («Listo para enviar»).

### Mantenimiento
- GitHub Actions (pruebas + banco de pruebas con umbral de F1), aviso de versión nueva y versión en el pie de la app.

### Resultados del banco de pruebas (78 casos sintéticos)
| Métrica | v1 | v2 | Meta |
|---|---|---|---|
| Recall de errores de **texto** | 97,1 % | 97,1 % | ≥ 95 % |
| Precisión de **texto** | 30,8 % | 97,1 % | ≥ 90 % |
| Recall de **color / elemento visual** | 100 % | 100 % | ≥ 90 % |
| **Falsos positivos** por caso | 5,67 | 0,17 | ≤ 1 |
| **CER** del OCR | 1,65 % | 0,86 % | ≤ 3 % |
| Casos sin errores → «Aprobado» | 96,6 % | 100 % | 100 % |
| Tiempo por página (200 dpi, 1 proceso, 8 núcleos) | ~5 s | ~10–12 s | ≤ 15 s |

Detalle por categoría y por tipo de imagen: `uv run python -m bench.comparar "v1 linea base tipos" "v2 final"`.
Las cifras son de casos **sintéticos**; las metas sobre los **20 casos reales** se medirán cuando se carguen
(ver `TAREAS.md`).

### Limitaciones conocidas
- **Datos reales pendientes**: todo se validó con casos sintéticos. Fotos, escaneos y WhatsApp reales pueden comportarse
  distinto; por eso el banco de pruebas y el modo revisión están pensados para medirlo apenas haya casos reales.
- **Tildes y OCR**: el OCR pierde acentos con facilidad. Si el diseño tiene la tilde y el OCR no la ve, **no** se reporta
  (evita falsos positivos); si el diseño NO la tiene y el cliente sí, se reporta como error de ortografía.
- **Texto pequeño (≈ 12 pt) claro sobre fondo oscuro** y **texto añadido en imágenes muy borrosas y reducidas** son los
  casos más difíciles del OCR; algunos aparecen solo como «elemento visual».
- **Fuentes**: se necesitan ≥ 3 palabras (de ≥ 3 letras) que coincidan en el mismo tramo de texto; la inclinación y el
  grosor no se miden en cuerpos menores de ~10 pt ni con imágenes borrosas.
- **Aprendizaje**: con datos sintéticos no se aprecia mejora medible (sus errores no son sistemáticos); el auto-ajuste
  solo se adopta si mejora en casos que no vio **y** no empeora el pipeline completo. El re-entrenamiento (≥ 300 líneas)
  se probó de punta a punta con líneas sintéticas, no con datos reales, y su prueba A/B usa el mismo banco de pruebas.
- **Rendimiento**: en un equipo de 4 núcleos o menos una página puede pasar de 15 s (el OCR corre en paralelo).
- La instalación limpia se probó con un `git clone` + `uv sync` local; falta probarla en otro equipo con Windows.

## 1.0.0
- Primera versión: comparación visual, texto (OCR), ortografía, color y fuente, reporte PDF, instalación con winget + uv.
