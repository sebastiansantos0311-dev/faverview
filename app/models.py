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
