"""Validación de datos GS1: dígito de control (módulo 10) e identificadores de aplicación (AI) básicos."""
import re
from datetime import date

from app.core.errors import UserError

# AI → (nombre, longitud fija o None, longitud máxima, solo dígitos)
AIS = {
    "00": ("SSCC", 18, 18, True), "01": ("GTIN", 14, 14, True), "02": ("GTIN de contenido", 14, 14, True),
    "10": ("Lote", None, 20, False), "11": ("Fecha de producción (AAMMDD)", 6, 6, True),
    "13": ("Fecha de envasado (AAMMDD)", 6, 6, True), "15": ("Consumo preferente (AAMMDD)", 6, 6, True),
    "17": ("Caducidad (AAMMDD)", 6, 6, True), "20": ("Variante", 2, 2, True), "21": ("Número de serie", None, 20, False),
    "30": ("Cantidad variable", None, 8, True), "37": ("Cantidad de unidades", None, 8, True),
    "310": ("Peso neto (kg)", 6, 6, True), "320": ("Peso neto (lb)", 6, 6, True), "400": ("Pedido del cliente", None, 30, False),
    "410": ("Entregar a (GLN)", 13, 13, True), "414": ("Ubicación (GLN)", 13, 13, True), "8004": ("GIAI", None, 30, False),
}
DATE_AIS = {"11", "13", "15", "17"}


def check_digit(digits: str) -> int:
    """Dígito de control GS1 (módulo 10) de una cadena numérica SIN su dígito de control."""
    s = 0
    for i, ch in enumerate(reversed(digits)):
        s += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - s % 10) % 10


def valid_check(full: str) -> bool:
    return full.isdigit() and len(full) > 1 and check_digit(full[:-1]) == int(full[-1])


def ensure_check(digits: str, total: int, nombre: str) -> tuple[str, str | None]:
    """Acepta `total-1` dígitos (calcula el de control) o `total` (lo verifica). Devuelve (código completo, aviso)."""
    d = re.sub(r"\s", "", digits)
    if not d.isdigit():
        raise UserError(f"{nombre}: solo admite dígitos.")
    if len(d) == total - 1:
        return d + str(check_digit(d)), f"Se calculó el dígito de control: {check_digit(d)}."
    if len(d) == total:
        if not valid_check(d):
            raise UserError(f"{nombre}: el dígito de control es incorrecto (debería ser {check_digit(d[:-1])}).")
        return d, None
    raise UserError(f"{nombre}: debe tener {total - 1} dígitos (se calcula el de control) o {total} (se verifica). Tiene {len(d)}.")


def parse_ais(text: str) -> list[tuple[str, str]]:
    """Convierte «(01)0950…(17)250101(10)AB12» en [(AI, valor)]. Valida longitudes, fechas y dígito de control del GTIN."""
    pairs = re.findall(r"\((\d{2,4})\)([^(]*)", text)
    if not pairs or "".join(f"({a}){v}" for a, v in pairs) != text.strip():
        raise UserError("Escribe los datos GS1 con los AI entre paréntesis, por ejemplo (01)09501101530003(17)250101(10)AB12.")
    out = []
    for ai, val in pairs:
        key = ai if ai in AIS else (ai[:3] if ai[:3] in AIS else None)
        if key is None:
            raise UserError(f"El AI ({ai}) no está en la tabla básica de FAVERVIEW (00, 01, 02, 10, 11, 13, 15, 17, 20, 21, 30, 37, 310x, 320x, 400, 410, 414, 8004).")
        nombre, fixed, mx, digits = AIS[key]
        if digits and not val.isdigit():
            raise UserError(f"({ai}) {nombre}: solo admite dígitos.")
        if fixed and len(val) != fixed:
            raise UserError(f"({ai}) {nombre}: debe tener {fixed} caracteres y tiene {len(val)}.")
        if len(val) > mx or not val:
            raise UserError(f"({ai}) {nombre}: longitud máxima {mx}.")
        if ai in ("01", "02", "00") and not valid_check(val):
            raise UserError(f"({ai}) {nombre}: el dígito de control es incorrecto (debería ser {check_digit(val[:-1])}).")
        if ai in DATE_AIS:
            yy, mm, dd = int(val[:2]), int(val[2:4]), int(val[4:])
            try:
                date(2000 + yy, mm, dd if dd else 1)
            except ValueError:
                raise UserError(f"({ai}) {nombre}: fecha no válida ({val}).")
        out.append((ai, val))
    return out
