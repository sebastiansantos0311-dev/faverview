"""Catálogo de pasos de las recetas (S8). Cada paso recibe el contexto del archivo y sus parámetros."""
from dataclasses import dataclass, field
from pathlib import Path

from app.core import ghostscript
from app.core.errors import UserError

IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class StopRecipe(Exception):
    """Una condición de la receta detiene el proceso del archivo (no es un fallo técnico)."""


class StepError(Exception):
    pass


@dataclass
class Ctx:
    input: Path
    out_dir: Path
    path: Path = None                                   # archivo de trabajo actual (cambia al editar)
    log: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    outputs: list = field(default_factory=list)

    def __post_init__(self):
        self.path = self.path or self.input
        self.out_dir.mkdir(parents=True, exist_ok=True)

    @property
    def kind(self) -> str:
        return "pdf" if self.path.suffix.lower() == ".pdf" else "imagen"

    def say(self, msg: str):
        self.log.append(msg)

    def out(self, name: str) -> Path:
        p = self.out_dir / name
        self.outputs.append(p)
        return p


def _need(ctx: Ctx, kind: str, step: str):
    if ctx.kind != kind:
        raise StepError(f"El paso «{step}» necesita un archivo {kind.upper() if kind == 'pdf' else 'de imagen'} y se recibió un archivo {ctx.kind.upper() if ctx.kind == 'pdf' else 'de imagen'}.")


def _gs(step: str):
    if not ghostscript.available():
        raise StepError(f"El paso «{step}» necesita Ghostscript (ver la guía de instalación).")


# ---------------------------------------------------------------- pasos
def preflight(ctx: Ctx, perfil="offset_hoja", detener_si_errores=True, detener_si_advertencias=False, reporte_pdf=True):
    _need(ctx, "pdf", "preflight")
    from app.modules.preflight import engine, report
    res = engine.run_preflight(ctx.path, perfil)
    r = res["resumen"]
    ctx.data["preflight"] = res
    ctx.say(f"Preflight ({res['perfil']}): {r['error']} errores, {r['advertencia']} advertencias, {r['info']} avisos.")
    if reporte_pdf:
        ctx.out("preflight.pdf").write_bytes(report.build_report(ctx.path, res, ctx.input.name))
    if detener_si_errores and r["error"]:
        raise StopRecipe(f"El preflight encontró {r['error']} error(es): {'; '.join(f['mensaje'] for f in res['hallazgos'] if f['severidad'] == 'error')[:300]}")
    if detener_si_advertencias and r["advertencia"]:
        raise StopRecipe(f"El preflight tiene {r['advertencia']} advertencia(s) y la receta pide detenerse.")


def corregir(ctx: Ctx, correcciones=None, perfil="offset_hoja"):
    _need(ctx, "pdf", "corregir")
    from app.modules.preflight import fixes
    dst = ctx.out("corregido.pdf")
    r = fixes.apply_fixes(ctx.path, dst, correcciones or {"eliminar_anotaciones": True}, perfil)
    ctx.path = dst
    ctx.say(f"Correcciones aplicadas: {r['hecho']}. Parecido visual {r['similitud_visual'] * 100:.1f} %.")


def unir_duplicadas(ctx: Ctx):
    _need(ctx, "pdf", "separar.unir_duplicadas")
    from app.modules.separate import pdf_edit
    from app.modules.separate.pdf_inks import read_inventory
    inv = read_inventory(ctx.path)
    m = {v: i.name for i in inv.inks if len(i.variants) > 1 for v in i.variants if v != i.name}
    if not m:
        ctx.say("No había tintas duplicadas.")
        return
    dst = ctx.out("sin_duplicadas.pdf")
    r = pdf_edit.apply_edits(ctx.path, dst, rename=m)
    ctx.path = dst
    ctx.say(f"Se unieron {r['renombradas']} nombre(s) de tinta duplicados.")


def eliminar_no_usadas(ctx: Ctx):
    _need(ctx, "pdf", "separar.eliminar_no_usadas")
    from app.modules.separate import pdf_edit
    dst = ctx.out("sin_no_usadas.pdf")
    r = pdf_edit.apply_edits(ctx.path, dst, delete_unused=True)
    ctx.path = dst
    ctx.say(f"Se eliminaron {r['eliminadas']} tinta(s) sin uso.")


def convertir_a_proceso(ctx: Ctx, tintas=None):
    _need(ctx, "pdf", "separar.convertir_a_proceso")
    from app.modules.separate import pdf_edit
    if not tintas:
        raise StepError("Indica las tintas a convertir en el parámetro «tintas».")
    dst = ctx.out("convertido.pdf")
    r = pdf_edit.apply_edits(ctx.path, dst, convert=list(tintas))
    ctx.path = dst
    ctx.say(f"Se convirtieron {r['convertidas']} objeto(s) a CMYK.")


def exportar_placas(ctx: Ctx, dpi=600, formato="tiff8", pagina=1):
    _need(ctx, "pdf", "separar.exportar_placas")
    _gs("separar.exportar_placas")
    from app.modules.separate import analysis, export
    from app.modules.separate.pdf_inks import read_inventory
    from app.modules.separate.pdf_render import render_plates
    plates = render_plates(ctx.path, pagina - 1, dpi)
    inv = read_inventory(ctx.path)
    meta = {i.name: {"tipo": i.kind} for i in inv.inks}
    finds = [f.to_dict() for f in analysis.run_checks(plates, ctx.path, pagina - 1, inv, meta)]
    ctx.out("placas.zip").write_bytes(export.export_zip(plates, meta, formato, finds))
    ctx.say(f"Placas exportadas ({len(plates.names)} tintas a {plates.dpi:g} dpi, formato {formato}).")


def step_repeat(ctx: Ctx, hoja_ancho=300, hoja_alto=200, columnas=None, filas=None, gap_x=3, gap_y=3, margen=(10, 10, 10, 10),
                marcas=None, trabajo=""):
    _need(ctx, "pdf", "tools.step_repeat")
    from app.modules.tools import imposition
    dst = ctx.out("imposicion.pdf")
    r = imposition.step_repeat(ctx.path, dst, sheet_w=hoja_ancho, sheet_h=hoja_alto, cols=columnas, rows=filas, gap_x=gap_x, gap_y=gap_y,
                               margin=tuple(margen), marks=marcas or {}, job_name=trabajo or ctx.input.stem)
    ctx.path = dst
    ctx.say(f"Step & repeat: {r['repeticiones']} repeticiones, aprovechamiento {r['aprovechamiento_pct']} %.")


def distorsion_flexo(ctx: Ctx, distorsion_pct=None, k=None, repeticion=None, direccion="vertical"):
    _need(ctx, "pdf", "tools.distorsion_flexo")
    from app.modules.tools import flexo
    pct = distorsion_pct if distorsion_pct is not None else flexo.distortion_pct(float(k), float(repeticion))
    dst = ctx.out("distorsion_flexo.pdf")
    flexo.apply_distortion(ctx.path, dst, pct, direccion)
    ctx.path = dst
    ctx.say(f"Distorsión flexo aplicada: {pct:.2f} % ({direccion}).")


def trapping(ctx: Ctx, proceso="flexo", ancho_mm=None, dpi=600):
    _need(ctx, "pdf", "tools.trapping")
    _gs("tools.trapping")
    from app.modules.separate import export
    from app.modules.separate.pdf_inks import read_inventory
    from app.modules.separate.pdf_render import render_plates
    from app.modules.tools import trapping as tp
    plates = render_plates(ctx.path, 0, dpi)
    meta = {i.name: {"tipo": i.kind, "lab": i.lab} for i in read_inventory(ctx.path).inks}
    res = tp.trap(plates, meta, proceso=proceso, ancho_mm=ancho_mm)
    ctx.out("placas_con_trap.zip").write_bytes(export.export_zip(res.plates, meta, "tiff8", []))
    ctx.say(f"Trapping: {len(res.traps)} traps ({proceso}).")


def verificar_codigos(ctx: Ctx, dpi=600, exigir_codigos=False, detener_si_errores=True):
    from app.modules.barcodes import verify
    r = verify.verify(ctx.path, dpi)
    ctx.data["codigos"] = r
    errs = [a["mensaje"] for c in r["codigos"] for a in c["avisos"] if a["severidad"] == "error"]
    ctx.say(f"Códigos de barras: {len(r['codigos'])} detectado(s), {len(errs)} error(es).")
    if exigir_codigos and not r["codigos"]:
        raise StopRecipe("La receta exige un código de barras legible y no se encontró ninguno.")
    if detener_si_errores and errs:
        raise StopRecipe("Errores en códigos de barras: " + "; ".join(errs)[:300])


def vectorizar(ctx: Ctx, preset="logo", colores=None, ancho_mm=None, formatos=("svg", "pdf")):
    _need(ctx, "imagen", "vectorizar")
    from app.modules.separate import raster
    from app.modules.vectorize import export, pipeline
    rgb, dpi = raster.load_image(ctx.path)
    res = pipeline.vectorize(rgb, dpi[0] if dpi else None, preset=preset, **({"k_max": colores} if colores else {}))
    if "svg" in formatos:
        ctx.out("vector.svg").write_text(export.to_svg(res, ancho_mm), encoding="utf-8")
    if "pdf" in formatos or "eps" in formatos:
        pdf = export.to_pdf(res, ancho_mm, "separation", [i.name for i in res.palette])
        ctx.out("vector.pdf").write_bytes(pdf)
        if "eps" in formatos:
            ctx.out("vector.eps").write_bytes(export.to_eps(pdf))
    if "dxf" in formatos:
        ctx.out("vector.dxf").write_bytes(export.to_dxf(res, ancho_mm))
    ctx.say(f"Vectorizado ({preset}): {res.stats['trazados']} trazados, {res.stats['nodos']} nodos, {res.stats['colores']} colores.")


def separar_imagen(ctx: Ctx, modo="planas", colores=6, dpi_salida=600, trama=None):
    _need(ctx, "imagen", "separar.imagen")
    from app.modules.separate import raster, raster_export
    rgb, dpi = raster.load_image(ctx.path)
    d = dpi[0] if dpi else 200.0
    if modo == "planas":
        res = raster.separate_flat(rgb, d, None, colores)
    elif modo == "indice":
        res = raster.separate_index(rgb, None, colores)
    elif modo == "cmyk":
        res = raster.separate_cmyk(rgb)
    else:
        raise StepError("El modo automático solo admite planas, indice o cmyk (proceso necesita elegir las tintas en la pantalla).")
    ctx.out("separacion.zip").write_bytes(raster_export.export_zip(res, d, {"modo": modo}, {"kind": trama} if trama else None, True, dpi_salida))
    ctx.say(f"Imagen separada en {len(res.names)} canales (modo {modo}).")


def reporte(ctx: Ctx):
    lines = [f"Archivo: {ctx.input.name}", *ctx.log]
    ctx.out("resumen.txt").write_text("\n".join(lines), encoding="utf-8")
    ctx.say("Resumen escrito en resumen.txt.")


# nombre → (función, entrada, descripción, parámetros {nombre: (tipo, valor por defecto, ayuda)})
CATALOG = {
    "preflight": (preflight, "pdf", "Revisar el PDF con un perfil de preflight", {
        "perfil": ("perfil", "offset_hoja", "Perfil de preflight"), "detener_si_errores": ("bool", True, "Detener y mover a errores/ si hay errores"),
        "detener_si_advertencias": ("bool", False, "Detener también si hay advertencias"), "reporte_pdf": ("bool", True, "Guardar el reporte en PDF")}),
    "preflight.corregir": (corregir, "pdf", "Aplicar correcciones seguras", {
        "correcciones": ("json", {"eliminar_anotaciones": True, "unir_duplicadas": True}, "eliminar_anotaciones, unir_duplicadas, cajas, sobreimpresion_tecnicas"),
        "perfil": ("perfil", "offset_hoja", "Perfil para comprobar antes y después")}),
    "separar.unir_duplicadas": (unir_duplicadas, "pdf", "Unir tintas duplicadas", {}),
    "separar.eliminar_no_usadas": (eliminar_no_usadas, "pdf", "Eliminar tintas definidas sin uso", {}),
    "separar.convertir_a_proceso": (convertir_a_proceso, "pdf", "Convertir directas a CMYK", {"tintas": ("lista", [], "Nombres de las tintas")}),
    "separar.exportar_placas": (exportar_placas, "pdf", "Exportar las placas (ZIP)", {
        "dpi": ("numero", 600, "Resolución"), "formato": ("texto", "tiff8", "tiff8, tiff1 o pdf"), "pagina": ("numero", 1, "Página")}),
    "separar.imagen": (separar_imagen, "imagen", "Separar una imagen en tintas", {
        "modo": ("texto", "planas", "planas, indice o cmyk"), "colores": ("numero", 6, "Colores"), "dpi_salida": ("numero", 600, "dpi de las placas"),
        "trama": ("texto", "", "am o fm (vacío = sin tramado)")}),
    "vectorizar": (vectorizar, "imagen", "Vectorizar una imagen", {
        "preset": ("texto", "logo", "logo, linea, ilustracion, escaneo o foto"), "colores": ("numero", None, "Máx. de colores"),
        "ancho_mm": ("numero", None, "Ancho final en mm"), "formatos": ("lista", ["svg", "pdf"], "svg, pdf, eps, dxf")}),
    "tools.step_repeat": (step_repeat, "pdf", "Step & repeat en una hoja", {
        "hoja_ancho": ("numero", 300, "mm"), "hoja_alto": ("numero", 200, "mm"), "columnas": ("numero", None, "vacío = rellenar"),
        "filas": ("numero", None, "vacío = rellenar"), "gap_x": ("numero", 3, "mm"), "gap_y": ("numero", 3, "mm"),
        "marcas": ("json", {"registro": True, "corte": True, "barra_color": True, "texto": True}, "registro, corte, barra_color, microdots, texto")}),
    "tools.distorsion_flexo": (distorsion_flexo, "pdf", "Distorsión flexo", {
        "distorsion_pct": ("numero", None, "D % directo"), "k": ("numero", None, "Factor k (mm)"), "repeticion": ("numero", None, "Repetición (mm)"),
        "direccion": ("texto", "vertical", "vertical u horizontal")}),
    "tools.trapping": (trapping, "pdf", "Trapping por placas (ZIP)", {
        "proceso": ("texto", "flexo", "flexo, offset o serigrafia"), "ancho_mm": ("numero", None, "vacío = según el proceso"), "dpi": ("numero", 600, "dpi")}),
    "codigos.verificar": (verificar_codigos, None, "Verificar los códigos de barras", {
        "dpi": ("numero", 600, "dpi"), "exigir_codigos": ("bool", False, "Detener si no hay códigos"), "detener_si_errores": ("bool", True, "Detener si hay errores")}),
    "reporte": (reporte, None, "Escribir el resumen del archivo", {}),
}
