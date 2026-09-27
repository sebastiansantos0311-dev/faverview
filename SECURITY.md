# Seguridad de FAVERVIEW

## Cómo reportar un problema de seguridad

**No abras un issue público.** Usa **Security → Report a vulnerability** en este repositorio (reporte privado de GitHub) y
describe el problema, cómo reproducirlo y la versión (`pie de la app` o `/api/version`). Responderemos lo antes posible.

## Diseño de seguridad (resumen)

| Tema | Cómo está protegido |
|---|---|
| Red | El servidor escucha **solo en `127.0.0.1`**: ningún otro dispositivo de la red ni de internet puede conectarse. |
| Otras páginas web | Toda petición con un origen distinto del propio FAVERVIEW (o marcada como *cross-site*) exige un token; aun con el token, solo se aceptan los orígenes del panel de Illustrator (CEP). Las peticiones con un `Host` ajeno se rechazan (defensa contra *DNS rebinding*). El botón «Actualizar» no se puede disparar desde otra web. |
| Plugin de Illustrator | Token aleatorio de 32 bytes guardado **solo en el equipo** (`%APPDATA%\FAVERVIEW\plugin.json`, nunca en el repositorio). El panel no usa Node.js y solo puede ejecutar en Illustrator las operaciones de una lista blanca. |
| Archivos | Identificadores y nombres de archivo validados (sin `..`, rutas absolutas ni separadores); importaciones ZIP sin *zip-slip*; XML (CxF) sin entidades externas (XXE); Ghostscript siempre con `-dSAFER`; ningún `shell=True`, `eval` ni `pickle`. |
| Datos | Archivos de clientes, resultados, aprendizaje, tintas y perfiles viven en `data/` y `datos_locales/`, excluidos de git. Nada sale del equipo. |
| Repositorio | Sin secretos (escaneo de secretos y protección de push de GitHub activados); certificados `.p12/.pfx`, `.zxp`, `.env`, claves y `plugin.json` en `.gitignore`; las pruebas de GitHub Actions corren con permisos de solo lectura. |

## Buenas prácticas para quien mantiene el proyecto

- Nunca subas archivos reales de clientes (`samples/` y `tests/` son públicos) ni el certificado del plugin y su clave.
- Antes de cada push: `git status` y revisar que no aparezca nada de `data/`, `datos_locales/`, `build/` ni certificados.
- Trabaja en ramas y publica con Pull Requests (ver la Guía del mantenedor).
