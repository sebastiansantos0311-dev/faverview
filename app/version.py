"""Versión de FAVERVIEW (la fuente de verdad es `version` en pyproject.toml)."""
import re
from pathlib import Path


def get_version() -> str:
    try:
        text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        if m:
            return m.group(1)
    except Exception:
        pass
    try:
        from importlib.metadata import version
        return version("faverview")
    except Exception:
        return "desconocida"
