import io
import threading
import time

import numpy as np
import pymupdf
import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageCms

from app.core import color_mgmt, ghostscript, jobs, reports
from app.core.errors import UserError
from app.core.files import check_job, find_upload, save_upload
from app.loaders import FileError


# ------------------------------------------------------------------------------------------ files
def _upload(name, data):
    return UploadFile(filename=name, file=io.BytesIO(data))


def test_save_upload_validates_extension_and_size(tmp_path):
    png = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(png, "PNG")
    p = save_upload(_upload("a.PNG", png.getvalue()), tmp_path / "j", "client", 1)
    assert p.name == "client.png" and p.exists()
    with pytest.raises(FileError, match="Formato no admitido"):
        save_upload(_upload("a.exe", b"x"), tmp_path / "j2", "client", 1)
    with pytest.raises(FileError, match="máximo"):
        save_upload(_upload("a.png", b"0" * (2 * 1024 * 1024)), tmp_path / "j3", "client", 1)
    assert not (tmp_path / "j3" / "client.png").exists()
    assert find_upload(tmp_path / "j", "client") == p
    with pytest.raises(FileError, match="ya no están"):
        find_upload(tmp_path / "vacio", "client")
    with pytest.raises(HTTPException):
        check_job("../../etc")
    check_job("0123456789ab")


# ------------------------------------------------------------------------------------------ jobs
def test_jobs_progress_done_and_errors():
    seen = []

    def ok(progress):
        progress("a", 0.5, "mitad")
        seen.append(1)
        return {"x": 1}

    j = jobs.start("aaaaaaaaaaaa", ok)
    for _ in range(50):
        if j.status != "running":
            break
        time.sleep(0.05)
    assert j.public()["status"] == "done" and j.public()["result"] == {"x": 1} and jobs.get("aaaaaaaaaaaa") is j

    def bad(progress):
        raise UserError("no se puede") if False else FileError("Archivo malo")

    j2 = jobs.start("bbbbbbbbbbbb", bad)
    time.sleep(0.3)
    assert j2.status == "error" and j2.error == "Archivo malo"

    def boom(progress):
        raise RuntimeError("interno")

    j3 = jobs.start("cccccccccccc", boom)
    time.sleep(0.3)
    assert j3.status == "error" and "error inesperado" in j3.error


# ------------------------------------------------------------------------------------------ color_mgmt
def test_color_mgmt_cmyk_icc_and_plain_paths(tmp_path):
    cmyk = Image.new("CMYK", (4, 4), (0, 255, 255, 0))
    rgb, space = color_mgmt.image_to_srgb(cmyk)
    assert "sin perfil" in space and rgb.getpixel((0, 0))[0] > 240
    # con perfil ICC incrustado (sRGB genérico creado por LittleCMS)
    prof = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    im = Image.new("RGB", (4, 4), (10, 20, 30))
    im.info["icc_profile"] = prof
    out, space = color_mgmt.image_to_srgb(im)
    assert out.mode == "RGB"
    # un perfil que NO es sRGB (Lab) se convierte
    lab = ImageCms.ImageCmsProfile(ImageCms.createProfile("LAB")).tobytes()
    im2 = Image.new("RGB", (4, 4), (10, 20, 30))
    im2.info["icc_profile"] = lab
    assert color_mgmt.image_to_srgb(im2)[0].mode == "RGB"
    # perfil CMYK por defecto inexistente → conversión estándar
    assert color_mgmt.image_to_srgb(cmyk, str(tmp_path / "no.icc"))[1].startswith("CMYK (sin perfil")
    # PDF: RGB vs CMYK
    doc = pymupdf.open()
    p = doc.new_page()
    p.draw_rect(pymupdf.Rect(10, 10, 100, 100), fill=(0.2, 0.8, 0.1, 0.1), color=None)
    f = tmp_path / "c.pdf"
    doc.save(f)
    assert color_mgmt.pdf_color_space(f).startswith("CMYK")
    assert color_mgmt.pdf_color_space(tmp_path / "no.pdf") == "desconocido"
    color_mgmt.enable_pdf_icc()


# ------------------------------------------------------------------------------------------ reports
def test_reports_helpers_build_a_real_pdf(tmp_path):
    img = np.zeros((120, 200, 3), np.uint8)
    img[20:60, 30:90] = (200, 30, 30)
    assert reports.jpg_bytes(img)[:2] == b"\xff\xd8" and reports.png_bytes(img)[:4] == b"\x89PNG"
    Image.fromarray(img).save(tmp_path / "x.png")
    assert reports.load_rgb(tmp_path / "x.png").shape == img.shape
    th = reports.thumb_pair(img, img, (30, 20, 60, 40))
    assert th.shape[0] > 10 and th.shape[1] > 20
    assert reports.clean_text("ΔE 3") == "dE 3" and reports.norm_color((255, 0, 51)) == (1.0, 0.0, 0.2)
    doc = pymupdf.open()
    reports.cover_page(doc, "Título Δ", ["línea 1", "línea 2"], ("Aprobado", (22, 163, 74)))
    pg = doc.new_page()
    y = reports.table(pg, 40, 40, ["A", "B"], [["uno", "2"], ["tres", "4"]], [100, 100])
    assert y > 40
    assert "Aprobado" in doc[0].get_text() and "tres" in doc[1].get_text()


# ------------------------------------------------------------------------------------------ ghostscript
@pytest.mark.skipif(not ghostscript.available(), reason="Ghostscript no instalado")
def test_ghostscript_cancel_and_timeout_kill_the_process(tmp_path):
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page().insert_text((50, 50), "x")
    f = tmp_path / "p.pdf"
    doc.save(f)
    # cancelación: se activa antes de empezar → se mata en el primer sondeo
    ev = threading.Event()
    ev.set()
    with pytest.raises(ghostscript.Cancelled):
        ghostscript.run_gs(["-sDEVICE=png16m", "-r2400", f"-sOutputFile={tmp_path}/o%d.png", str(f)], cancel=ev)
    # tiempo límite
    with pytest.raises(UserError, match="tardó más"):
        ghostscript.run_gs(["-sDEVICE=png16m", "-r4800", f"-sOutputFile={tmp_path}/t%d.png", str(f)], timeout=0.05)
    assert "Ghostscript" in ghostscript.translate_error("Error: /syntaxerror")
    assert "memoria" in ghostscript.translate_error("VMerror")
    assert ghostscript._version_key(r"C:\gs\gs10.08.0\bin\x") == (10, 8, 0)
