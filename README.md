# FAVERVIEW

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
3. Arrastra el arte del cliente (A) y tu diseño (B). Si algún PDF tiene varias páginas, elige la página.
4. Pulsa **Comparar**.
5. Revisa las vistas: lado a lado, deslizador, diferencia y superpuesto. Rueda del ratón = zoom; arrastrar = mover.
6. Haz clic en un error de la lista para hacer zoom en la zona. Usa los filtros, **Ignorar** o
   **Agregar al diccionario** (para marcas y nombres del cliente).
7. **Sensibilidad** → ajusta los umbrales y pulsa **Recalcular**.
8. **Descargar reporte PDF** genera el informe con miniaturas.
9. Para salir, cierra la ventana negra.

Colores: 🔴 texto · 🟡 ortografía · 🟠 color · 🔵 elemento visual · 🟣 fuente.
Semáforo: ≥ 98 % Aprobado · 90–98 % Revisar · < 90 % Con errores.

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
Los resultados y el historial se guardan en `data/`. Se conservan 30 días, y `data/uploads` se vacía al iniciar.

---

## Licencia

[AGPL-3.0](LICENSE). Usa PyMuPDF, que también se distribuye bajo AGPL.
