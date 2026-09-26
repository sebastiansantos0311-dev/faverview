"""PDF sintéticos con tintas directas para probar el separador (S2). Se construyen con pikepdf, sin archivos de clientes.

Uso:  uv run python -m bench.synth_separations [--out tests/sinteticos_sep]"""
import argparse
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, Pdf, String

PAGE_W, PAGE_H = 300, 200


def _fn2(c1, n=1):
    return Dictionary(FunctionType=2, Domain=Array([0, 1]), C0=Array([0, 0, 0, 0]), C1=Array(list(c1)), N=n)


class Builder:
    """Construye una página con espacios de color Separation/DeviceN y un contenido en operadores PDF."""

    def __init__(self, w=PAGE_W, h=PAGE_H):
        self.pdf = Pdf.new()
        self.w, self.h = w, h
        self.cs = {}
        self.ops: list[str] = []
        self.fonts = False
        self.gs = {}

    # ---- espacios de color
    def separation(self, key, name, alt_cmyk):
        self.cs[key] = Array([Name.Separation, Name("/" + name.replace(" ", "#20")) if False else Name("/" + _n(name)),
                              Name.DeviceCMYK, self.pdf.make_indirect(_fn2(alt_cmyk))])
        return key

    def devicen(self, key, names, colorants_cmyk):
        """DeviceN de 2 tintas (a, b) → CMYK con una función PostScript (tipo 4) lineal."""
        assert len(names) == 2 and len(colorants_cmyk) == 2
        (c1, m1, y1, k1), (c2, m2, y2, k2) = colorants_cmyk
        ps = (f"{{ 1 index {c1} mul 1 index {c2} mul add 2 index {m1} mul 2 index {m2} mul add "
              f"3 index {y1} mul 3 index {y2} mul add 4 index {k1} mul 4 index {k2} mul add 8 -4 roll pop pop pop pop }}")
        # (evaluada con cuidado: ver tests) usamos una versión más simple y verificable:
        ps = ("{ 2 copy 0 mul exch 0 mul add pop "  # (no-op para demostrar copy)
              f"1 index {c1} mul 1 index {c2} mul add "
              f"2 index {m1} mul 2 index {m2} mul add "
              f"3 index {y1} mul 3 index {y2} mul add "
              f"4 index {k1} mul 4 index {k2} mul add "
              "6 -2 roll pop pop }")
        fn = self.pdf.make_stream(ps.encode("latin-1"))
        fn["/FunctionType"] = 4
        fn["/Domain"] = Array([0, 1, 0, 1])
        fn["/Range"] = Array([0, 1, 0, 1, 0, 1, 0, 1])
        self.cs[key] = Array([Name.DeviceN, Array([Name("/" + _n(n)) for n in names]), Name.DeviceCMYK, fn])
        return key

    def extgstate(self, key, **kw):
        self.gs[key] = Dictionary(**{k: v for k, v in kw.items()})

    # ---- contenido
    def raw(self, s):
        self.ops.append(s)

    def rect(self, x, y, w, h, color: str):
        """color: 'C M Y K k' (DeviceCMYK), 'g'/'rg' u operador con espacio: '/CS0 cs 1 scn'."""
        self.ops.append(f"{color} {x} {y} {w} {h} re f")

    def text(self, x, y, size, s, color="0 0 0 1 k"):
        self.fonts = True
        self.ops.append(f"BT {color} /F1 {size} Tf {x} {y} Td ({s}) Tj ET")

    def build(self, path):
        pdf = self.pdf
        res = Dictionary(ColorSpace=Dictionary(**{k: v for k, v in self.cs.items()}))
        if self.fonts:
            res["/Font"] = Dictionary(F1=pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)))
        if self.gs:
            res["/ExtGState"] = Dictionary(**{k: v for k, v in self.gs.items()})
        page = pdf.add_blank_page(page_size=(self.w, self.h))
        page.obj["/Resources"] = res
        page.obj["/Contents"] = pdf.make_stream("\n".join(self.ops).encode("latin-1"))
        pdf.save(path)
        return path


def _n(name: str) -> str:
    """Nombre PDF (Name) válido: los espacios se codifican como #20 automáticamente por pikepdf."""
    return name


def patches_pdf(path: Path) -> Path:
    """Parches al 0/25/50/75/100 % de Cyan y de una tinta directa «Demo Rojo 1» (para probar la convención de valores)."""
    b = Builder()
    b.separation("CS0", "Demo Rojo 1", (0.0, 0.9, 0.8, 0.05))
    for i, t in enumerate((0, 0.25, 0.5, 0.75, 1.0)):
        b.rect(10 + i * 50, 110, 40, 40, f"{t} 0 0 0 k")           # Cyan
        b.rect(10 + i * 50, 30, 40, 40, f"/CS0 cs {t} scn")        # tinta directa
    return b.build(path)


def suite_pdf(path: Path, case: str) -> Path:
    """Casos de la §6.7 del plan. `case`: limpio, completo."""
    b = Builder()
    b.separation("CS0", "Demo Rojo 1", (0.0, 0.9, 0.8, 0.05))
    b.separation("CS1", "Demo 485C", (0.0, 0.85, 0.9, 0.0))
    if case != "limpio":
        b.separation("CS2", "DEMO 485 C", (0.0, 0.85, 0.9, 0.0))          # duplicado por nombre
        b.separation("CS3", "Demo Sin Usar", (0.5, 0.0, 0.5, 0.0))       # definida pero sin objetos
        b.separation("CS4", "Blanco", (0.0, 0.0, 0.0, 0.0))
    b.devicen("CS5", ["Demo Azul", "Demo Verde"], [(0.8, 0.4, 0.0, 0.0), (0.5, 0.0, 0.9, 0.0)])
    b.rect(10, 120, 60, 40, "0.6 0.1 0 0 k")                               # CMYK
    b.rect(80, 120, 60, 40, "/CS0 cs 1 scn")
    b.rect(150, 120, 60, 40, "/CS1 cs 0.7 scn")
    b.rect(220, 120, 60, 40, "/CS5 cs 1 0.5 scn")
    b.text(10, 80, 12, "Texto normal 12 pt", "0 0 0 1 k")
    if case != "limpio":
        b.rect(10, 20, 60, 40, "/CS2 cs 1 scn")                          # usa el duplicado
        b.rect(80, 20, 60, 40, "/CS4 cs 1 scn")                          # blanco (knockout por defecto)
        b.text(150, 50, 5, "Texto 5pt en 4 colores", "1 1 1 1 k")        # texto pequeño en 4 tintas
        b.text(150, 30, 9, "Negro enriquecido", "0.6 0.5 0.5 1 k")       # negro enriquecido en texto
        b.rect(220, 20, 60, 40, "1 1 1 0.4 k")                           # TAC 340 %
    return b.build(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "tests" / "sinteticos_sep")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    patches_pdf(a.out / "parches.pdf")
    suite_pdf(a.out / "limpio.pdf", "limpio")
    suite_pdf(a.out / "completo.pdf", "completo")
    print("PDF sintéticos en", a.out)


if __name__ == "__main__":
    main()
