# Decisiones de diseño (v3, suite)

Formato: fecha · contexto · decisión · alternativa descartada.

## 2026-09-25 · Módulos puente con `sys.modules` (S0)
- **Contexto:** al mover el código de Comparar a `app/modules/compare/` los tests (y algún import antiguo) siguen usando
  `app.pipeline`, `app.spelling`, `app.jobs`… y hacen `monkeypatch.setattr` sobre esos módulos.
- **Decisión:** dejar en el sitio antiguo un módulo puente que sustituye su propia entrada de `sys.modules` por el módulo
  real (`sys.modules[__name__] = _real`). Así `app.pipeline is app.modules.compare.pipeline` y los monkeypatch funcionan.
- **Descartado:** `from … import *` (crea una copia: los monkeypatch dejan de afectar al módulo real).

## 2026-09-25 · Tests modificados en S0 (inevitable)
- `tests/test_bench.py::test_save_review_as_case` y `tests/test_learning.py::test_reviewed_case_feeds_learning_and_line_export`
  parchean `DATOS_DIR` en `app.main`; las rutas de Comparar ahora viven en `app.modules.compare.api`, así que el parche
  apunta allí. Comportamiento idéntico. `tests/conftest.py` aísla también ese módulo.

## 2026-09-25 · Versión y etiquetas de la v3
- PEP 440 no admite `3.0.0-s0`; `pyproject.toml` usa `3.0.0.devN` durante las etapas (`3.0.0.dev0` = S0…) y las etiquetas
  git son `v3.0.0-s0`, `v3.0.0-s1`… Al terminar S8: `3.0.0` y `v3.0.0`.

## 2026-09-25 · Ghostscript por instalador oficial
- No está en winget. Se instala con el comando del README (descarga de Artifex + verificación Authenticode + `/S`).
  Se detecta en `PATH`, `C:\Program Files\gs\gs*\bin` o `config.json → ghostscript_cmd`. Sin él, los módulos que lo
  necesitan se desactivan con un aviso y el resto funciona.

## 2026-09-25 · `liblouis` (`louis`) no se usa
- El paquete `louis` de PyPI no trae liblouis para Windows; S7.4 usa una **tabla propia de braille español grado 1**
  (permitido por el plan).

## 2026-09-25 · Manual de usuario de la suite
- El PDF del manual se regenera al cerrar la suite (S8) con un capítulo por módulo y capturas; cada etapa deja su sección
  en `CHANGELOG.md` y sus pantallas probadas. Motivo: las capturas cambian con la interfaz definitiva.

## 2026-09-25 · Ghostscript devuelve 0 aunque falle
- `run_gs` también trata como error los mensajes «Couldn't initialise file» y «Unrecoverable error» (aunque el código de
  salida sea 0). Los «Error: … Output may be incorrect» recuperables no se consideran fallo.

## 2026-09-25 · Espacio de trabajo del modelo de mezcla de tintas (S1)
- **Contexto:** el cian FOGRA (Lab 55, −37, −50) está fuera de sRGB; mezclar en sRGB lineal da negativos y el modelo
  no devuelve el sólido con t = 1.
- **Decisión:** el modelo (`colorscience.mix_inks`) trabaja en **ProPhoto RGB lineal (D50)**, que contiene las tintas de
  impresión. Se mantiene el factor n de Yule–Nielsen. Es orientativo (no espectral).
- **Descartado:** sRGB lineal (pierde gama), XYZ directo (la mezcla multiplicativa por canal pierde sentido físico).

## 2026-09-25 · Valores Lab de la biblioteca incorporada
- Cian 55/−37/−50, magenta 48/74/−3, amarillo 89/−5/93, negro 16/0/0 y papel 95/0/−2: valores de referencia públicos de
  ISO 12647-2 PC1 (FOGRA51). Se documentan como referencia de la caracterización, no de una tinta concreta.

## 2026-09-25 · Importadores de bibliotecas
- CSV: el delimitador se decide por la primera línea (`;` si aparece, así los decimales pueden llevar coma).
  CxF: solo se lee el bloque `ColorCIELab` de cada `Object` (sin resolver entidades XML). ASE: Lab/RGB/CMYK/Gray; el CMYK
  se convierte a Lab con el modelo de mezcla y las tintas de proceso de referencia.
