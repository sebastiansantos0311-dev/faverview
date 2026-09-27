# FAVERVIEW para Illustrator – Pruebas manuales

Estas pruebas las ejecutas **tú en Illustrator** (yo no tengo Illustrator). Todo lo automatizable ya se ejecuta sin Illustrator
(`uv run pytest`: servidor, capa host con un mock de Illustrator, panel completo en Edge con CEP simulado). Aquí solo está lo que
**solo se puede comprobar con el programa real**.

**Antes de empezar**
1. Instala el panel (ver `README.md` de esta carpeta) y abre FAVERVIEW (acceso directo).
2. En Illustrator ejecuta **Archivo → Scripts → Otro script…** y elige `plugin/tests/archivos/crear_documento_de_prueba.jsx`: crea el documento de
   prueba (3 mesas desplazadas, una de ellas en posición negativa, con errores conocidos).
3. Anota tu versión de Illustrator y de FAVERVIEW. Si algo falla, adjunta una captura y el texto exacto del aviso.

Marca cada prueba con ✔ o ✘ y escribe observaciones. **No marques ✔ algo que no probaste.**

| # | Prueba | Pasos | Resultado esperado | ✔/✘ | Observaciones / captura |
|---|---|---|---|---|---|
| 1 | Instalar con UPIA | Instala el `.zxp` con el instalador de Creative Cloud (ver README) en Illustrator 2024, 2025 y 2026 (los que tengas) y reinicia | Aparece **Ventana → Extensiones → FAVERVIEW** y el panel abre con las 7 pestañas | | |
| 2 | Conexión | Con FAVERVIEW **cerrado**, abre el panel. Luego abre FAVERVIEW | Primero 🔴 «FAVERVIEW no está abierto» con instrucciones y botón Reintentar; al abrir FAVERVIEW pasa **solo** a 🟢 «Conectado a FAVERVIEW 3.x» (≤ 5 s) | | |
| 3 | Vectorizar un logo | Coloca un JPG de un logo **vinculado** y otro **incrustado y rotado 30°**. Selecciona uno, pestaña **Vectorizar → Vectorizar → Colocar sobre la imagen** | El vector cae **exactamente encima** (posición, tamaño y rotación), en la capa «FAVERVIEW – Vector». Las tintas aparecen como muestras spot **sin duplicados** (Ventana → Muestras) | | |
| 4 | Vectorizar con trap | Igual que la 3 marcando **Añadir trap** con el perfil «Serigrafía textil automática» | Existe el grupo de traps; en **Ventana → Previsualizar separaciones** los trazos de trap están en sobreimpresión | | |
| 5 | Preflight y zoom | Pestaña **Preflight**, perfil «Serigrafía» → **Revisar todas las mesas** en el documento de prueba. Haz clic en un hallazgo de la mesa 1 y en otro de la mesa 3 | Aparece una lista agrupada por severidad; el clic hace **zoom y selecciona** los objetos correctos en cada mesa (también en la mesa de posición negativa) | | |
| 6 | Correcciones nativas | Preflight → **Correcciones en Illustrator**: «Sobreimpresión en tintas técnicas» (Ver → Aplicar), «Unir muestras spot duplicadas» y «Eliminar muestras sin uso» | «Ver» muestra el nº de objetos; al aplicar, **Previsualizar separaciones** muestra el troquel en sobreimpresión, solo queda una muestra 485 y desaparece «Sin uso». Ctrl+Z deshace cada una | | |
| 7 | Separaciones | Pestaña **Separar → Analizar separaciones** en una mesa con CMYK+directas | Las tintas y el TAC coinciden con **Acrobat → Previsualización de salida** (± 1 %); avisa de la muestra sin uso y de las tintas sin muestra | | |
| 8 | Comparar | Elige un arte del cliente con **3 diferencias conocidas** frente a una mesa → **Comparar** | 3 marcadores en el lugar correcto (capa «FAVERVIEW – Revisión», que no se imprime); el clic en la lista hace zoom | | |
| 9 | Código EAN-13 | Pestaña **Códigos**: EAN-13 `590123412345` → **Insertar** | Se inserta centrado en la vista, como vector, en la tinta elegida; **escaneable con el celular** | | |
| 10 | Trap vectorial | Mesa 2 del documento de prueba (dos tintas que se tocan): pestaña **Trap** → **Analizar registro** (✘ con filetes) → **Crear traps vectoriales** → **Analizar registro** de nuevo. Repite en un arte con degradado | Primero «✘ … mm² de filetes»; tras crear los traps aparece la capa «FAVERVIEW – Traps» y el segundo análisis da «✔ Sin filetes con ±0,20 mm». Con degradado: mensaje del límite (usar placas con trap ráster) | | |
| 11 | Deshacer | Después de **Colocar** un vector (prueba 3), pulsa **Ctrl+Z** una vez | Vuelve al estado anterior con **un solo** Ctrl+Z (si necesitas más, anótalo) | | |
| 12 | Documento grande | Abre un documento con **más de 5 000 objetos** y usa Preflight (clic → zoom) y Marcar | Ninguna operación del panel congela Illustrator **más de 2 s**; si el documento es enorme aparece el aviso de límite | | |
| 13 | Desinstalar | Desinstala con UPIA (`/remove com.faverview.illustrator`, ver README) y reinicia | El panel desaparece del menú Extensiones | | |

## Comprobaciones extra recomendadas
- **Exportar sin tocar tu documento:** después de cualquier análisis, el nombre del documento y su ruta siguen iguales y no aparece marcado como modificado por el panel.
- **Tema:** cambia el tema de Illustrator (claro/oscuro) → el panel cambia sin reiniciar.
- **Firma propia:** anota si Creative Cloud mostró un aviso de «editor no verificado» al instalar (con captura).
- **Ruta de UPIA:** anota la ruta real de `UnifiedPluginInstallerAgent.exe` en tu equipo si difiere de la del README.

## Criterio de aceptación
≥ 12 de 13 pruebas en ✔ en **al menos una** versión de Illustrator; las ✘ documentadas con su plan de arreglo.
