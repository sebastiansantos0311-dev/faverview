"""Exportar / importar el aprendizaje (ZIP) para llevarlo a otro equipo.

Por defecto solo incluye vocabulario, patrones, confusiones, ajustes y el modelo entrenado; NO incluye imágenes de
clientes (los recortes de entrenamiento son opcionales, con aviso de privacidad)."""
import io
import json
import zipfile
from pathlib import Path

from . import confusions, store, vocab

FILES = ["vocabulario.txt", "patrones.txt", "confusiones.json", "ajustes_ocr.json", "estado.json", "modelo_info.json"]


def export_zip(include_lines: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            p = store.path(name)
            if p.exists():
                z.write(p, name)
        model = store.path("modelos") / "spa_fv.traineddata"
        if model.exists():
            z.write(model, "modelos/spa_fv.traineddata")
        if include_lines:
            for f in (store.path("lineas")).glob("*"):
                z.write(f, f"lineas/{f.name}")
        z.writestr("LEEME.txt", "Exportación de aprendizaje de FAVERVIEW.\n"
                   + ("INCLUYE recortes de imágenes de clientes (datos privados).\n" if include_lines else
                      "No incluye imágenes de clientes.\n"))
    return buf.getvalue()


def _safe(name: str) -> bool:
    return not name.startswith(("/", "\\")) and ".." not in Path(name).parts and ":" not in name


def import_zip(data: bytes) -> dict:
    """Fusiona: suma frecuencias de vocabulario y conteos de confusiones; los ajustes/modelo se copian si faltan."""
    added = {"vocabulario": 0, "confusiones": 0, "ajustes": 0, "modelo": 0, "lineas": 0}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if _safe(n)]
        if "vocabulario.txt" in names:
            cur = vocab.counts()
            for ln in z.read("vocabulario.txt").decode("utf-8").splitlines():
                w, _, c = ln.partition("\t")
                if w.strip():
                    cur[w.strip().lower()] = cur.get(w.strip().lower(), 0) + (int(c) if c.strip().isdigit() else 1)
                    added["vocabulario"] += 1
            vocab._write(cur)
        if "patrones.txt" in names:
            p = store.path("patrones.txt")
            pats = set(p.read_text(encoding="utf-8").splitlines()) if p.exists() else set()
            pats |= set(z.read("patrones.txt").decode("utf-8").splitlines())
            p.write_text("\n".join(sorted(x for x in pats if x)) + "\n", encoding="utf-8")
        if "confusiones.json" in names:
            new = json.loads(z.read("confusiones.json").decode("utf-8"))
            cur = confusions.load()
            for k, v in new.get("pares", {}).items():
                cur["pares"][k] = cur["pares"].get(k, 0) + int(v)
                cur["ejemplos"].setdefault(k, new.get("ejemplos", {}).get(k, [])[:3])
                added["confusiones"] += 1
            store.save_json(confusions.FILE, cur)
        if "ajustes_ocr.json" in names:
            new = json.loads(z.read("ajustes_ocr.json").decode("utf-8"))
            cur = store.load_json("ajustes_ocr.json", {})
            for t, ent in new.items():
                if t not in cur or ent.get("cer_despues", 1) < cur[t].get("cer_despues", 1):
                    cur[t] = ent
                    added["ajustes"] += 1
            store.save_json("ajustes_ocr.json", cur)
        if "modelos/spa_fv.traineddata" in names:
            dst = store.path("modelos")
            dst.mkdir(exist_ok=True)
            (dst / "spa_fv.traineddata").write_bytes(z.read("modelos/spa_fv.traineddata"))
            added["modelo"] = 1
        for n in names:
            if n.startswith("lineas/") and not n.endswith("/"):
                d = store.path("lineas")
                d.mkdir(exist_ok=True)
                (d / Path(n).name).write_bytes(z.read(n))
                added["lineas"] += 1
    return added
