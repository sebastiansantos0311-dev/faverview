"""Perfiles de máquina (AUTOTRAP T0): tolerancia de movimiento (mal registro) y reglas de trapping por prensa.

Los valores de los perfiles de ejemplo son ORIENTATIVOS: mide el movimiento real de tu máquina con una prueba de registro."""
import re

from pydantic import BaseModel, Field, field_validator

from app.config import DATOS_DIR
from app.core.errors import UserError

PRESS_DIR = DATOS_DIR / "prensas"
NOTE = "Valores orientativos: mide el movimiento real de tu máquina con una prueba de registro."


class PressProfile(BaseModel):
    nombre: str = "Sin nombre"
    proceso: str = "serigrafia"                        # serigrafia | flexo | offset | digital
    tolerancia_mm: float | list[float] = 0.20          # escalar o [x, y] (x = ancho, y = dirección de impresión)
    factor_trap: float = 1.0
    trap_max_fraccion_objeto: float = 0.33
    choke_blanco_mm: float | None = None
    retraccion_negro_mm: float | None = None
    centrado_si_delta_L_menor_que: float = 8.0
    no_trapear_texto_menor_pt: float = 6.0
    direccion_impresion: str | None = "vertical"
    ejemplo: bool = False

    @field_validator("tolerancia_mm")
    @classmethod
    def _tol(cls, v):
        vals = v if isinstance(v, list) else [v]
        if len(vals) not in (1, 2) or any(x < 0 or x > 5 for x in vals):
            raise ValueError("La tolerancia debe estar entre 0 y 5 mm (un valor o [x, y]).")
        return v

    def tol_xy(self) -> tuple[float, float]:
        t = self.tolerancia_mm
        return (float(t[0]), float(t[-1])) if isinstance(t, list) else (float(t), float(t))

    def trap_xy(self) -> tuple[float, float]:
        x, y = self.tol_xy()
        return x * self.factor_trap, y * self.factor_trap

    def trap_mm(self) -> float:
        return max(self.trap_xy())

    def choke_mm(self) -> float:
        return self.choke_blanco_mm if self.choke_blanco_mm is not None else max(self.tol_xy())

    def pullback_mm(self) -> float:
        return self.retraccion_negro_mm if self.retraccion_negro_mm is not None else max(self.tol_xy())


EXAMPLES = {
    "serigrafia_textil_manual": PressProfile(nombre="Serigrafía textil manual", proceso="serigrafia", tolerancia_mm=0.40, ejemplo=True),
    "serigrafia_textil_automatica": PressProfile(nombre="Serigrafía textil automática", proceso="serigrafia", tolerancia_mm=0.20, ejemplo=True),
    "flexo_banda_angosta": PressProfile(nombre="Flexo banda angosta (etiquetas)", proceso="flexo", tolerancia_mm=0.15, ejemplo=True),
    "flexo_banda_ancha": PressProfile(nombre="Flexo banda ancha / corrugado", proceso="flexo", tolerancia_mm=0.25, ejemplo=True),
    "offset_pliego": PressProfile(nombre="Offset pliego", proceso="offset", tolerancia_mm=0.08, ejemplo=True),
    "digital": PressProfile(nombre="Digital (sin trap)", proceso="digital", tolerancia_mm=0.0, ejemplo=True),
}
DEFAULT_TOL = {"serigrafia": 0.20, "flexo": 0.15, "offset": 0.08, "digital": 0.0}


def _safe(pid: str) -> str:
    if not re.match(r"^[\w\- ]{1,60}$", pid or ""):
        raise UserError("El identificador del perfil de máquina solo admite letras, números, espacios, _ y -.")
    return pid


def list_profiles() -> list[dict]:
    out = [{"id": k, "nombre": v.nombre, "tolerancia_mm": v.tolerancia_mm, "proceso": v.proceso, "propio": False} for k, v in EXAMPLES.items()]
    if PRESS_DIR.exists():
        for f in sorted(PRESS_DIR.glob("*.json")):
            try:
                p = PressProfile.model_validate_json(f.read_text(encoding="utf-8"))
                out.append({"id": f.stem, "nombre": p.nombre, "tolerancia_mm": p.tolerancia_mm, "proceso": p.proceso, "propio": True})
            except Exception:
                pass
    return out


def load(pid: str) -> PressProfile:
    f = PRESS_DIR / f"{_safe(pid)}.json"
    if f.exists():
        return PressProfile.model_validate_json(f.read_text(encoding="utf-8"))
    if pid in EXAMPLES:
        return EXAMPLES[pid].model_copy()
    raise UserError("No existe ese perfil de máquina.")


def save(pid: str, p: PressProfile) -> None:
    PRESS_DIR.mkdir(parents=True, exist_ok=True)
    (PRESS_DIR / f"{_safe(pid)}.json").write_text(p.model_copy(update={"ejemplo": False}).model_dump_json(indent=1), encoding="utf-8")


def delete(pid: str) -> None:
    f = PRESS_DIR / f"{_safe(pid)}.json"
    if not f.exists():
        raise UserError("Solo se pueden borrar tus propios perfiles.")
    f.unlink()


def resolve(perfil: str | None = None, tolerancia_mm=None, proceso: str | None = None) -> PressProfile:
    """Perfil por id (o por proceso) y, si se indica, con otra tolerancia."""
    if perfil:
        p = load(perfil)
    else:
        proc = proceso or "serigrafia"
        p = PressProfile(nombre=f"Proceso {proc}", proceso=proc, tolerancia_mm=DEFAULT_TOL.get(proc, 0.2))
    if tolerancia_mm is not None:
        p = p.model_copy(update={"tolerancia_mm": tolerancia_mm})
    return p
