"""Información técnica de un PDF: páginas, cajas (mm), OutputIntent, versión PDF/X, transparencias y capas."""
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pikepdf

from app.core.errors import UserError
from app.core.units import pt_to_mm


@dataclass
class PageBoxes:
    index: int
    media: tuple[float, float, float, float]   # x0, y0, x1, y1 en puntos
    crop: tuple[float, float, float, float]
    trim: tuple[float, float, float, float]
    bleed: tuple[float, float, float, float]
    has_trim: bool
    has_bleed: bool
    rotate: int = 0

    @staticmethod
    def _size_mm(b):
        return round(pt_to_mm(b[2] - b[0]), 2), round(pt_to_mm(b[3] - b[1]), 2)

    def to_dict(self) -> dict:
        return {"pagina": self.index + 1, "media_mm": self._size_mm(self.media), "crop_mm": self._size_mm(self.crop),
                "trim_mm": self._size_mm(self.trim), "bleed_mm": self._size_mm(self.bleed),
                "tiene_trimbox": self.has_trim, "tiene_bleedbox": self.has_bleed, "rotacion": self.rotate,
                "sangrado_mm": self.bleed_mm()}

    def bleed_mm(self) -> dict:
        """Sangrado disponible por lado = diferencia entre TrimBox y BleedBox."""
        return {"izq": round(pt_to_mm(self.trim[0] - self.bleed[0]), 2), "abajo": round(pt_to_mm(self.trim[1] - self.bleed[1]), 2),
                "der": round(pt_to_mm(self.bleed[2] - self.trim[2]), 2), "arriba": round(pt_to_mm(self.bleed[3] - self.trim[3]), 2)}


@dataclass
class PdfInfo:
    pages: int
    version: str
    encrypted: bool
    boxes: list[PageBoxes]
    output_intents: list[dict] = field(default_factory=list)
    pdfx_version: str | None = None
    has_transparency: bool = False
    transparency_pages: list[int] = field(default_factory=list)
    layers: list[dict] = field(default_factory=list)      # [{"nombre", "visible"}]
    title: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["boxes"] = [b.to_dict() for b in self.boxes]
        return d


def _box(page, key, default):
    try:
        v = page.get(key)
        if v is None and page.get("/Parent") is not None:
            v = page.Parent.get(key)   # las cajas se heredan del nodo padre
        if v is None:
            return default, False
        return tuple(float(x) for x in v), True
    except Exception:
        return default, False


def _open(path) -> pikepdf.Pdf:
    try:
        return pikepdf.open(str(path))
    except pikepdf.PasswordError:
        raise UserError("El PDF está protegido con contraseña.")
    except Exception:
        raise UserError("El PDF está dañado o no se puede abrir.")


def _page_has_transparency(page) -> bool:
    try:
        grp = page.get("/Group")
        if grp is not None and str(grp.get("/S")) == "/Transparency":
            return True
        res = page.get("/Resources")
        if res is None:
            return False
        gs = res.get("/ExtGState")
        if gs is not None:
            for _, st in gs.items():
                sm = st.get("/SMask")
                if sm is not None and str(sm) != "/None":
                    return True
                for k in ("/ca", "/CA"):
                    if k in st and float(st[k]) < 1.0:
                        return True
                bm = st.get("/BM")
                if bm is not None and str(bm) not in ("/Normal", "/Compatible"):
                    return True
        xo = res.get("/XObject")
        if xo is not None:
            for _, x in xo.items():
                if x.get("/SMask") is not None:
                    return True
    except Exception:
        pass
    return False


def read_pdf_info(path) -> PdfInfo:
    """Lee la estructura del PDF con pikepdf (no renderiza nada)."""
    pdf = _open(path)
    try:
        boxes, trans = [], []
        for i, page in enumerate(pdf.pages):
            pg = page.obj
            media, _ = _box(pg, "/MediaBox", (0.0, 0.0, 612.0, 792.0))
            crop, _ = _box(pg, "/CropBox", media)
            trim, has_trim = _box(pg, "/TrimBox", crop)
            bleed, has_bleed = _box(pg, "/BleedBox", crop)
            rot = int(pg.get("/Rotate", 0) or 0)
            boxes.append(PageBoxes(i, media, crop, trim, bleed, has_trim, has_bleed, rot))
            if _page_has_transparency(pg):
                trans.append(i + 1)

        intents = []
        root = pdf.Root
        for oi in (root.get("/OutputIntents") or []):
            def s(k):
                v = oi.get(k)
                return str(v) if v is not None else ""
            intents.append({"tipo": s("/S").lstrip("/"), "condicion": s("/OutputConditionIdentifier"),
                            "descripcion": s("/OutputCondition"), "registro": s("/RegistryName"),
                            "perfil_incrustado": oi.get("/DestOutputProfile") is not None})

        pdfx = None
        info = pdf.docinfo
        if info is not None and "/GTS_PDFXVersion" in info:
            pdfx = str(info["/GTS_PDFXVersion"])
        if pdfx is None:
            try:
                xmp = pdf.open_metadata()
                for k in ("pdfxid:GTS_PDFXVersion", "{http://www.npes.org/pdfx/ns/id/}GTS_PDFXVersion"):
                    if k in xmp:
                        pdfx = str(xmp[k])
                        break
            except Exception:
                pass

        layers = []
        ocp = root.get("/OCProperties")
        if ocp is not None:
            off = {id(x.objgen) for x in (ocp.get("/D", {}).get("/OFF") or [])}
            off_gens = {x.objgen for x in (ocp.get("/D", {}).get("/OFF") or [])}
            base_off = str(ocp.get("/D", {}).get("/BaseState", "/ON")) == "/OFF"
            on_gens = {x.objgen for x in (ocp.get("/D", {}).get("/ON") or [])}
            for g in (ocp.get("/OCGs") or []):
                hidden = (g.objgen in off_gens) or (base_off and g.objgen not in on_gens)
                layers.append({"nombre": str(g.get("/Name", "")), "visible": not hidden})

        title = str(info.get("/Title", "")) if info is not None else ""
        return PdfInfo(pages=len(pdf.pages), version=str(pdf.pdf_version), encrypted=pdf.is_encrypted, boxes=boxes,
                       output_intents=intents, pdfx_version=pdfx, has_transparency=bool(trans), transparency_pages=trans,
                       layers=layers, title=title)
    finally:
        pdf.close()


def page_size_mm(path, page: int = 0) -> tuple[float, float]:
    """Tamaño del TrimBox (o CropBox si no hay) de una página, en mm."""
    info = read_pdf_info(path)
    b = info.boxes[min(page, len(info.boxes) - 1)]
    return PageBoxes._size_mm(b.trim)
