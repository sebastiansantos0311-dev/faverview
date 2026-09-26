"""Unidades: mm, pt, pulgadas y píxeles a un dpi dado (1 in = 25.4 mm = 72 pt)."""
IN_MM = 25.4
IN_PT = 72.0


def mm_to_pt(mm: float) -> float:
    return mm * IN_PT / IN_MM


def pt_to_mm(pt: float) -> float:
    return pt * IN_MM / IN_PT


def mm_to_in(mm: float) -> float:
    return mm / IN_MM


def in_to_mm(inch: float) -> float:
    return inch * IN_MM


def px_to_mm(px: float, dpi: float) -> float:
    return px * IN_MM / dpi


def mm_to_px(mm: float, dpi: float) -> float:
    return mm * dpi / IN_MM


def pt_to_px(pt: float, dpi: float) -> float:
    return pt * dpi / IN_PT


def px_to_pt(px: float, dpi: float) -> float:
    return px * IN_PT / dpi


def ppi_at_size(pixels: float, size_mm: float) -> float:
    """Resolución efectiva (ppi) de una imagen de `pixels` colocada con `size_mm` de lado."""
    return pixels / (size_mm / IN_MM) if size_mm else 0.0


def scale_dpi(dpi_from: float, factor: float) -> float:
    return dpi_from * factor
