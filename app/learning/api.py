"""Rutas del aprendizaje del OCR (v2, fase 7)."""
import threading

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import load_config

router = APIRouter()

# ---------------------------------------------------------------------------------- aprendizaje (Fase 7)
_LEARN_LOG: dict = {"running": None, "log": [], "resultado": None}


def _bg(name: str, fn):
    """Ejecuta una tarea larga del aprendizaje en un hilo y guarda su registro."""
    import threading
    if _LEARN_LOG["running"]:
        raise HTTPException(409, f"Ya hay una tarea en curso: {_LEARN_LOG['running']}.")
    _LEARN_LOG.update(running=name, log=[], resultado=None)

    def run():
        try:
            _LEARN_LOG["resultado"] = fn(lambda *a: _LEARN_LOG["log"].append(" ".join(str(x) for x in a)))
        except Exception as e:
            _LEARN_LOG["resultado"] = {"ok": False, "mensaje": f"Error: {e}"}
        finally:
            _LEARN_LOG["running"] = None

    threading.Thread(target=run, daemon=True).start()


@router.get("/api/learning")
def learning_summary():
    from . import cli as lcli, confusions, tuning, vocab
    r = lcli.resumen()
    r["confusiones_lista"] = confusions.summary()[:60]
    r["vocabulario_lista"] = [{"palabra": w, "veces": c} for w, c in sorted(vocab.counts().items(), key=lambda kv: -kv[1])[:80]]
    r["autoajuste_en_curso"] = tuning.is_running()
    r["tarea"] = {"en_curso": _LEARN_LOG["running"], "registro": _LEARN_LOG["log"][-12:], "resultado": _LEARN_LOG["resultado"]}
    r["activo"] = load_config().get("learning_enabled", True)
    return r


@router.delete("/api/learning/confusion")
def learning_del_confusion(key: str):
    from . import confusions
    confusions.remove(key)
    return {"ok": True}


@router.delete("/api/learning/vocab")
def learning_del_vocab(word: str):
    from . import vocab
    vocab.remove_word(word)
    return {"ok": True}


@router.post("/api/learning/tune")
def learning_tune():
    from . import tuning
    _bg("Ajustando el preprocesado del OCR", lambda log: tuning.autotune(log=log))
    return {"ok": True}


@router.post("/api/learning/train")
def learning_train():
    from . import finetune

    def work(log):
        info = finetune.train(log=log)
        if info.get("ok"):
            info = finetune.ab_test(log=log)
        return info

    _bg("Re-entrenando el modelo de OCR", work)
    return {"ok": True}


class ModelToggle(BaseModel):
    activo: bool


@router.post("/api/learning/model")
def learning_model(body: ModelToggle):
    from . import finetune
    finetune.activate(body.activo)
    return {"ok": True, "activo": finetune.is_active()}


@router.get("/api/learning/export")
def learning_export(recortes: bool = False):
    from fastapi.responses import Response
    from . import portability
    return Response(portability.export_zip(recortes), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="aprendizaje_faverview.zip"'})


@router.post("/api/learning/import")
def learning_import(file: UploadFile = File(...)):
    from . import portability
    try:
        return {"ok": True, "agregado": portability.import_zip(file.file.read())}
    except Exception:
        raise HTTPException(400, "El archivo no es una exportación válida de aprendizaje.")


