"""FAVERVIEW: crea la app, monta los routers de cada módulo y los archivos estáticos."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import history, updates
from app.config import DATOS_DIR, RESULTS_DIR, UPLOADS_DIR, WEB_DIR, setup_tesseract  # noqa: F401 (re-export)
from app.core import api as core_api
from app.core import inks_api
from app.learning import api as learning_api
from app.core.errors import UserError
from app.loaders import FileError
from app.modules.compare import api as compare_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    history.cleanup(30)
    setup_tesseract()
    updates.check_background()  # aviso de versión nueva (1 vez al día, sin bloquear el arranque)
    yield


app = FastAPI(title="FAVERVIEW", lifespan=lifespan)


@app.exception_handler(FileError)
async def file_error_handler(request, exc: FileError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(UserError)
async def user_error_handler(request, exc: UserError):
    return JSONResponse(status_code=400, content={"error": exc.message, "detail": exc.message})


@app.get("/favicon.ico")
def favicon():
    return FileResponse(WEB_DIR.parent / "assets" / "faverview.ico")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.include_router(core_api.router)
app.include_router(inks_api.router)
app.include_router(compare_api.router)
app.include_router(learning_api.router)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
