"""Porcentajes por categoría, total ponderado y semáforo."""


def _pct(num: float, den: float) -> float:
    if den <= 0:
        return 100.0
    return max(0.0, min(100.0, 100.0 * num / den))


def compute_scores(visual_ssim: float, text_matched: int, text_total: int,
                   color_error_area: float, total_area: float,
                   spell_errors: int, spell_total: int,
                   font_bad: int, font_total: int, weights: dict) -> tuple[dict, str]:
    scores = {
        "visual": max(0.0, min(100.0, visual_ssim * 100.0)),
        "text": _pct(text_matched, text_total),
        "color": _pct(total_area - color_error_area, total_area),
        "spelling": _pct(spell_total - spell_errors, spell_total),
        "font": _pct(font_total - font_bad, font_total),
    }
    wsum = sum(weights.get(k, 0) for k in scores) or 1.0
    total = sum(scores[k] * weights.get(k, 0) for k in scores) / wsum
    scores["total"] = total
    scores = {k: round(v, 1) for k, v in scores.items()}
    return scores, status_for(total)


def status_for(total: float) -> str:
    if total >= 98:
        return "aprobado"
    if total >= 90:
        return "revisar"
    return "con_errores"
