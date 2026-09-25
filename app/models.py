from typing import Literal

from pydantic import BaseModel, Field


class Difference(BaseModel):
    id: int = 0
    category: Literal["visual", "text", "spelling", "color", "font"]
    subtype: str | None = None
    bbox: tuple[int, int, int, int]  # x, y, w, h en píxeles del diseño
    severity: Literal["alta", "media", "baja"] = "media"
    message: str = ""
    expected: str | None = None  # lo que dice/tiene el cliente
    found: str | None = None  # lo que dice/tiene el diseño
    suggestions: list[str] = Field(default_factory=list)
    expected_hex: str | None = None
    found_hex: str | None = None
    delta_e: float | None = None
    review: Literal["pendiente", "real", "falso_positivo"] = "pendiente"  # revisión (Fase 5.3 / 7)
    status: Literal["pendiente", "corregido", "no_aplica"] = "pendiente"  # checklist (Fase 8.5)
    comment: str | None = None
    ocr_confidence: float | None = None
    ignored_by_zone: bool = False


class Result(BaseModel):
    job_id: str
    width: int
    height: int
    aligned: bool
    alignment_quality: float
    scores: dict[str, float]  # visual, text, color, spelling, font, total
    status: Literal["aprobado", "revisar", "con_errores"]
    differences: list[Difference]
    fonts_in_design: list[dict] = Field(default_factory=list)
    images: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    client_name: str = ""
    design_name: str = ""
    created: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)
    pages: dict = Field(default_factory=dict)
    elapsed_s: float = 0.0
    image_type: str | None = None  # exportado / whatsapp / foto / escaneo / captura
    color_spaces: dict[str, str] = Field(default_factory=dict)  # {"design": "CMYK", "client": "sRGB"}
    alignment_method: str | None = None  # orb / sift / ecc / manual
    template: str | None = None
    timings: dict[str, float] = Field(default_factory=dict)  # segundos por etapa
    learning_version: str | None = None
    client_text: str | None = None  # texto leído del arte del cliente (para medir CER)
    mode: str = "comparacion"  # "comparacion" (cliente vs diseño) | "versiones" (v1 vs v2 de mi diseño)
    fix_report: dict | None = None  # verificación de correcciones frente a una revisión anterior
