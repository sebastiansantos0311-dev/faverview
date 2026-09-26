# Investigación: software de preprensa y propuesta de la suite FAVERVIEW

> Objetivo: entender cómo funcionan las suites profesionales de preprensa (Esko y sus competidores), qué módulos
> tienen y cómo construir una suite similar, **local, gratuita y open source**, empezando por el
> **separador de colores** y el **vectorizador**.
> Fuentes consultadas en español, inglés y alemán (lista al final).

---

## 1. ¿Qué es la preprensa y cuál es el flujo?

Preprensa es todo lo que ocurre entre "el diseño está aprobado" y "la plancha o el cliché están en la máquina".
En empaque (flexo, offset, huecograbado, serigrafía, digital), el flujo típico es:

```
Arte del cliente → Preflight (revisión técnica) → Edición/adaptación (tintas, textos, códigos, blanco)
 → Separación de colores → Trapping (reventado/Überfüllung) → Montaje / step & repeat / imposición
 → Prueba de color (proof) y aprobación → RIP + tramado (screening) → Plancha/cliché → Impresión
```

Y en paralelo: gestión de color (ICC, gama extendida), control de versiones, aprobación del cliente, diseño
estructural (troqueles) y maquetas 3D.

**FAVERVIEW ya cubre** una parte de "aprobación / control de calidad": la comparación del arte del cliente contra
el diseño. En Esko, el equivalente comercial es la revisión de artes de WebCenter/Comply.

---

## 2. Empresas y software del sector

| Empresa (país) | Productos clave | Enfoque |
|---|---|---|
| **Esko** (Bélgica, grupo Veralto) | ArtPro+, DeskPack, Automation Engine, WebCenter, Color Engine, Equinox, Phoenix, ArtiosCAD, Studio, Imaging Engine, Pack Proof, CDI (planchas) | Líder en empaque y etiquetas. Suite completa de principio a fin. |
| **Hybrid Software** (Bélgica) | **PACKZ** (editor PDF nativo), **Cloudflow** (flujo + RIP + aprobación) | Principal competidor de Esko. PACKZ es independiente (no es un plugin de Illustrator). |
| **Kodak** (EE. UU.) | **Prinergy** (flujo), Maxtone SX (tramado flexo), Flexcel NX | Muy fuerte en offset y en empaque convencional. |
| **Agfa** (Bélgica) | Apogee, Asanti, Arkitex | Flujos para comercial y gran formato. |
| **SCREEN** (Japón) | Trueflow, Equios | Flujos y RIP. |
| **Heidelberg** (Alemania) | **Prinect** | Flujo integrado con sus prensas offset. |
| **callas software** (Alemania, Berlín) | **pdfToolbox** | Preflight, corrección, conversión de color, imposición. Estándar de facto en revisión de PDF. |
| **Enfocus** (Bélgica) | PitStop Pro/Server, Switch | Preflight y edición de PDF, automatización. |
| **GMG** (Alemania) | ColorProof, OpenColor | Pruebas de color y gestión de color para empaque. |
| **Fogra** (Alemania) | Normas y certificaciones (ISO 12647, perfiles FOGRA39/51) | Instituto de investigación: define cómo "debe" imprimirse. |
| **Freehand Graphics** (EE. UU.) | **Separation Studio NXT** | Separaciones para **serigrafía** (proceso simulado, índice, tintas planas). |
| **UltraSeps** (EE. UU.) | UltraSeps (plugin de Photoshop) | Separaciones automáticas para serigrafía. |
| Vectorizadores | Adobe Image Trace, CorelDRAW PowerTRACE, Vector Magic, Vectorizer.AI, **VTracer** (open source), **Potrace** (open source), Inkscape Trace Bitmap | Convertir imágenes de píxeles en vectores. |

**Conclusión del mercado:** hay dos modelos.
1. **Plugins de Illustrator/Photoshop** (Esko DeskPack): dependen de Adobe.
2. **Editores PDF nativos independientes** (Esko ArtPro+, Hybrid PACKZ): trabajan directamente sobre el PDF.
   Es la tendencia actual.

Para nosotros, lo coherente es el modelo 2 (app web local que trabaja sobre PDF/imágenes), sin depender de Adobe.

---

## 3. ¿Qué tiene la suite de Esko? (mapa completo)

### 3.1 Edición y preparación ("Structure & Graphics")
| Producto | Qué hace |
|---|---|
| **ArtPro+** | Editor PDF nativo para preprensa: gestión de tintas (separaciones), trapping automático e interactivo, step & repeat, marcas dinámicas, códigos de barras, tramado por objeto, reconocimiento de texto, distorsión (flexo), conversión a CMYK. |
| **DeskPack** | Plugins para Illustrator/Photoshop. **Essentials:** Data Exchange, boostX, Dynamic Barcodes, PDF Import, Preflight, Viewer, White Underprint, Dynamic Marks, Dynamic VDP, Text Recognition. **Advanced** (además): Channel Mapping, Color Engine, Image Extractor, Instant Trapper, Trapper, Screening, PowerLayout, PowerTrapper. |
| **Dynamic Content** | Separa los textos (ingredientes, idiomas, legales) del diseño y los gestiona como datos. |
| **Phoenix** | Planificación automática de montaje/imposición (ganging de trabajos para ahorrar material). |
| **ArtiosCAD** | Diseño estructural 2D/3D: troqueles, cajas plegadizas, corrugado. |
| **Studio** | Maquetas 3D realistas del empaque (desde Illustrator). |
| **Cape Pack / Truckfill** | Paletizado y carga de contenedores. |
| **Store Visualizer** | Realidad virtual de la góndola. |

### 3.2 Color e impresión ("Color & Print")
| Producto | Qué hace |
|---|---|
| **Color Engine** | Gestión de color centralizada: bibliotecas de tintas, perfiles, device links, conversiones. |
| **Equinox** | **Gama extendida**: convierte tintas especiales (Pantone) a un juego fijo de tintas (CMYK+OGV) para no cambiar tintas en máquina. Aplica UCR/GCR y ahorro de tinta. |
| **Automation Engine** | Automatización de flujos: preflight, normalización, trapping, step & repeat y salida, integrada con ERP/MIS (JDF/JMF, XML). |
| **Imaging Engine** | RIP y tramado (screening) para flexo, offset y digital. |
| **Pack Proof** | Pruebas de color precisas, incluyendo tintas especiales y gama extendida. |
| **Flexo Front End** | Conexión del diseño con la producción de clichés flexo. |

### 3.3 Colaboración ("Content & Collaboration")
| Producto | Qué hace |
|---|---|
| **WebCenter** | Gestión de artes, aprobaciones en línea, anotaciones, versiones y proyectos. |
| **Comply** | Revisión asistida de cumplimiento del arte (textos legales, alérgenos, etc.). |

### 3.4 Hardware de planchas
CDI (imagers de clichés), XPS (exposición LED), HD Flexo. **Fuera de alcance** para nosotros (es hardware).

---

## 4. Módulo 1 – Separador de colores

Hay **dos problemas distintos** que la gente llama "separación de colores". La suite debe resolver ambos.

### 4.1 Separación de un PDF vectorial ("ver y sacar las placas")
Tomar el PDF final y obtener **una placa por tinta** (C, M, Y, K + cada tinta directa como Pantone, blanco o
barniz), como la paleta "Separaciones" de ArtPro+ o la "Vista previa de salida" de Acrobat.

**Funciones:**
- Listar todas las tintas del PDF (proceso + directas + blanco/barniz/troquel), mostrar/ocultar cada una y verlas
  en negativo o positivo.
- **Cobertura de tinta** por placa y **TAC** (cobertura total, p. ej. máx. 300% en offset o 260–280% en flexo) con
  un mapa de calor de las zonas que se pasan.
- **Densitómetro virtual**: al pasar el mouse, muestra el % de cada tinta en ese punto.
- **Mapeo de tintas** (channel mapping): unir tintas duplicadas ("PANTONE 485 C" vs "Pantone 485C"), renombrar,
  convertir una directa a CMYK, eliminar las que no se usan.
- Detectar la **sobreimpresión** (overprint) y el knockout, blanco sobreimpreso por error y texto negro 4 colores.
- Exportar cada placa como TIFF de 1 bit/8 bits o PDF, más una hoja de "placas" para el cliente.

**Tecnología (gratis):**
- **Ghostscript** (AGPL, compatible con nuestra licencia): dispositivo `tiffsep` = un TIFF por tinta, incluidas
  las directas, y el compuesto. También hace **trapping básico** de bitmap (`-dTrapX/-dTrapY`, Captrap).
- **PyMuPDF**: leer el contenido del PDF (espacios de color `Separation`/`DeviceN`, sobreimpresión en ExtGState).
- **pikepdf** (MPL-2.0): modificar el PDF a bajo nivel (renombrar/unir tintas).
- **LittleCMS** (MIT, vía `Pillow.ImageCms`) para conversiones ICC.

### 4.2 Separación de una IMAGEN (raster) a tintas ("separar una foto o un logo en N tintas")
Clave para **serigrafía, flexo de pocas tintas y etiquetas**. Es lo que hacen Separation Studio y UltraSeps.

| Modo | Para qué | Algoritmo (sin IA) |
|---|---|---|
| **Tintas planas (spot)** | Logos e ilustraciones con colores sólidos | Cuantización de color en **CIELAB** (k-means / median cut) → cada píxel se asigna a la tinta más cercana (ΔE2000). Limpieza morfológica. Opción de fijar la paleta a tintas del usuario. |
| **Proceso simulado** | Fotos sobre prenda oscura o pocas tintas "fotográficas" | Por píxel, resolver qué % de cada tinta reproduce el color: **mínimos cuadrados no negativos** en Lab sobre un modelo de mezcla de tintas (Neugebauer / Yule-Nielsen, o Kubelka-Munk para tintas opacas). Luego se suavizan los canales. |
| **Índice** | Serigrafía: puntos cuadrados del mismo tamaño | Asignar cada píxel a una tinta con **dithering por difusión de error** (Floyd–Steinberg / Jarvis) en Lab, a 170–200 dpi. |
| **CMYK** | Proceso normal | Conversión ICC (FOGRA39/51, GRACoL) con **GCR/UCR** configurable y límite de TAC. |
| **Gama extendida (tipo Equinox)** | Reemplazar Pantones por CMYK+OGV | Para cada tinta directa, buscar la combinación de tintas fijas que minimiza ΔE2000 (optimización con límite de tintas y TAC). Mostrar el ΔE resultante de cada Pantone. |

**Extras de serigrafía/flexo:**
- **Base blanca** (underbase) automática con **choke** (contracción) para prendas oscuras.
- **Tramado:** AM (punto redondo/elíptico, lineatura y ángulo por tinta) y FM/estocástico.
- **Vista previa simulada** de la impresión sobre el color del sustrato (prenda o cartón kraft).
- Exportar placas como **PDF con tintas directas** (DeviceN) o TIFF por canal.

**Tecnología:** NumPy/SciPy (`scipy.optimize.nnls`), scikit-image (Lab, ΔE2000), OpenCV, LittleCMS, y
**ArgyllCMS** (AGPL) si más adelante queremos crear perfiles propios.

> ⚠️ **Pantone:** los valores Lab oficiales de las bibliotecas Pantone son propiedad de Pantone (X-Rite) y tienen
> licencia. Solución: que el usuario **importe sus propias bibliotecas** (CxF, ASE o CSV exportadas de su software
> con licencia) o mida con su espectrofotómetro. La app no trae Pantone de fábrica.

---

## 5. Módulo 2 – Vectorizador (objetivo: mejor que Illustrator y CorelDRAW)

### 5.1 El estado del arte
- **Adobe Image Trace**: 12 preajustes, buenos resultados, pero produce muchos nodos, huecos o "costuras" entre
  formas, colores no controlados y formas con agujeros.
- **CorelDRAW PowerTRACE**: similar, con buenas opciones de limpieza de color.
- **Potrace** (GPL): excelente en **blanco y negro**. Solo una tinta.
- **VTracer** (MIT, Rust, con paquete para Python): **color**. Usa agrupación jerárquica de colores y apila formas
  (sin agujeros), lo que da una salida **más compacta que Image Trace**, muy buena para logos con colores planos.
- Vectorizadores con IA en la nube (Vectorizer.AI, etc.): muy buenos, pero de pago y en la nube.
  Descartados por nuestras reglas.

### 5.2 Dónde podemos ganarle a Illustrator: vectorización **pensada para preprensa**
Illustrator vectoriza "para que se vea bien en pantalla". Nosotros vectorizamos **para imprimir**, y ahí están las
ventajas medibles:

1. **Paleta controlada:** el usuario elige N tintas (o las detecta el separador del Módulo 1). Cada forma sale con
   un color **exacto** de esa paleta, nunca con 200 tonos parecidos. Salida directa con **tintas directas**
   (Separation) en PDF.
2. **Cero huecos entre formas:** mapa planar con **fronteras compartidas**, así que dos formas vecinas usan
   exactamente la misma curva. Opción "apilado" tipo VTracer y opción "sin superposición" para corte de vinilo
   o serigrafía.
3. **Menos nodos, curvas más limpias:** ajuste de Bézier con detección de esquinas, más **reconocimiento de
   primitivas**: líneas rectas, arcos, **círculos y elipses perfectos**, ángulos de 90°, y **simetría** detectada
   y forzada (muy común en logos).
4. **Preprocesado inteligente sin IA:** quitar el ruido JPEG y el antialias con filtros que preservan bordes
   (bilateral, mean-shift), escalado previo ×2–×4 para imágenes pequeñas y umbral adaptativo para B/N.
5. **Controles de preprensa:** grosor mínimo de línea y de detalle imprimible (p. ej. 0.1 mm en flexo), eliminar
   manchas menores a X mm², y opción de **trapping** automático en la salida.
6. **Texto:** detectar zonas de texto con OCR (ya lo tenemos) y **sugerir la fuente** o marcarlas para reemplazarlas
   con texto real en vez de vectorizarlas.
7. **Comparación objetiva:** superponer el vector sobre el original y medir la diferencia con el motor de
   FAVERVIEW, es decir, reutilizar el buscador de diferencias.

### 5.3 Pipeline propuesto
```
Imagen → limpieza (bilateral/mean-shift, escalado) → cuantización en Lab con paleta controlada
 → segmentación en regiones (mapa planar, fronteras compartidas) → limpieza (manchas, huecos)
 → trazado de contornos → ajuste de curvas (Bézier + esquinas) → primitivas (rectas, arcos, círculos, simetría)
 → salida SVG / PDF (tintas directas) / EPS / DXF
```
- **Motores base:** VTracer (color) y Potrace (B/N), usados como punto de partida y como referencia a superar.
  Las mejoras propias (paleta, fronteras compartidas, primitivas y controles de preprensa) van encima.

### 5.4 Cómo demostrar que es "mejor"
Banco de pruebas propio (igual que el de FAVERVIEW) con 30–50 imágenes: logos, líneas, escaneos, fotos de baja
resolución y capturas de WhatsApp. Por cada una se mide:
- **Fidelidad:** SSIM y ΔE promedio entre el vector renderizado y el original.
- **Complejidad:** número de nodos y de formas (menos es mejor, a igual fidelidad).
- **Limpieza:** huecos/costuras entre formas (píxeles de fondo visibles entre regiones) y nº de colores de salida
  respecto a la paleta pedida.
- **Tiempo.**
Comparamos contra **Image Trace, PowerTRACE, VTracer y Potrace**. Los archivos de Illustrator y Corel se generan a
mano una vez, porque tú o tu equipo tienen las licencias. **Solo diremos "mejor" cuando los números lo muestren.**

---

## 6. ¿Qué más tiene una suite completa? (y qué es viable para nosotros)

| Módulo | Equivalente comercial | Viabilidad para FAVERVIEW | Prioridad |
|---|---|---|---|
| **Comparador de artes** | WebCenter/Comply | ✅ Hecho (v1) + v2 en curso | — |
| **Separador de colores** (PDF y raster) | ArtPro+ Separations, Separation Studio | ✅ Alta (Ghostscript + NumPy) | **1** |
| **Vectorizador** | Image Trace, PowerTRACE | ✅ Alta (VTracer/Potrace + mejoras) | **1** |
| **Preflight** (revisión técnica del PDF) | Esko Preflight, callas pdfToolbox, PitStop | ✅ Alta: fuentes, resolución, espacios de color, sangrado, línea fina, texto pequeño, overprint, TAC, PDF/X | **2** |
| **Códigos de barras** (generar + verificar) | Dynamic Barcodes | ✅ Alta: generar (EAN/UPC/GS1-128/DataMatrix/QR) y verificar legibilidad, tamaño y reducción de barras (BWR) | **2** |
| **Gestión de color / conversión de tintas** | Color Engine, Equinox | 🟡 Media (LittleCMS + optimización; Pantone con licencia del usuario) | **3** |
| **Trapping** (reventado) | Trapper, Instant Trapper | 🟡 Media: trapping vectorial por reglas (tinta clara bajo oscura, ancho por tinta). El trapping "estético" de Esko es difícil. | **3** |
| **Step & repeat / imposición / marcas** | ArtPro+, Phoenix, pdfToolbox | 🟡 Media: rejilla, marcas de registro/corte, barras de color, ganging simple | **3** |
| **Base blanca / barniz / capas técnicas** | White Underprint | ✅ Alta (se hace dentro del separador) | **3** |
| **Braille** (empaque farmacéutico) | Esko Braille | ✅ Media (liblouis LGPL + norma Marburg Medium) | 4 |
| **Distorsión flexo** (compensación del cliché) | ArtPro+ Distortion | ✅ Alta (escalar en dirección de impresión según el grosor del cliché) | 4 |
| **Prueba de color en pantalla** (soft proof) | Pack Proof | 🟡 Media (simular sustrato y tintas; sin certificación Fogra) | 4 |
| **Tramado / RIP** | Imaging Engine, Harlequin | 🟠 Baja-media: vista previa del tramado sí; un RIP de producción certificado no | 5 |
| **Editor PDF nativo completo** | ArtPro+, PACKZ | 🔴 Muy costoso (años de trabajo). Mejor: herramientas puntuales sobre PDF, y seguir usando Illustrator para editar | — |
| **Automatización** (flujos por lotes) | Automation Engine, Cloudflow, Switch | ✅ Alta: "recetas" (preflight → separar → exportar) sobre carpetas | 5 |
| **Aprobación en línea** | WebCenter | 🟡 Requiere servidor en la nube; contradice "100% local". Opcional futuro. | — |
| **CAD estructural / 3D** | ArtiosCAD, Studio | 🔴 Fuera de alcance por ahora | — |
| **Planchas / hardware** | CDI, XPS | ❌ No aplica | — |

### Estándares que la suite debe respetar
- **PDF/X-4** (ISO 15930-7) y **PDF/X-1a**: formatos de intercambio. Especificaciones **Ghent Workgroup (GWG 2015/2022)**
  para el preflight.
- **ISO 12647-2** (offset), **-6** (flexo), **-5** (serigrafía): valores de color, TAC y ganancia de punto.
- **Fogra** (FOGRA39/51/52), **GRACoL/G7** (EE. UU.): condiciones de impresión y perfiles.
- **ISO 20654** (SCTV, tono de tintas directas) y **CxF** (intercambio de color de tintas).
- **GS1** para códigos de barras.

---

## 7. Arquitectura propuesta: "FAVERVIEW Suite"

Una sola app web local (la que ya existe), con **módulos en pestañas** y un núcleo compartido:

```
FAVERVIEW Suite  (uv run faverview → navegador)
├── Comparar        (ya existe)
├── Separar colores (PDF → placas · imagen → tintas)
├── Vectorizar
├── Preflight
├── Códigos de barras
└── Herramientas    (trapping, step & repeat, blanco, distorsión, braille)

Núcleo compartido (app/core/):
  carga de PDF/imagen · gestión de color (LittleCMS) · bibliotecas de tintas del usuario
  · render de separaciones (Ghostscript) · visor con zoom/capas · reportes PDF · historial · banco de pruebas
```

**Nuevas dependencias (todas gratis):**
| Paquete | Uso | Licencia |
|---|---|---|
| Ghostscript (winget `ArtifexSoftware.GhostScript`) | separaciones `tiffsep`, trapping de bitmap, render | AGPL |
| `vtracer` | vectorización a color (base) | MIT |
| `potracer` / Potrace | vectorización B/N (base) | GPL-2+ (compatible con AGPL-3) |
| `pikepdf` | editar PDF a bajo nivel | MPL-2.0 |
| `zxing-cpp` | leer/verificar códigos de barras | Apache-2.0 |
| `treepoem` (BWIPP) o `python-barcode` + `segno` | generar códigos de barras / QR | MIT / BSD |
| `louis` (liblouis) | braille | LGPL |
| ArgyllCMS (opcional) | crear perfiles ICC | AGPL |

---

## 8. Hoja de ruta sugerida

| Etapa | Contenido | Resultado |
|---|---|---|
| **S1** | Núcleo compartido + pestañas + visor de placas | Base de la suite |
| **S2** | **Separador PDF**: tintas, placas, TAC, densitómetro, mapeo de tintas, exportar | Primer módulo nuevo útil |
| **S3** | **Separador raster**: tintas planas, índice, proceso simulado, CMYK con GCR, base blanca, tramado | Serigrafía y flexo |
| **S4** | **Vectorizador** v1 (VTracer/Potrace + paleta controlada + fronteras compartidas + salida con tintas) y su banco de pruebas vs Illustrator/Corel | Primera comparación con números |
| **S5** | Vectorizador v2: primitivas (rectas, círculos, simetría), controles de preprensa, detección de texto | Superar a Image Trace en logos |
| **S6** | Preflight (reglas GWG) + códigos de barras | Control técnico |
| **S7** | Gama extendida, trapping, step & repeat, distorsión, braille | Herramientas avanzadas |
| **S8** | Automatización por lotes ("recetas") | Productividad |

Cada etapa lleva su **plan detallado para el agente** (como `PLAN_V2.md`), con pruebas y métricas.

---

## 9. Riesgos y límites honestos

- **Esko tiene décadas de desarrollo.** No vamos a igualar toda la suite. Sí podemos ser **mejores en módulos
  concretos** (separación raster, vectorización para preprensa, comparación) y **gratis**.
- **Pantone** requiere licencia: el usuario aporta sus bibliotecas.
- **Certificaciones** (Fogra, GWG, prueba de color contractual): no las tendremos al inicio. Nuestra prueba en
  pantalla es orientativa, no contractual.
- **Trapping estético** y un **RIP de producción** son problemas muy especializados. Se recomienda seguir usando el RIP
  del proveedor de planchas.
- **Licencias:** Ghostscript y PyMuPDF son AGPL, igual que FAVERVIEW. Todo encaja mientras el código siga
  siendo público.

---

## Fuentes

**Esko**
- [ArtPro+ – editor PDF nativo](https://www.esko.com/en/products/artpro-plus) · [Novedades ArtPro+ (Innovation Hub)](https://innovation.esko.com/en/labels-flexibles/artpro-plus) · [Guía de usuario ArtPro+ 24.07 (PDF)](https://docs.esko.com/docs/en-us/artproplus/24.07/userguide/pdf/artproplus.pdf)
- [Catálogo de productos Esko](https://www.esko.com/en/products) · [Automation Engine](https://innovation.esko.com/en/esko/home/products/automation-engine/features) · [Color Engine](https://esko.com/en/products/color-engine)
- [DeskPack](https://www.esko.com/en/products/deskpack) · [Paquetes DeskPack](https://site.esko.com/en/shop/software-overview/deskpack-plugins) · [Contenido de DeskPack Essentials](https://site.esko.com/en/downloads/trials/deskpack-essentials) · [Contenido de DeskPack Advanced](https://site.esko.com/en/downloads/trials/deskpack-advanced)
- [Guía de preprensa flexo (blog Esko)](https://www.esko.com/en/blog/flexo-prepress-full-guide) · [Panorama de la preprensa de empaque](https://www.esko.com/en/blog/the-complete-overview-of-packaging-prepress)
- [Plataforma Esko (CTGA)](https://www.ctgraphicarts.com/esko-software-platform) · [Esko en Wikipedia](https://en.wikipedia.org/wiki/Esko_(company))

**Competidores y comparativas**
- [PACKZ – Hybrid Software](https://hybridsoftware.com/products/packz/) · [PACKZ 9 (printing.org)](https://www.printing.org/content/2023/08/08/hybrid-software-s-packz-version-9-becomes-only-all-in-one-packaging-editor)
- [PrintPlanet: Esko o Kodak](https://printplanet.com/threads/esko-or-kodak.269879/) · [Hybrid PACKZ vs Esko](https://printplanet.com/threads/hybrid-packz-rip-vs-esko.291056/) · [Esko vs Hybrid](https://printplanet.com/threads/esko-vs-hybrid-workflow.293884/) · [Experiencia implementando Hybrid](https://printplanet.com/threads/follow-up-review-hybrid-software-implementation.294634/)
- [Hager Papprint con Hybrid Software](https://hybridsoftware.com/hager-papprint-optimizes-their-prepress-process-with-hybrid-software/)

**Alemán – callas pdfToolbox y Druckvorstufe**
- [callas pdfToolbox 10: nueva tecnología para la preprensa (print.de)](https://www.print.de/allgemein/druckvorstufe-preflight-erklimmt-naechste-technologie-stufe/) · [pdfToolbox 12 (print.de)](https://www.print.de/news-de/callas-software-veroeffentlicht-die-pdf-toolbox-version-12/)
- [Funciones de pdfToolbox Server (impressed)](https://www.impressed.de/produkte.php?c=detail&prnr=1271&link=fct&art=funktion) · [pdfToolbox para preprensa (Actino)](https://www.actino.de/produkte/callas-pdftoolbox-druckvorstufe/) · [pdfToolbox 15 (PDF Association)](https://pdfa.org/callas-software-veroffentlicht-pdftoolbox-15/)

**Separación para serigrafía**
- [Separation Studio (Freehand Graphics)](https://solutionsforscreenprinters.com/color-separation/) · [Manual Spot Process Separation Studio](https://solutionsforscreenprinters.com/wp-content/uploads/2018/11/2018-user-guide-sim-process.pdf)
- [Tipos de separación (UltraSeps)](https://m.ultraseps.com/types-of-color-separations-for-screen-printing/) · [Separaciones 101 – Scott Fresener](https://t-biznetwork.com/blogs/scottfresener/color-separations-101-scott-fresener/) · [Top 10 software de separación 2026](https://www.inksplit.com/post/top-10-color-separation-software-options-for-screen-printing-2025)

**Vectorización**
- [VTracer (GitHub)](https://github.com/visioncortex/vtracer) · [Alternativas a Image Trace 2026](https://vectosolve.com/blog/illustrator-image-trace-alternative-2026) · [Comparativa de vectorizadores](https://3dshouse.com/image-to-vector-tool-comparison/) · [Guía de software de vectorización 2026](https://www.svgvector.com/blog/image-to-vector-software-guide.html)

**Herramientas open source y estándares**
- [Ghostscript: dispositivos de salida (tiffsep)](https://ghostscript.readthedocs.io/en/latest/Devices.html) · [Ghostscript: trapping](https://ghostscript.com/features/trapping/) · [Little CMS](https://en.wikipedia.org/wiki/Little_CMS)
- [GWG: flujo PDF/X](https://gwg.org/pdf-x-workflow/) · [Formato PDF/X (Library of Congress)](https://www.loc.gov/preservation/digital/formats/fdd/fdd000124.shtml) · [Guía ISO/TC 130 de normas de producción](https://committee.iso.org/files/live/sites/tc130/files/Resources/Guidelines%20for%20using%20print%20production%20standards%20v2%20Jan%202024.pdf)
- [Certificaciones Fogra de preprensa](https://fogra.org/en/certification/prepress-technology) · [Datos de caracterización Fogra](https://fogra.org/en/downloads/work-tools/characterisation-data) · [Media Standard Print](https://en.wikipedia.org/wiki/Media_Standard_Print)
