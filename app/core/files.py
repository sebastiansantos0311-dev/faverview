"""Subida, validación y ubicación de archivos por trabajo (compartido por todos los módulos)."""
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.loaders import ALLOWED_EXT, FileError, validate_file

JOB_RE = re.compile(r"^[0-9a-f]{12}$")
FILE_RE = re.compile(r"^[\w.\-]+$")


def check_job(job_id: str) -> None:
    if not JOB_RE.match(job_id):
        raise HTTPException(404, "Trabajo no encontrado.")


def save_upload(up: UploadFile, dest_dir: Path, stem: str, max_mb: float, allowed=ALLOWED_EXT, formats_msg: str = "") -> Path:
    """Guarda un archivo subido validando extensión y tamaño (en trozos, sin cargarlo entero en memoria)."""
    ext = Path(up.filename or "").suffix.lower()
    if ext not in allowed:
        raise FileError(f"Formato no admitido ({ext or 'sin extensión'}). "
                        + (formats_msg or "Usa JPG, PNG, WEBP, BMP, TIFF o PDF."))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stem}{ext}"
    limit = int(max_mb * 1024 * 1024)
    size = 0
    with open(dest, "wb") as f:
        while chunk := up.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise FileError(f"El archivo supera el máximo de {max_mb:g} MB.")
            f.write(chunk)
    validate_file(dest, max_mb)
    return dest


def find_upload(job_dir: Path, stem: str) -> Path:
    for p in job_dir.glob(f"{stem}.*"):
        return p
    raise FileError("Los archivos originales de este análisis ya no están disponibles. "
                    "Vuelve a subirlos para recalcular.")
