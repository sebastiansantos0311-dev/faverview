"""Rutas de la pantalla «Tintas»: bibliotecas del usuario (ver, importar, editar y exportar)."""
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from app.core import inks
from app.core.errors import UserError

router = APIRouter()
MAX_BYTES = 5 * 1024 * 1024


def _with_swatches(lib: inks.InkLibrary) -> dict:
    d = lib.model_dump()
    for raw, ink in zip(d["inks"], lib.inks):
        raw["swatch"] = ink.swatch_hex()
    return d


@router.get("/api/tintas")
def list_libs():
    return inks.list_libraries()


@router.get("/api/tintas/{nombre}")
def get_lib(nombre: str):
    return _with_swatches(inks.load_library(nombre))


@router.post("/api/tintas")
def save_lib(lib: inks.InkLibrary):
    return _with_swatches(inks.save_library(lib))


@router.post("/api/tintas-importar")
def import_lib(file: UploadFile = File(...), nombre: str = Form("")):
    """Lee una biblioteca (CxF, ASE, CSV o JSON). Con `nombre` la guarda (fusionando duplicados); sin él solo la muestra."""
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise UserError("El archivo de la biblioteca es demasiado grande (máx. 5 MB).")
    found = inks.dedupe(inks.import_any(file.filename or "", data))
    lib = inks.InkLibrary(name=nombre.strip() or (file.filename or "importada").rsplit(".", 1)[0], inks=found)
    if nombre.strip():
        try:
            prev = inks.load_library(lib.name)
            lib.inks = inks.dedupe(prev.inks + found)
        except UserError:
            pass
        inks.save_library(lib)
    return _with_swatches(lib)


@router.delete("/api/tintas/{nombre}")
def delete_lib(nombre: str):
    inks.delete_library(nombre)
    return {"ok": True}


@router.get("/api/tintas/{nombre}/exportar")
def export_lib(nombre: str, formato: str = "json"):
    lib = inks.load_library(nombre)
    if formato == "csv":
        body, mt, ext = inks.to_csv(lib), "text/csv", "csv"
    else:
        body, mt, ext = inks.to_json(lib), "application/json", "json"
    return Response(body.encode("utf-8"), media_type=mt,
                    headers={"Content-Disposition": f'attachment; filename="tintas.{ext}"'})
