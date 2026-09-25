# Cambios de FAVERVIEW

## 2.0.0 — pendiente de fecha

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

### Limitaciones conocidas
_(se completa tras la evaluación final)_

## 1.0.0
- Primera versión: comparación visual, texto (OCR), ortografía, color y fuente, reporte PDF, instalación con winget + uv.
