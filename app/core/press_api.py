"""Rutas de los perfiles de máquina (AUTOTRAP T0)."""
from fastapi import APIRouter

from app.core import press
from app.core.press import PressProfile

router = APIRouter(prefix="/api/prensas")


@router.get("")
def list_all():
    return {"perfiles": press.list_profiles(), "nota": press.NOTE}


@router.get("/{pid}")
def get_one(pid: str):
    return press.load(pid)


@router.put("/{pid}")
def put(pid: str, p: PressProfile):
    press.save(pid, p)
    return {"ok": True}


@router.delete("/{pid}")
def delete(pid: str):
    press.delete(pid)
    return {"ok": True}
