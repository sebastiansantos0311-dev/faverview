# FAVERVIEW

[![Pruebas](https://github.com/sebastiansantos0311-dev/faverview/actions/workflows/tests.yml/badge.svg)](https://github.com/sebastiansantos0311-dev/faverview/actions/workflows/tests.yml)

Compara el **arte del cliente** (JPG, PNG, WEBP, BMP, TIFF o PDF) con **tu diseño** (PDF exportado) y marca las
diferencias de texto, ortografía, color, elementos visuales y fuente. Todo corre en tu equipo y se usa desde el
navegador. Solo necesita internet durante la instalación.

> **¿Por qué no hay `.exe` ni `.bat`?** Windows y los antivirus marcan como sospechosos los ejecutables y scripts
> sin firma digital. FAVERVIEW se distribuye como código fuente desde GitHub y todo lo que se instala viene de
> **winget**, con paquetes oficiales y firmados. Así no aparecen avisos de virus.

---

## Instalación en un equipo nuevo (Windows 10/11)

Solo se hace **una vez**, y tarda entre 5 y 10 minutos.

### Paso 1 – Abrir PowerShell
Menú Inicio → escribe **PowerShell** → ábrelo. No hace falta abrirlo como administrador.

### Paso 2 – Instalar las herramientas
Copia y pega este comando y presiona Enter. Acepta los permisos si Windows los pide.
```bash
winget install -e --id astral-sh.uv; winget install -e --id Git.Git; winget install -e --id UB-Mannheim.TesseractOCR
```
- **uv**: descarga Python y las librerías de la app automáticamente.
- **Git**: descarga la app desde GitHub.
- **Tesseract**: lee el texto de las imágenes (OCR).

**Cierra PowerShell y ábrelo de nuevo** para que Windows reconozca los programas nuevos.

### Paso 3 – Descargar FAVERVIEW
Esto crea la carpeta `FAVERVIEW` en tu carpeta de usuario:
```bash
git clone https://github.com/sebastiansantos0311-dev/faverview.git $HOME\FAVERVIEW
```
> Si el repositorio es **privado**, Git abrirá una ventana para iniciar sesión en GitHub. Hazlo con tu cuenta.

### Paso 4 – Primer arranque
```bash
cd $HOME\FAVERVIEW; uv run faverview
```
La primera vez descarga Python y las librerías (unos minutos). Después se abre el navegador con la app.

### Paso 5 – Crear el acceso directo en el Escritorio (opcional)
```bash
cd $HOME\FAVERVIEW; uv run faverview --acceso-directo
```
Desde entonces basta con hacer **doble clic en "FAVERVIEW"** en el Escritorio.

---

## Uso diario

1. Doble clic en el acceso directo **FAVERVIEW**, o ejecuta `uv run faverview` dentro de la carpeta.
2. Se abre una ventana negra (el servidor) y el navegador con la app. **No cierres la ventana negra** mientras uses la app.
3. Arrastra el arte del cliente (A) y tu diseño (B). También puedes **pegar una imagen con Ctrl+V** o arrastrarla desde
   WhatsApp Web o el correo. Si algún PDF tiene varias páginas, elige la página.
4. Pulsa **Comparar**. Verás el progreso por etapas.
5. Revisa las vistas: lado a lado, deslizador, diferencia y superpuesto. Rueda del ratón = zoom; arrastrar = mover.
6. Haz clic en un error de la lista para hacer zoom en la zona. Usa los filtros, **Ignorar** o
   **Agregar al diccionario** (para marcas y nombres del cliente).
7. **Sensibilidad** → ajusta los umbrales y pulsa **Recalcular**.
8. **Descargar reporte PDF** genera el informe con miniaturas, el estado de cada error y tus comentarios.
9. Para salir, cierra la ventana negra.

Colores: 🔴 texto · 🟡 ortografía · 🟠 color · 🔵 elemento visual · 🟣 fuente.
Semáforo: ≥ 98 % Aprobado · 90–98 % Revisar · < 90 % Con errores.

### Funciones para el trabajo diario
| Función | Cómo se usa |
|---|---|
| **Zonas a ignorar** | En el visor pulsa **Ignorar zona**, elige *todo / solo color / solo texto* y dibuja un rectángulo. Lo que caiga dentro se oculta y no cuenta en el %. Pulsa **Guardar como plantilla…** para reutilizarla con ese cliente (se sugiere sola por el nombre del archivo o el tamaño). |
| **Alinear manualmente** | Si la alineación automática sale «mala» o «regular», marca 4 puntos equivalentes en cada imagen. |
| **Versiones de mi diseño** | En «Qué quieres comparar» elige *Versiones (v1 vs. v2)*: compara el texto exacto (sin OCR), fuentes, colores y el render de dos PDF tuyos. |
| **Verificar correcciones** | Con un resultado abierto pulsa **Verificar correcciones…** y sube el diseño corregido: te dice qué errores quedaron corregidos ✔, cuáles siguen ✘ y cuáles son nuevos. |
| **Todas las páginas** | Si los PDF tienen varias páginas aparece **Comparar todas las páginas**: empareja por orden (o por parecido visual si el número difiere), resume cada página y genera un solo reporte PDF. |
| **Checklist de aprobación** | Cada error tiene *Pendiente / Corregido / No aplica* y un comentario. Cuando no queda ninguno pendiente aparece **✔ Listo para enviar**. |
| **Aprendizaje** | El botón **Aprendizaje** muestra lo que el OCR ha aprendido de tus casos revisados (vocabulario, confusiones, ajustes, modelo) y permite exportarlo o importarlo en otro equipo. |

---

## Cómo aprende el OCR

Cada vez que guardas un caso revisado (**Modo revisión → Guardar como caso de prueba**) FAVERVIEW aprende, todo en local
(`datos_locales/aprendizaje/`, nunca se sube a GitHub):

1. **Vocabulario y patrones**: las marcas y nombres del diseño que no están en el diccionario dejan de marcarse como
   error y se le pasan a Tesseract (`--user-words`, `--user-patterns`).
2. **Confusiones**: si marcas un error de texto como *✘ Falso positivo*, se aprende qué letras suele confundir
   (`rn→m`, `l→i`, `e→é`…). Una diferencia que se explique solo con confusiones vistas 3+ veces aparece como
   «posible error de lectura» de severidad baja. **Nunca** se oculta un cambio de número (`10.000 → 12.000`).
3. **Ajuste por tipo de imagen** (exportado, WhatsApp, foto, escaneo, captura): cada 5 casos se busca el mejor
   preprocesado del OCR para cada tipo.
4. **Re-entrenamiento** (opcional, con 300+ líneas revisadas): ajusta el modelo español de Tesseract; solo se activa si
   mejora el banco de pruebas.

```bash
uv run faverview-aprender --resumen
```
```bash
uv run faverview-aprender --ajustar
```
```bash
uv run faverview-aprender --entrenar
```
También: `--original` (volver al modelo de fábrica), `--exportar aprendizaje.zip` y `--importar aprendizaje.zip`.

---

## Cómo crear casos de prueba

Cada caso que revises sirve para **medir** qué tan bien funciona la app y, más adelante, para que el OCR **aprenda**.
Los casos viven en `datos_locales/casos/` y **nunca se suben a GitHub** (son archivos de tus clientes).

1. Compara normalmente el arte del cliente con tu diseño.
2. Pulsa **Modo revisión** (barra sobre el visor).
3. En cada error de la lista marca **✔ Real** o **✘ Falso positivo**.
4. Si hay algo que la app **no detectó**, pulsa **Marcar error no detectado**, dibuja un rectángulo sobre la
   zona en el visor, elige la categoría y escribe lo que dice el cliente.
5. Elige el **tipo de arte** (exportado, WhatsApp, foto, escaneo, captura, CMYK, curvas) y, si quieres medir el
   OCR, transcribe el texto exacto del cliente.
6. Pulsa **Guardar como caso de prueba**. Se crea `datos_locales/casos/caso_NNN/`.

**Qué casos reunir (meta: 20)**

| Tipo de arte del cliente | Casos |
|---|---|
| PNG/JPG exportado limpio (sin errores) | 3 |
| PNG/JPG exportado con errores de texto (precio, fecha, nombre, teléfono) | 3 |
| Captura de WhatsApp | 3 |
| Foto con el celular (torcida, con luz) | 3 |
| Escaneo | 2 |
| PDF del cliente en CMYK | 2 |
| Texto pequeño, fondo de color o texto claro sobre oscuro | 2 |
| PDF de varias páginas | 1 |
| Diseño con el texto convertido a curvas | 1 |

Cada caso debería tener entre 0 y 8 errores conocidos, de categorías variadas.

**Medir la precisión**
```bash
uv run python -m bench.run --etiqueta "mi prueba"
```
Genera un reporte (`.md` y `.html`) en `datos_locales/bench_resultados/` con precisión, recall, F1, falsos
positivos por caso, CER del OCR y tiempos, comparado con la corrida anterior. Opciones: `--real`, `--sinteticos`,
`--caso caso_007`, `--workers 3`. Los 72 casos sintéticos (`tests/sinteticos/`) se regeneran con
`uv run python -m bench.synth`.

---

## Actualizar a la última versión


```bash
cd $HOME\FAVERVIEW; git pull
```
La próxima vez que abras la app, `uv` instalará lo que haga falta.

---

## Si algo falla

| Problema | Solución |
|---|---|
| *"winget no se reconoce"* | Instala **App Installer** desde Microsoft Store y vuelve a abrir PowerShell. |
| *"uv/git no se reconoce"* después del paso 2 | Cierra y vuelve a abrir PowerShell. Si sigue igual, reinicia el equipo. |
| Aviso *"no se encontró Tesseract"* | Ejecuta `winget install UB-Mannheim.TesseractOCR` y reinicia la app. |
| El navegador no se abre | Abre manualmente la dirección que aparece en la ventana negra (por ejemplo `http://127.0.0.1:8000`). |
| Puerto en uso | La app usa automáticamente el siguiente puerto libre (8001, 8002…); mira la ventana negra. |
| Descargaste el ZIP en vez de usar `git clone` | Antes de descomprimir: clic derecho en el ZIP → **Propiedades** → marca **Desbloquear** → Aceptar. |

Los valores de sensibilidad por defecto están en `config.json`.

---

## Desarrollo

```bash
uv run python tests/make_samples.py
```
```bash
uv run pytest
```
```bash
uv run python -m bench.run --sinteticos --etiqueta "mi cambio"
```
Cada `push` corre las pruebas y el banco de pruebas en GitHub Actions (pestaña *Actions*); el banco falla si el F1 de
alguna categoría baja más de 2 puntos respecto a `bench/umbral_ci.json`. Para fijar un umbral nuevo después de una
mejora: `uv run python -m bench.run --sinteticos --guardar-umbral`.

Los resultados y el historial se guardan en `data/`. Se conservan 30 días, y `data/uploads` se vacía al iniciar.
La app avisa (una vez al día, si hay internet) cuando hay una versión nueva; versión actual y cambios en
[CHANGELOG.md](CHANGELOG.md).

---

## Licencia

[AGPL-3.0](LICENSE). Usa PyMuPDF, que también se distribuye bajo AGPL.
