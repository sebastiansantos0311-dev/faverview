"""Trabajos en segundo plano con progreso por etapas (la interfaz consulta /api/jobs/{id})."""
import threading
import time
import traceback
from dataclasses import dataclass, field

from app.loaders import FileError

_LOCK = threading.Lock()
_MAX = 60


@dataclass
class Job:
    id: str
    status: str = "running"  # running | done | error
    stage: str = "cargar"
    message: str = "Iniciando…"
    pct: float = 0.0
    result: dict | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)
    started: float = field(default_factory=time.time)

    def public(self) -> dict:
        d = {"job_id": self.id, "status": self.status, "stage": self.stage, "message": self.message,
             "pct": round(self.pct, 3), "error": self.error, "extra": self.extra}
        if self.status == "done":
            d["result"] = self.result
        return d


JOBS: dict[str, Job] = {}


def get(job_id: str) -> Job | None:
    return JOBS.get(job_id)


def start(job_id: str, fn, extra: dict | None = None) -> Job:
    """Ejecuta `fn(progress)` en un hilo. `progress(stage, pct, message)` actualiza el estado."""
    job = Job(job_id, extra=extra or {})
    with _LOCK:
        JOBS[job_id] = job
        for old in sorted(JOBS.values(), key=lambda j: j.started)[:-_MAX]:
            if old.status != "running":
                JOBS.pop(old.id, None)

    def progress(stage: str, pct: float, message: str = "") -> None:
        job.stage, job.pct = stage, pct
        if message:
            job.message = message

    def run():
        try:
            job.result = fn(progress)
            job.pct, job.status = 1.0, "done"
        except FileError as e:
            job.status, job.error = "error", str(e)
        except Exception as e:  # nunca dejar la interfaz esperando para siempre
            traceback.print_exc()
            job.status, job.error = "error", f"Ocurrió un error inesperado al comparar ({type(e).__name__}: {e})."

    threading.Thread(target=run, daemon=True).start()
    return job
