# FAVERVIEW – Plan: Auto-trap (reventado automático) con tolerancia de registro

> **Instrucciones para el agente**
> - Lee antes: `PLAN_SUITE.md` (§7 separación raster, §11.1 trapping), `DECISIONES.md` y el código de
>   `app/modules/tools/trapping.py`, `app/modules/separate/raster.py` y `app/modules/vectorize/`.
> - Ejecuta las etapas **T0 → T6 en orden**. `uv run pytest` tras cada tarea y banco de pruebas tras cada etapa.
>   Commit por etapa: `T<n>: …`. Sin `git push` salvo que el usuario lo pida.
> - Reglas del proyecto sin cambios (local, gratis, sin IA, español, honestidad en la UI).
> - **Este plan va antes que `PLAN_PLUGIN_ILLUSTRATOR.md`**: el plugin reutiliza lo que se construye aquí.

---

## 0. Qué piden los clientes y por qué

En la impresión, cada tinta sale de una plancha, cliché o pantalla distinta, y en máquina **nunca caen exactamente en
el mismo sitio** (mal registro). Si dos colores solo "se tocan" en el borde, al moverse aparece un **filete blanco** (el
sustrato) o un solape feo. El **trapping/reventado** agranda ligeramente un color bajo el vecino para que, dentro de una
**tolerancia de movimiento** (p. ej. ±0.2 mm), el borde siga cubierto.

Los clientes quieren:
1. que la **separación de colores** lo haga **automáticamente** (no como paso aparte),
2. poder indicar la **tolerancia de movimiento** de su máquina (en mm), y
3. **ver/comprobar** que con esa tolerancia no quedan filetes.

## 1. Estado actual (revisión del 2026-09-26)

| Qué | Dónde | Estado |
|---|---|---|
| Trapping de placas raster (la tinta clara se expande bajo la oscura, ancho por proceso, choke del blanco, tope de TAC, simulación de mal registro) | `app/modules/tools/trapping.py`, pestaña **Herramientas** | ✅ existe, pero es un paso manual separado |
| Separación de imagen en tintas planas | `app/modules/separate/raster.py::separate_flat` | ⚠️ genera bordes **a tope** (sin solape): se abren con cualquier movimiento |
| Choke de base blanca | `separate_process(..., choke_px)` | ✅ en px, no ligado a una tolerancia en mm |
| Separación PDF (placas) | `app/modules/separate/` | ⚠️ sin opción de auto-trap en la misma pantalla |
| Vectorizador | `app/modules/vectorize/` | ⚠️ sin traps en la salida vectorial |

**Defectos encontrados en `trapping.py`:**
- **D1 (grave):** si las dos tintas tienen luminosidad parecida (`La <= Lb + 5`), **no se crea ningún trap**. Ejemplo
  verificado: rojo L = 52 junto a verde L = 50 → sin trap → filete blanco con cualquier movimiento.
- **D2:** el ancho se define "por proceso" y no como **tolerancia de movimiento** de la máquina del cliente.
- **D3:** no hay límite del trap en **objetos finos** (texto pequeño, líneas): un trap de 0.3 mm en un trazo de 0.4 mm lo deforma.
- **D4:** no hay **retracción (pullback)** de CMY bajo el borde del negro enriquecido.
- **D5:** no existe una **verificación objetiva** de que la tolerancia se cumple (la simulación actual mueve una sola tinta y
  solo es visual).

---

## 2. T0 – Perfiles de máquina y tolerancia

- [x] Nuevo modelo `PressProfile` (`app/core/press.py`), guardado en `datos_locales/prensas/*.json` y editable en la UI
      (pantalla **Tintas → Prensas**, o panel propio):
  ```json
  {
    "nombre": "Pulpo automático 6 colores",
    "proceso": "serigrafia",
    "tolerancia_mm": 0.20,
    "factor_trap": 1.0,
    "trap_max_fraccion_objeto": 0.33,
    "choke_blanco_mm": null,
    "retraccion_negro_mm": null,
    "centrado_si_delta_L_menor_que": 8.0,
    "no_trapear_texto_menor_pt": 6,
    "direccion_impresion": "vertical"
  }
  ```
- [x] Perfiles de ejemplo (valores **orientativos**, documentados como tales en la UI):
  | Perfil | Tolerancia |
  |---|---|
  | Serigrafía textil manual | 0.40 mm |
  | Serigrafía textil automática | 0.20 mm |
  | Flexo banda angosta (etiquetas) | 0.15 mm |
  | Flexo banda ancha / corrugado | 0.25 mm |
  | Offset pliego | 0.08 mm |
  | Digital | 0 (sin trap) |
- [x] Regla de cálculo: **ancho del trap = tolerancia × factor_trap** (por defecto 1.0). Choke del blanco = tolerancia
      (si `null`). Retracción del negro = tolerancia (si `null`).
- [x] `trapping.trap()` acepta `press: PressProfile` y mantiene la compatibilidad con los parámetros actuales (`proceso`, `ancho_mm`).

## 3. T1 – Reglas de trapping corregidas (`app/modules/tools/trapping.py`)

Implementar un **motor de decisión por pares de tintas** probado, con estas reglas en orden:

| # | Situación | Acción |
|---|---|---|
| R1 | Tinta técnica (troquel, cotas, braille) o barniz | Nunca se trapea |
| R2 | Blanco (base) | Solo **choke** (se contrae) el ancho de choke |
| R3 | Una de las dos es negro/tinta muy oscura (L < 25) | La otra se **expande bajo** la oscura (el negro no se mueve) |
| R4 | \|ΔL\| ≥ umbral (`centrado_si_delta_L_menor_que`) | La **más clara se expande** bajo la más oscura (ancho completo) |
| R5 | \|ΔL\| < umbral (luminosidad parecida) → **corrige D1** | **Trap centrado**: cada una se expande **la mitad** del ancho hacia la otra (el total cubre la tolerancia) |
| R6 | Tinta opaca (metálicos, opacidad ≥ 0.8) contra transparente | La **transparente se expande bajo** la opaca |
| R7 | Negro enriquecido (K + CMY) contra color claro/sustrato | **Retracción**: CMY se retrae la tolerancia desde el borde del negro (el K cubre el borde) → **corrige D4** |
| R8 | Objeto fino: ancho local < `trap / trap_max_fraccion_objeto` (medido con la transformada de distancia) | Reducir el trap a `ancho_local × fracción` en esa zona → **corrige D3** |
| R9 | Texto < `no_trapear_texto_menor_pt` (si se conoce su posición: PDF) | Sin trap, o solo el blanco bajo él |
| R10 | Degradados/imágenes (cobertura < 50% en el borde) | Trap "deslizante": se aplica con la cobertura del borde (comportamiento actual), nunca > 100% |
| R11 | Tope de TAC | Se mantiene el tope actual en la zona del trap |
| R12 | Dirección de impresión (opcional) | Tolerancia distinta en la dirección de la máquina y en la transversal (`tolerancia_mm` o `[x, y]`) → elemento estructurante **elíptico** |

- [x] Devolver en cada trap: `{de, bajo, regla, ancho_mm, pixeles}` para mostrarlo en la UI y en el informe.
- [x] `DECISIONES.md`: registrar las reglas y que son **estándar de la industria, orientativas**.

## 4. T2 – Verificación objetiva de la tolerancia (`app/modules/tools/registration_check.py`)

**Prueba de movimiento:** para cada tinta, desplazar su placa en **8 direcciones** (±x, ±y y diagonales) una distancia =
tolerancia, **combinada** con el desplazamiento opuesto de cada otra tinta (peor caso por pares), y calcular:
- **Filetes de sustrato:** píxeles donde el original tenía tinta (cualquier placa ≥ 50%) y tras el movimiento no queda
  ninguna tinta ≥ 50% → **deben ser 0** con trap.
- **Área de solape visible** (dos tintas oscuras superpuestas fuera de lo previsto) → informativo.
- Resultado: `{filetes_px, filetes_mm2, bordes_protegidos_pct, peor_par, mapa_png}`.
- [x] Mapa visual: filetes en **magenta brillante** sobre el trabajo en gris, para "sin trap" y "con trap", lado a lado.
- [x] **Deslizador de movimiento** en la UI (0 → 2 × tolerancia) que anima la vista simulada con las placas desplazadas.
- [x] Rendimiento: a 300 dpi, A4 con 6 tintas ≤ 10 s (usar operaciones morfológicas equivalentes en lugar de rehacer el
      render por cada dirección: el filete aparece donde `max(dilatación de los desplazamientos)` no cubre; calcular por
      pares con máscaras binarias).

## 5. T3 – Auto-trap integrado en la separación

### 5.1 Separar → Imagen (tintas planas)
- [x] En el paso "Ajustes": casilla **"Auto-trap (reventado)"**, **activada por defecto** cuando el perfil de máquina es
      serigrafía o flexo, más el selector **Perfil de máquina** y el campo **Tolerancia de movimiento (mm)**.
- [x] Se aplica a los canales **antes** del tramado y de la exportación (orden: separar → limpiar → **trap** → choke del
      blanco → tramado → exportar).
- [x] En el modo **Índice** (difusión de error) no se aplica (no hay bordes a tope) y se informa por qué.
- [x] En el modo **Proceso simulado**: trap solo para la base blanca (choke) y las tintas opacas (R6); el resto se superpone
      por naturaleza. Informarlo.
- [x] Visor: capas **"Mapa de traps"** y **"Prueba de movimiento"** (T2) + el resultado "✔ Sin filetes con ±0.20 mm" o
      "✘ 3.2 mm² de filetes: ver mapa".

### 5.2 Separar → PDF
- [x] Botón **"Auto-trap"** en la barra (usa el perfil de máquina) → placas con trap en la vista y en **Exportar placas**
      (TIFF/PDF de placas con trap). El PDF original **no** se modifica (el trap es raster, a la resolución de salida).
- [x] Aviso honesto: "El trap se aplica a las placas rasterizadas a X dpi; para un trap vectorial usa el Vectorizador o
      Illustrator".

### 5.3 Herramientas → Trapping
- [x] Se mantiene, ahora con los perfiles de máquina, las reglas nuevas y la prueba de movimiento.

## 6. T4 – Trap vectorial en la salida del Vectorizador

El vectorizador ya produce un **mapa planar con fronteras compartidas** (cada frontera es una cadena entre exactamente dos
regiones). Eso permite un trap **vectorial exacto**:
- [x] Para cada cadena entre las regiones A y B, decidir la dirección con las reglas de T1 (R1–R6).
- [x] Emitir un **trazo (stroke)** a lo largo de la cadena, con el color de la tinta que se expande, **ancho = 2 × trap**,
      **sobreimpresión (overprint) activada**, extremos y uniones redondeados, **recortado** a la unión A ∪ B (para no salir
      al sustrato ni a regiones de terceros), con máscara de recorte (clip path) de A ∪ B.
      Para el trap centrado (R5): dos trazos de ancho = trap (uno por tinta), cada uno en overprint.
- [x] Capa/grupo separado **"Traps FAVERVIEW"** en el PDF/SVG, para poder revisarlo o borrarlo.
- [x] PDF: overprint real (ExtGState `OP/op true, OPM 1`). SVG no tiene overprint → avisar y exportar el SVG sin traps por
      defecto (opción "incluir traps simulados").
- [x] Opción en la UI de Vectorizar: **"Añadir trap para impresión"** + perfil de máquina.
- [x] Verificación: renderizar el PDF con Ghostscript `tiffsep` (con overprint) → pasar la prueba de movimiento (T2) →
      0 filetes.

## 7. T5 – Automatización, preflight e informes

- [x] Paso de receta `auto_trap(perfil, tolerancia_mm)` y `prueba_movimiento(tolerancia_mm)` (con la condición
      "si hay filetes → mover a `errores/`").
- [x] Chequeo de preflight **"Bordes sin protección de registro"** (perfiles serigrafía/flexo): ejecuta la prueba T2 sobre
      las placas y reporta las zonas con filetes.
- [x] Informe de separaciones: sección "Trapping" con el perfil, la tolerancia, la tabla de traps (de, bajo, regla, ancho)
      y los mapas.

## 8. T6 – Pruebas y banco

- [x] Tests unitarios, uno por regla (R1–R12), con placas sintéticas:
  - dos tintas con ΔL grande → la clara se expande exactamente el ancho;
  - **ΔL pequeño → trap centrado, cada una la mitad (regresión de D1)**;
  - negro vs color → el color se expande bajo el negro y el negro no cambia;
  - negro enriquecido → CMY retraído;
  - blanco → solo choke;
  - trazo fino de 0.3 mm con trap de 0.3 mm → trap limitado y el trazo conserva ≥ 90% de su ancho;
  - técnica y barniz → sin cambios;
  - tope de TAC respetado;
  - tolerancia elíptica (x ≠ y).
- [x] Test de la **prueba de movimiento**: sin trap → filetes > 0; con auto-trap a la misma tolerancia → **filetes = 0**;
      con el movimiento 2 × tolerancia → filetes > 0 (el test demuestra que mide algo).
- [x] Test del **trap vectorial**: el PDF tiene overprint en el grupo de traps, el render con tiffsep pasa la prueba T2 y
      las regiones fuera de A ∪ B no cambian.
- [x] Banco (`bench/trapping/`): 20 casos sintéticos (logos de 2–6 tintas planas, pares con ΔL parecido, texto fino,
      negro enriquecido, base blanca sobre prenda) × 3 perfiles. Métricas: filetes tras movimiento (debe ser 0), % de
      área modificada (menos es mejor, sin filetes) y tiempo. Umbral en CI.
- [x] Manual: capítulo **"Reventado (trapping) y tolerancia de registro"**, con qué es, cómo elegir la tolerancia (medir
      el movimiento real de la máquina con una prueba de registro), capturas y los límites.

### Criterios de aceptación
- Con el perfil y la tolerancia elegidos, **la prueba de movimiento da 0 filetes** en los 60 casos del banco.
- D1–D5 corregidos, cada uno con su test de regresión.
- La separación de imagen en tintas planas genera el trap **sin pasos extra** para los perfiles de serigrafía y flexo.
- El PDF vectorial con traps pasa la prueba de movimiento renderizado con Ghostscript.
- Tests y bancos existentes (Comparar, Separación, Vectorizador) sin regresiones.
