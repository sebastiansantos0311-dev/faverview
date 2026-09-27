# FAVERVIEW para Illustrator

Panel de Illustrator (CEP) que conecta con **FAVERVIEW** (la app local) para vectorizar, revisar (preflight), analizar separaciones, comparar con el
arte del cliente, revisar el registro/trap y generar códigos de barras y braille **sin salir de Illustrator**.

> **Idea clave:** el panel es solo un **puente**. Toda la lógica (imagen, color, vectorización, preflight, separación, trapping…) vive en FAVERVIEW.
> El panel exporta desde Illustrator → llama a la API local con un token → trae el resultado de vuelta al documento.

## Requisitos
- **Illustrator 2024 (v28), 2025 (v29) o 2026 (v30)**, en Windows (macOS: compatible, sin probar).
- **FAVERVIEW abierto** (acceso directo; versión 3.2 o superior). Ghostscript instalado para separaciones y trap.
- Nada más: no usa Node.js ni se conecta a internet (solo a `127.0.0.1`).

## Instalar (sin `.exe` propios)
1. Descarga `FAVERVIEW-Illustrator-<versión>.zxp` del último **Release** de GitHub (o pídeselo a quien lo firmó).
2. Ejecuta el instalador oficial de Creative Cloud desde PowerShell:
   ```powershell
   & "C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe" /install "C:\ruta\FAVERVIEW-Illustrator-3.2.0.zxp"
   ```
   *(Verifica la ruta en tu equipo: si no existe, busca `UnifiedPluginInstallerAgent.exe` dentro de `C:\Program Files\Common Files\Adobe`. Esta sintaxis y la de
   desinstalar están pendientes de confirmar en un equipo con Creative Cloud: anota en `PRUEBAS_MANUALES.md` lo que veas.)*
3. Reinicia Illustrator → **Ventana → Extensiones → FAVERVIEW**.

**Actualizar:** el panel te avisa en **Ajustes** cuando hay una versión nueva; instala el `.zxp` nuevo igual que arriba.
**Desinstalar:** `UnifiedPluginInstallerAgent.exe /remove com.faverview.illustrator` y reinicia Illustrator.

## Usar
1. Abre FAVERVIEW y luego Illustrator. El panel muestra 🟢 **Conectado a FAVERVIEW** (🔴 si FAVERVIEW no está abierto; reintenta solo cada 5 s).
2. Pestañas: **Vectorizar** · **Preflight** · **Separar** · **Comparar** · **Códigos** · **Trap** · **Ajustes**.
3. Nada modifica tu documento sin una acción explícita (colocar, corregir, marcar), y todo se puede deshacer con Ctrl+Z. Los análisis exportan una **copia** de la mesa
   a la carpeta temporal (`%TEMP%\FAVERVIEW`, se limpia a las 24 h).

| Pestaña | Qué hace |
|---|---|
| Vectorizar | Vectoriza la imagen seleccionada (preajustes, tintas de tu biblioteca, trap opcional) y coloca el vector **exactamente encima**. |
| Preflight | Revisa mesa(s) con un perfil; clic en un hallazgo → zoom y selección; marcadores; correcciones nativas (sobreimpresión, negro pequeño, unir/eliminar muestras). |
| Separar | Tintas del PDF frente a las muestras del documento, cobertura, TAC, placas y exportación. |
| Comparar | Arte del cliente (archivo o Ctrl+V) contra la mesa; marca las diferencias. |
| Códigos | Genera e inserta EAN/UPC/ITF/Code 128/GS1/DataMatrix/QR y braille; verifica los del documento. |
| Trap | Prueba de movimiento con la tolerancia de tu máquina; crea traps vectoriales (arte plano) en la capa «FAVERVIEW – Traps». |

## Si algo falla
| Síntoma | Qué hacer |
|---|---|
| El panel no aparece en Extensiones | Revisa que instalaste el `.zxp` **firmado** y reinicia Illustrator. Con un `.zxp` sin firmar Illustrator lo ignora (solo desarrollo con PlayerDebugMode). |
| El panel sale en blanco | Versión de CSXS: el manifest pide CSXS.11 (Illustrator 2024/2025) y funciona en CSXS.12 (2026). Actualiza Illustrator; en desarrollo, abre el depurador (puerto 8088) y mira la consola. |
| 🔴 «no conecta» con FAVERVIEW abierto | Cierra y abre FAVERVIEW; comprueba que existe `%APPDATA%\FAVERVIEW\plugin.json`; revisa el cortafuegos (solo tráfico local a `127.0.0.1`). |
| 🟡 «Versión incompatible» | Actualiza FAVERVIEW o el plugin (el mensaje dice cuál). |
| Aviso de editor no verificado al instalar | Un certificado propio es válido para CEP; anótalo en `PRUEBAS_MANUALES.md` y, si tu equipo lo permite, confirma la instalación. |
| «La mesa de trabajo está vacía» | El análisis exporta los objetos de la mesa activa: selecciona una mesa con contenido. |

## Firmar y publicar (quien mantiene el plugin)
1. Descarga **ZXPSignCmd** (herramienta oficial de Adobe, repositorio `Adobe-CEP/CEP-Resources`; no se incluye aquí).
2. Crea **una vez** tu certificado propio (guarda el `.p12` y su clave **fuera del repositorio**; `*.p12` está en `.gitignore`):
   ```powershell
   $env:ZXP_CERT_PASS = "una-clave-larga"
   uv run python plugin/tools/build_zxp.py --crear-certificado C:\seguro\cert.p12 --zxpsigncmd C:\herramientas\ZXPSignCmd.exe --pais CO --provincia Antioquia --organizacion "Mi taller" --nombre "FAVERVIEW"
   ```
3. Empaqueta, firma (con sello de tiempo) y verifica:
   ```powershell
   $env:ZXP_CERT_PASS = "una-clave-larga"
   uv run python plugin/tools/build_zxp.py --cert C:\seguro\cert.p12 --zxpsigncmd C:\herramientas\ZXPSignCmd.exe
   ```
   Sale `build/zxp/FAVERVIEW-Illustrator-<versión>.zxp` (la versión sale de `pyproject.toml`). Sin firma (CI): `--sin-firma`.
4. Publícalo como archivo adjunto de un **GitHub Release** (subiéndolo tú, o desde la CI si configuras el certificado en base64 y su clave como *secretos* del repositorio).

## Desarrollo
```powershell
uv run python plugin/tools/dev_install.py        # copia el panel y activa PlayerDebugMode (pide confirmación; solo desarrollo)
uv run python plugin/tools/dev_install.py --desinstalar
uv run pytest tests/test_plugin_servidor.py tests/test_plugin_js.py tests/test_plugin_panel_edge.py tests/test_plugin_estatico.py
node --test plugin/tests/host_mock/host.test.js
```
- El panel está en `plugin/cep/` (HTML/JS sin Node) y la capa host en `plugin/cep/host/` (ExtendScript ES3, **solo ASCII**: los acentos van como `\uXXXX`).
- Para depurar: crea `plugin/cep/.debug` con `<ExtensionList><Extension Id="com.faverview.illustrator.panel"><HostList><Host Name="ILST" Port="8088"/></HostList></Extension></ExtensionList>` y abre `http://localhost:8088` en Chrome. Está excluido del `.zxp` y de git.
- Seguridad: el servidor escribe un token en `%APPDATA%\FAVERVIEW\plugin.json`; toda petición con origen distinto del propio FAVERVIEW (o a `/api/plugin/*`) debe traer `X-FAVERVIEW-Token`. Una página web cualquiera no puede llamar a la API.
- Migración a UXP: ver `MIGRACION_UXP.md`.
