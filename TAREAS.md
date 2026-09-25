# Tareas pendientes (salen de la evaluación final de la v2)

Cada tarea agrupa una **causa** con 2 o más apariciones entre los falsos positivos (FP) y falsos negativos (FN) que quedan
en el banco de pruebas (`datos_locales/bench_resultados/`, corrida «v2 final»). Al cargar los 20 casos reales conviene
repetir el análisis: las causas más frecuentes cambiarán.

| # | Causa | Categoría | Apariciones | Idea de solución |
|---|---|---|---|---|
| 1 | **Regiones visuales sobre texto** cuando cambia el tamaño de una línea o se quita una palabra (el texto se corre y el desfase se ve como «elemento cambiado») | visual (FP) | 3 | Explicar la región con la línea de texto completa que contiene un error de texto/fuente, no solo con la caja de la palabra (`pipeline._dedupe`). |
| 2 | **Inclinación (¿cursiva?) medida en líneas de ~12 pt** | fuente (FP) | 2 | Medir la inclinación con la mediana de más palabras o exigir ≥ 14 pt (hoy: alto de tinta ≥ 28 px). |
| 3 | **Color de texto en el límite** (ΔE 12–13 en textos de 18–20 pt con iluminación irregular) | color (FP) | 2 | Corregir la iluminación también dentro del texto (ganancia local) o subir la tolerancia con la varianza de iluminación. |
| 4 | **Celdas sueltas de color en bandas de colores** (32×32 px con ΔE 15–23) | color (FP) | 2 | Exigir vecinos de la misma zona o comparar contra la mediana de la banda en lugar de la celda. |
| 5 | **Texto pequeño, claro sobre fondo oscuro** (12 pt gris sobre azul marino): el OCR pierde tildes o letras | texto (FP/FN) | 3 | Añadir variantes de preprocesado para fondo oscuro (invertir antes de escalar) al ajuste automático (nivel 3) y verlo con casos reales. |
| 6 | **Palabra añadida por el cliente en imagen borrosa y reducida** queda solo como región visual | texto (FN) | 1 (se vigila) | Leer las regiones visuales sin texto del diseño con más variantes (`ocr_guided.read_region`). |

## Antes de la próxima versión
- [ ] Cargar los **20 casos reales** (modo revisión) y correr `uv run python -m bench.run --etiqueta "reales"`.
- [ ] Repetir este análisis con los FP/FN de los casos reales y reordenar la tabla.
- [ ] Con ≥ 300 líneas revisadas: `uv run faverview-aprender --entrenar` (la prueba A/B decide si se activa).
