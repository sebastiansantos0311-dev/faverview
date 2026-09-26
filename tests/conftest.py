import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


import pytest


@pytest.fixture(autouse=True)
def _datos_locales_aislado(tmp_path_factory, monkeypatch):
    """Ninguna prueba debe escribir en el datos_locales real (casos, aprendizaje, plantillas): se redirige a una
    carpeta temporal."""
    tmp = tmp_path_factory.mktemp("datos_locales")
    import app.config as config
    monkeypatch.setattr(config, "DATOS_DIR", tmp)
    for modname in ("app.learning.store", "app.learning.tuning", "app.ignore_zones", "app.main", "app.updates",
                    "app.modules.compare.api"):
        try:
            mod = __import__(modname, fromlist=["x"])
        except Exception:
            continue
        if hasattr(mod, "DATOS_DIR"):
            monkeypatch.setattr(mod, "DATOS_DIR", tmp)
    try:
        import app.updates as updates
        monkeypatch.setattr(updates, "STATE", tmp / "actualizaciones.json")
    except Exception:
        pass
    try:
        import app.learning.vocab as vocab
        vocab._cache["mtime"] = None
    except Exception:
        pass
