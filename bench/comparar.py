"""Tabla «antes vs después» entre dos corridas del banco de pruebas.

    uv run python -m bench.comparar "v1 linea base" "v2 final"

Busca, para cada texto, la corrida más reciente cuya etiqueta lo contenga (mismo alcance)."""
import json
import sys
from datetime import datetime

from .metrics import CATEGORIES
from .report import NAMES
from .run import OUT_DIR


def latest(label: str, scope: str | None = None) -> dict:
    best, best_m = None, -1
    for p in OUT_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or label.lower() not in d.get("etiqueta", "").lower():
            continue
        if scope and d.get("scope") != scope:
            continue
        if p.stat().st_mtime > best_m:
            best, best_m = d, p.stat().st_mtime
    if best is None:
        raise SystemExit(f"No hay ninguna corrida con la etiqueta «{label}».")
    return best


def _cell(a, b, higher_better=True) -> str:
    if a is None or b is None:
        return "—"
    d = b - a
    mark = "=" if abs(d) < 0.05 else ("↑" if (d > 0) == higher_better else "↓")
    return f"{a} → {b} {mark}"


def build(a: dict, b: dict) -> str:
    L = [f"# Antes vs después: «{a['etiqueta']}» → «{b['etiqueta']}»\n",
         f"Alcance: {a['scope']} / {b['scope']} · Casos: {a['global']['casos']} / {b['global']['casos']}\n",
         "## Métricas por categoría (↑ mejoró, ↓ empeoró)\n",
         "| Categoría | Precisión % | Recall % | F1 % |", "|---|---|---|---|"]
    for k in CATEGORIES + ["color_visual", "todas"]:
        x, y = a["totales"][k], b["totales"][k]
        L.append(f"| {NAMES[k]} | {_cell(x['precision'], y['precision'])} | {_cell(x['recall'], y['recall'])} | {_cell(x['f1'], y['f1'])} |")
    ga, gb = a["global"], b["global"]
    L += ["\n## Globales\n", "| Métrica | Antes → después | Meta |", "|---|---|---|",
          f"| Falsos positivos por caso | {_cell(ga['fp_por_caso'], gb['fp_por_caso'], False)} | ≤ 1 |",
          f"| Casos sin errores que dan «Aprobado» % | {_cell(ga['identicos_aprobados_pct'], gb['identicos_aprobados_pct'])} | 100 |",
          f"| CER del OCR % | {_cell(ga['cer_pct'], gb['cer_pct'], False)} | ≤ 3 |",
          f"| Tiempo medio por caso (s) | {_cell(ga['tiempo_medio_s'], gb['tiempo_medio_s'], False)} | ≤ 15 |"]
    tipos = sorted(set(a.get("por_tipo", {})) | set(b.get("por_tipo", {})))
    if tipos:
        L += ["\n## Por tipo de imagen\n", "| Tipo | Casos | Recall % | Precisión % | FP/caso | CER % |", "|---|---|---|---|---|---|"]
        for t in tipos:
            x, y = a.get("por_tipo", {}).get(t), b.get("por_tipo", {}).get(t)
            if not x or not y:
                L.append(f"| {t} | {(y or x)['casos']} | (solo en una corrida) | | | |")
                continue
            L.append(f"| {t} | {y['casos']} | {_cell(x['recall'], y['recall'])} | {_cell(x['precision'], y['precision'])} | "
                     f"{_cell(x['fp_por_caso'], y['fp_por_caso'], False)} | {_cell(x['cer_pct'], y['cer_pct'], False)} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print(__doc__)
        return 1
    a, b = latest(argv[0]), latest(argv[1], None)
    md = build(a, b)
    safe = lambda t: "".join(c if c.isalnum() else "_" for c in t)
    out = OUT_DIR / f"{datetime.now():%Y-%m-%d}_comparacion_{safe(argv[0])}_vs_{safe(argv[1])}.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print("Guardado en", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
