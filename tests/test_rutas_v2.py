import json
from pathlib import Path

from app.main import app


def test_all_v2_urls_still_exist():
    """S0: el refactor no debe quitar ninguna URL de la v2 (lista guardada en tests/rutas_v2.json)."""
    esperado = json.loads((Path(__file__).parent / "rutas_v2.json").read_text(encoding="utf-8"))
    paths = app.openapi()["paths"]
    faltan = [(m, p) for m, p in esperado if p not in ("/", "/favicon.ico") and m.lower() not in paths.get(p, {})]
    assert not faltan, faltan
