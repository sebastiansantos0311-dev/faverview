"""Rutas comunes: estado de trabajos, versión y actualizaciones."""
from fastapi import APIRouter, HTTPException

from app import updates
from app.core import jobs, tools
from app.core.files import check_job
from app.version import get_version

router = APIRouter()

@router.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    check_job(job_id)
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(404, "Trabajo no encontrado.")
    return j.public()


@router.get("/api/version")
def version():
    return {"version": get_version()}


@router.get("/api/update")
def update_status():
    return {**updates.status(), "version": get_version()}


@router.post("/api/update/apply")
def update_apply():
    return updates.apply()




@router.get("/api/status")
def status():
    """Versión, herramientas detectadas (con versión y ruta) y módulos habilitados."""
    herr = tools.status()
    modulos = {}
    for k, m in tools.MODULOS.items():
        faltan = [h for h in m["requiere"] if not herr[h]["ok"]]
        modulos[k] = {"nombre": m["nombre"], "habilitado": not faltan,
                      "aviso": ("Requiere " + ", ".join(faltan) + ": " + " ".join(herr[h]["ayuda"] for h in faltan))
                      if faltan else None}
    return {"version": get_version(), "herramientas": herr, "modulos": modulos}
