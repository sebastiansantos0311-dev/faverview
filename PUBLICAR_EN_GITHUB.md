# Guía del dueño: mantener FAVERVIEW en GitHub

Repositorio **público**: https://github.com/sebastiansantos0311-dev/faverview
Cualquiera puede verlo e instalarlo siguiendo el `README.md`. Solo tú puedes modificarlo.

## Publicar cambios
Cada vez que mejores la app, en PowerShell:
```bash
cd $HOME\Desktop\FAVERVIEW; git add -A; git commit -m "Describe el cambio"; git push
```
Los demás equipos se actualizan con `git pull` (ver el README).

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
