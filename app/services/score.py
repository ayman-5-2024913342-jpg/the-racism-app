"""Skin tone lightness score (1-100), percentile on a normal curve, and the inline SVG chart.

Score: the sampled CIELAB lightness L* is mapped linearly from the range the analysis can actually
measure (L_MIN..L_MAX in skin.py, i.e. 10..97) onto 1..100. 1 = darkest measurable, 100 = lightest.

Percentile: the score is placed on a normal curve with a *reference* mean and standard deviation
(SCORE_MEAN / SCORE_SD in config). These are assumptions, not measured population statistics.
"""
from __future__ import annotations

import math

from markupsafe import Markup, escape

from app.services.skin import L_MAX, L_MIN

SCORE_MIN, SCORE_MAX = 1.0, 100.0


def skin_score(lab_l: float) -> float:
    """Map L* to 1..100 (1 = darkest, 100 = lightest), rounded to one decimal."""
    frac = (lab_l - L_MIN) / (L_MAX - L_MIN)
    return round(min(SCORE_MAX, max(SCORE_MIN, SCORE_MIN + frac * (SCORE_MAX - SCORE_MIN))), 1)


def _pdf(x: float, mean: float, sd: float) -> float:
    return math.exp(-0.5 * ((x - mean) / sd) ** 2) / (sd * math.sqrt(2 * math.pi))


def percentile(score: float, mean: float, sd: float) -> float:
    """Share (0-100) of the reference normal curve that sits below this score."""
    return 50.0 * (1.0 + math.erf((score - mean) / (sd * math.sqrt(2.0))))


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def curve_svg(score: float, mean: float, sd: float, name: str | None = None) -> Markup:
    """Normal curve with the user's position marked and the area below it shaded. Name is HTML-escaped."""
    w, h = 640, 300
    left, right, top, bottom = 24, 24, 46, 54
    pw, ph = w - left - right, h - top - bottom
    base_y = top + ph

    def sx(v: float) -> float:
        return left + (v - SCORE_MIN) / (SCORE_MAX - SCORE_MIN) * pw

    peak = _pdf(mean, mean, sd)

    def sy(v: float) -> float:
        return base_y - _pdf(v, mean, sd) / peak * ph * 0.92

    xs = [SCORE_MIN + i * (SCORE_MAX - SCORE_MIN) / 198 for i in range(199)]
    line = " ".join(f"{sx(x):.1f},{sy(x):.1f}" for x in xs)
    below = [x for x in xs if x <= score] or [SCORE_MIN]
    area = f"{sx(below[0]):.1f},{base_y} " + " ".join(f"{sx(x):.1f},{sy(x):.1f}" for x in below) + f" {sx(score):.1f},{sy(score):.1f} {sx(score):.1f},{base_y}"

    mx, my = sx(score), sy(score)
    label = f"{(name or 'You')[:20]} · {score:g}"
    anchor = "start" if mx < left + 80 else "end" if mx > w - right - 80 else "middle"
    ticks = "".join(
        f'<line x1="{sx(t):.1f}" y1="{base_y}" x2="{sx(t):.1f}" y2="{base_y + 5}" style="stroke:var(--muted)"/>'
        f'<text x="{sx(t):.1f}" y="{base_y + 19}" text-anchor="middle" style="fill:var(--muted);font-size:11px">{t}</text>'
        for t in (1, 25, 50, 75, 100)
    )
    pct = round(percentile(score, mean, sd))
    aria = f"Normal distribution of skin tone lightness scores from 1 (darkest) to 100 (lightest). Your score is {score:g}, around the {ordinal(pct)} percentile."
    return Markup(
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(aria)}" style="width:100%;height:auto;display:block">'
        f'<polygon points="{area}" style="fill:var(--olive);opacity:.22"/>'
        f'<polyline points="{line}" style="fill:none;stroke:var(--olive-dark);stroke-width:2.5"/>'
        f'<line x1="{left}" y1="{base_y}" x2="{w - right}" y2="{base_y}" style="stroke:var(--line);stroke-width:1.5"/>'
        f'{ticks}'
        f'<line x1="{mx:.1f}" y1="30" x2="{mx:.1f}" y2="{base_y}" style="stroke:var(--clay);stroke-width:2;stroke-dasharray:4 3"/>'
        f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="6" style="fill:var(--clay);stroke:#fff;stroke-width:2"/>'
        f'<text x="{mx:.1f}" y="20" text-anchor="{anchor}" style="fill:var(--ink);font-size:13px;font-weight:700">{escape(label)}</text>'
        f'<text x="{left}" y="{h - 10}" style="fill:var(--muted);font-size:11px">1 = darkest</text>'
        f'<text x="{w - right}" y="{h - 10}" text-anchor="end" style="fill:var(--muted);font-size:11px">100 = lightest</text>'
        f'</svg>'
    )
