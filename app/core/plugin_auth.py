"""Autenticación del plugin de Illustrator (PLUGIN P0): token, archivo de conexión, CORS restringido y comprobación de Host/Origin.

El panel CEP lee `plugin.json` (puerto + token) de una ruta fija y manda el token en `X-FAVERVIEW-Token`. El propio frontend de
FAVERVIEW (mismo origen) no necesita token. Las páginas web de terceros no pueden llamar a la API aunque el servidor escuche en local."""
import json
import os
import secrets
import sys
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.version import get_version

API_VERSION = 1
HEADER = "X-FAVERVIEW-Token"
CEP_ORIGINS = {"null", "file://"}                    # orígenes con los que el Chromium de CEP hace peticiones
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}
PLUGIN_PREFIX = "/api/plugin"
_TOKEN: str | None = None


def plugin_file() -> Path:
    env = os.environ.get("FAVERVIEW_PLUGIN_JSON")
    if env:
        return Path(env)
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "FAVERVIEW" / "plugin.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FAVERVIEW" / "plugin.json"
    return Path.home() / ".config" / "FAVERVIEW" / "plugin.json"


def _read() -> dict:
    try:
        return json.loads(plugin_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_token() -> str:
    """Token de 32 bytes; se conserva entre arranques y se genera si no existe."""
    global _TOKEN
    if _TOKEN is None:
        t = _read().get("token")
        _TOKEN = t if isinstance(t, str) and len(t) >= 32 else secrets.token_urlsafe(32)
    return _TOKEN


def write_connection_file(port: int | None = None) -> Path:
    """Escribe/actualiza `plugin.json` (el puerto puede cambiar en cada arranque)."""
    port = int(port or os.environ.get("FAVERVIEW_PORT") or 8000)
    f = plugin_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"puerto": port, "token": get_token(), "version": get_version(), "pid": os.getpid()}, indent=1), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass
    return f


def token_ok(value: str | None) -> bool:
    return bool(value) and secrets.compare_digest(value.encode(), get_token().encode())


def _host_name(host_header: str) -> str:
    h = (host_header or "").strip().lower()
    if h.startswith("["):
        return h.split("]")[0] + "]"
    return h.split(":")[0]


def _is_self_origin(origin: str, host_header: str) -> bool:
    """El frontend propio: http://127.0.0.1:<puerto> o http://localhost:<puerto> del mismo servidor."""
    if not origin.startswith("http://"):
        return False
    return origin[len("http://"):] == (host_header or "").strip() and _host_name(host_header) in ALLOWED_HOSTS


class PluginGuard(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        if _host_name(host) not in ALLOWED_HOSTS:            # defensa contra DNS rebinding
            return JSONResponse({"detail": "Host no permitido."}, status_code=400)
        origin = request.headers.get("origin")
        site = request.headers.get("sec-fetch-site", "")
        path = request.url.path
        token = request.headers.get(HEADER)
        cep_origin = origin in CEP_ORIGINS if origin is not None else False

        if request.method == "OPTIONS" and origin is not None:     # preflight: no lleva token; solo se responde a CEP
            if not cep_origin:
                return Response(status_code=403)
            h = {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                 "Access-Control-Allow-Headers": f"Content-Type, {HEADER}", "Access-Control-Max-Age": "600", "Vary": "Origin"}
            if request.headers.get("access-control-request-private-network", "").lower() == "true":
                h["Access-Control-Allow-Private-Network"] = "true"
            return Response(status_code=204, headers=h)

        foreign = (origin is not None and not _is_self_origin(origin, host)) or site in ("cross-site", "same-site")
        needs_token = path.startswith(PLUGIN_PREFIX) or foreign
        if needs_token and not token_ok(token):
            return JSONResponse({"detail": "Falta el token de FAVERVIEW o no es válido."}, status_code=401)
        if foreign and origin is not None and not cep_origin:      # con token válido, pero desde una web cualquiera: no
            return JSONResponse({"detail": "Origen no permitido."}, status_code=403)
        resp = await call_next(request)
        if cep_origin and token_ok(token):
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition, X-Errores"
            resp.headers["Vary"] = "Origin"
        return resp
