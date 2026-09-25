"""Reporte del banco de pruebas: Markdown + HTML con comparación contra la corrida anterior."""
import html
import json
from pathlib import Path

from .metrics import CATEGORIES

NAMES = {"text": "Texto", "spelling": "Ortografía", "color": "Color", "visual": "Elemento visual",
         "font": "Fuente", "color_visual": "Color + visual", "todas": "Todas"}
METS = ("precision", "recall", "f1")


def _arrow(new, old, higher_better=True):
    if old is None or new is None:
        return ""
    if abs(new - old) < 0.05:
        return " ="
    better = (new > old) == higher_better
    return f" ↑{abs(new - old):.1f}" if better else f" ↓{abs(new - old):.1f}"


def load_previous(dirpath: Path, current_name: str, scope: str, contra: str | None = None) -> dict | None:
    files = sorted((p for p in dirpath.glob("*.json") if p.stem != current_name), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("scope") == scope and (not contra or contra.lower() in d.get("etiqueta", "").lower()):
            return d
    return None


def render_markdown(run: dict, prev: dict | None, media_rel: str) -> str:
    L = []
    L.append(f"# Banco de pruebas – {run['etiqueta']}")
    L.append(f"\nFecha: {run['fecha']} · Alcance: **{run['scope']}** · Casos: {run['global']['casos']}")
    if prev:
        L.append(f"Comparado con: *{prev['etiqueta']}* ({prev['fecha']})")
    L.append("\n## Métricas por categoría\n")
    L.append("| Categoría | TP | FP | FN | Precisión % | Recall % | F1 % |")
    L.append("|---|---|---|---|---|---|---|")
    for k in CATEGORIES + ["color_visual", "todas"]:
        m = run["totales"][k]
        pm = prev["totales"].get(k) if prev else None
        cells = [f"{m[x]}{_arrow(m[x], pm[x]) if pm else ''}" for x in METS]
        L.append(f"| {NAMES[k]} | {m['tp']} | {m['fp']} | {m['fn']} | " + " | ".join(cells) + " |")
    g, pg = run["global"], (prev["global"] if prev else {})
    L.append("\n## Globales\n")
    L.append("| Métrica | Valor | Meta |")
    L.append("|---|---|---|")
    L.append(f"| Falsos positivos por caso | {g['fp_por_caso']}{_arrow(g['fp_por_caso'], pg.get('fp_por_caso'), False)} | ≤ 1 |")
    if g["identicos_aprobados_pct"] is not None:
        L.append(f"| Casos sin errores que dan «Aprobado» | {g['identicos_aprobados_pct']}% "
                 f"({g['identicos']} casos){_arrow(g['identicos_aprobados_pct'], pg.get('identicos_aprobados_pct'))} | 100% |")
    if g["cer_pct"] is not None:
        L.append(f"| CER medio del OCR | {g['cer_pct']}%{_arrow(g['cer_pct'], pg.get('cer_pct'), False)} | ≤ 3% |")
    L.append(f"| Tiempo medio / máximo por caso | {g['tiempo_medio_s']} s / {g['tiempo_max_s']} s | ≤ 15 s |")
    L.append("| Tiempo medio por etapa | " + ", ".join(f"{k} {v}s" for k, v in g["etapas_s"].items()) + " | |")

    if run.get("por_tipo"):
        L.append("\n## Por tipo de imagen\n")
        L.append("| Tipo | Casos | Recall % | Precisión % | FP/caso | CER % |")
        L.append("|---|---|---|---|---|---|")
        for t, v in run["por_tipo"].items():
            L.append(f"| {t} | {v['casos']} | {v['recall']} | {v['precision']} | {v['fp_por_caso']} | {v['cer_pct']} |")

    L.append("\n## Casos con falsos positivos o negativos\n")
    bad = [c for c in run["por_caso"] if c["fp_list"] or c["fn_list"]]
    if not bad:
        L.append("Ninguno. ✔")
    for c in bad:
        L.append(f"### {c['caso']} ({c['tipo']}) – {c['status']} {c['total']}%")
        for x in c["fp_list"]:
            L.append(f"- **FP** [{x['category']}/{x.get('subtype')}] {x['message'][:110]}"
                     + (f"  \n  ![]({media_rel}/{x['thumb']})" if x.get("thumb") else ""))
        for x in c["fn_list"]:
            L.append(f"- **FN** [{x['categoria']}/{x.get('subtipo')}] esperado en {x['bbox']}"
                     + (f"  \n  ![]({media_rel}/{x['thumb']})" if x.get("thumb") else ""))
    return "\n".join(L) + "\n"


def render_html(md: str, title: str) -> str:
    """HTML simple (sin dependencias): convierte el Markdown básico que genera este módulo."""
    out, in_table = [], False
    for ln in md.splitlines():
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if set("".join(cells)) <= set("-"):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if ln.startswith("# "):
            out.append(f"<h1>{html.escape(ln[2:])}</h1>")
        elif ln.startswith("## "):
            out.append(f"<h2>{html.escape(ln[3:])}</h2>")
        elif ln.startswith("### "):
            out.append(f"<h3>{html.escape(ln[4:])}</h3>")
        elif ln.strip().startswith("![]("):
            out.append(f'<img src="{ln.strip()[4:-1]}">')
        elif ln.startswith("- "):
            out.append(f"<p>{html.escape(ln[2:]).replace('**', '')}</p>")
        elif ln.strip():
            out.append(f"<p>{html.escape(ln)}</p>")
    if in_table:
        out.append("</table>")
    css = ("body{font:14px Segoe UI,sans-serif;max-width:1000px;margin:20px auto;padding:0 14px}"
           "table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #ccc;padding:3px 8px;text-align:left}"
           "th{background:#eee}img{display:block;margin:4px 0 10px;max-width:420px;border:1px solid #ccc}")
    return f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title><style>{css}</style>" + "\n".join(out)
