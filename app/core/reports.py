"""Utilidades comunes de reporte PDF (PyMuPDF): portada, tablas, miniaturas, imágenes y textos seguros."""
from pathlib import Path

import cv2
import numpy as np
import pymupdf

A4 = (595, 842)


def norm_color(c) -> tuple:
    """RGB 0–255 → 0–1 (lo que espera PyMuPDF)."""
    return tuple(v / 255 for v in c)


def clean_text(t: str | None) -> str:
    """Las fuentes base de PDF no tienen Δ: se sustituye por «d»."""
    return (t or "").replace("ΔE", "dE").replace("Δ", "d")


def jpg_bytes(img: np.ndarray, quality: int = 82) -> bytes:
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


def png_bytes(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return buf.tobytes()


def load_rgb(path: Path) -> np.ndarray:
    """Lee una imagen (con rutas con acentos) como RGB."""
    data = np.frombuffer(Path(path).read_bytes(), np.uint8)
    return cv2.cvtColor(cv2.imdecode(data, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def thumb_pair(a: np.ndarray, b: np.ndarray, bbox, pad: int = 12, max_w: int = 150, max_h: int = 60) -> np.ndarray:
    """Miniatura de una zona en dos imágenes (a | b), lado a lado."""
    H, W = b.shape[:2]
    x, y, w, h = bbox
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    tiles = []
    for im in (a, b):
        c = im[y0:y1, x0:x1]
        s = min(max_w / max(c.shape[1], 1), max_h / max(c.shape[0], 1), 3.0)
        tiles.append(cv2.resize(c, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC))
    hh = max(t.shape[0] for t in tiles)
    padded = [cv2.copyMakeBorder(t, 0, hh - t.shape[0], 0, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
    return np.hstack(padded)


def cover_page(doc: pymupdf.Document, title: str, lines: list[str], status: tuple[str, tuple] | None = None):
    """Portada sencilla: título, líneas de texto y (opcional) semáforo (texto, RGB 0–255)."""
    p = doc.new_page(width=A4[0], height=A4[1])
    p.insert_text((50, 80), clean_text(title), fontsize=22, fontname="hebo")
    y = 110
    for ln in lines:
        p.insert_text((50, y), clean_text(ln), fontsize=11)
        y += 16
    if status:
        p.draw_circle((80, y + 50), 24, color=None, fill=norm_color(status[1]))
        p.insert_text((120, y + 58), clean_text(status[0]), fontsize=20, fontname="hebo", color=norm_color(status[1]))
    return p


def table(page: pymupdf.Page, x: float, y: float, headers: list[str], rows: list[list[str]], widths: list[float],
          row_h: float = 18, fontsize: float = 8.5) -> float:
    """Tabla de texto simple; devuelve la y final. No divide en páginas (el llamador decide)."""
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + w)
    page.draw_rect(pymupdf.Rect(x, y, xs[-1], y + row_h), color=None, fill=(0.86, 0.92, 1))
    for i, hd in enumerate(headers):
        page.insert_text((xs[i] + 3, y + row_h - 5), clean_text(hd), fontsize=fontsize, fontname="hebo")
    y += row_h
    for r in rows:
        for i, cell in enumerate(r):
            page.insert_textbox(pymupdf.Rect(xs[i] + 3, y + 2, xs[i + 1] - 3, y + row_h), clean_text(str(cell)), fontsize=fontsize)
        page.draw_line((x, y + row_h), (xs[-1], y + row_h), color=(0.85, 0.85, 0.85), width=0.4)
        y += row_h
    return y
