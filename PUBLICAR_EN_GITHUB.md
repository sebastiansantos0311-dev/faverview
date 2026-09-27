# Guía del dueño: mantener FAVERVIEW en GitHub

Repositorio **público**: https://github.com/sebastiansantos0311-dev/faverview
Cualquiera puede verlo e instalarlo siguiendo el `README.md`. Solo tú puedes modificarlo.

## Publicar cambios
Todos los equipos se actualizan desde la rama `main` (la app avisa sola), así que **nunca subas a `main` algo sin probar**.
Trabaja en una rama y publica con un Pull Request:
```bash
git switch -c mejora/nombre
```
```bash
git add -A; git commit -m "Describe el cambio"; git push -u origin mejora/nombre
```
```bash
gh pr create --fill
```
GitHub Actions ejecuta todas las pruebas; fusiona el PR solo con la marca verde. El paso a paso completo (versiones, novedades que ve
el usuario, etiquetas, Releases y firma del plugin) está en la
[Guía del mantenedor](docs/Guia_del_mantenedor_FAVERVIEW.pdf).

## Privacidad
- Los commits usan el correo anónimo de GitHub (`…@users.noreply.github.com`), configurado solo en este repositorio.
- **Nunca** subas archivos de clientes reales: `data/uploads/`, `data/results/` y **`datos_locales/`** (casos de prueba
  reales, aprendizaje del OCR, plantillas y reportes del banco de pruebas) están excluidos en `.gitignore`.
  No pongas archivos reales en `samples/` ni en `tests/sinteticos/`, porque esas carpetas sí se publican.
  Antes de cada `git push` comprueba con `git status` que no aparezca nada de `datos_locales/`.

## Licencia
AGPL-3.0 (archivo `LICENSE`), compatible con PyMuPDF.

---

## Más adelante: instalador firmado (opcional, de pago)
Si algún día distribuyes FAVERVIEW a clientes o a muchos equipos sin conocimientos técnicos:
- Crea un instalador con **Inno Setup** (gratis) y **fírmalo** con **Azure Trusted Signing** (unos US$10/mes;
  la disponibilidad depende del país) o con un certificado OV/EV (US$200–500/año). Con eso, SmartScreen deja de avisar.
- También puedes empaquetarlo como **MSIX** y publicarlo en **Microsoft Store**, la opción sin ningún aviso.
