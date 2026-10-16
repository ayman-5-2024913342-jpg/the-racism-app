"""Skin-colour estimation pipeline.

Documented rules (all heuristics; NOT scientifically validated for uncalibrated photos):

1. Skin candidate mask: pixel must satisfy BOTH
     - YCrCb:  133 <= Cr <= 180 and 77 <= Cb <= 135   (Chai & Ngan style range)
     - HSV:    hue <= 25 or >= 165 (OpenCV 0-179), saturation >= 15, value >= 50
   followed by a morphological open/close. This can miss some skin tones or accept
   skin-like backgrounds; the user's crop is the first line of defence, and the
   "treat my crop as skin" option bypasses the mask.
2. Usable samples: exclude L* < 10, L* > 97 and clipped pixels (any channel >= 252).
3. Robust trimming: drop pixels farther than max(2.5 * 1.4826 * MAD, 5) from the median Lab.
4. Representative colour: per-channel median of trimmed Lab pixels.
5. Shade band: Individual Typology Angle, ITA = atan((L*-50)/b*), bands after Chardon 1991.
   The bands were defined for calibrated skin measurements; here they are only a coarse label.
6. Undertone: hue angle h_ab = atan2(b*, a*). < 50 deg "cool/rosy", 50-58 "neutral", > 58 "warm/golden".
   Reported "inconclusive" when within 1.5 deg of a boundary, chroma < 8, a colour cast is detected,
   or the overall reliability is low.
7. Reliability: weighted geometric mean of six factor scores in [0, 1] (see _confidence).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.errors import AppError
from app.services.color import (
    ita_degrees, lab_to_lch, lab_to_rgb, rgb_to_lab, to_hex,
)
from app.services.quality import assess_quality

ALGORITHM_VERSION = "1.0.0"
MIN_SKIN_FRACTION = 0.10
LOW_COVERAGE = 0.35
MIN_SAMPLES = 150
L_MIN, L_MAX = 10.0, 97.0

SHADE_BANDS = [  # (lower ITA bound, key, label)
    (55.0, "very_light", "Very light"),
    (41.0, "light", "Light"),
    (28.0, "intermediate", "Intermediate"),
    (10.0, "tan", "Tan"),
    (-30.0, "brown", "Brown"),
    (-1e9, "deep", "Deep"),
]
COOL_MAX, NEUTRAL_MAX, UNDERTONE_MARGIN, MIN_UNDERTONE_CHROMA = 50.0, 58.0, 1.5, 8.0
UNDERTONE_LABELS = {
    "cool": "Cool (rosy leaning)",
    "neutral": "Neutral",
    "warm": "Warm (golden leaning)",
    "inconclusive": "Inconclusive",
}


@dataclass
class Factor:
    key: str
    label: str
    score: float
    note: str


@dataclass
class SkinAnalysis:
    rgb: tuple[int, int, int]
    hex: str
    lab: tuple[float, float, float]
    lch: tuple[float, float, float]
    ita: float
    shade_key: str
    shade_label: str
    shade_alternative: str | None
    undertone_key: str
    undertone_label: str
    undertone_note: str
    confidence: float
    confidence_label: str
    factors: list[Factor]
    warnings: list[dict]
    n_samples: int
    skin_fraction: float
    region_method: str
    spread: float
    algorithm_version: str = ALGORITHM_VERSION


def detect_skin_mask(rgb: np.ndarray) -> np.ndarray:
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
    cr, cb = ycc[..., 1], ycc[..., 2]
    m1 = (cr >= 133) & (cr <= 180) & (cb >= 77) & (cb <= 135)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m2 = ((hue <= 25) | (hue >= 165)) & (sat >= 15) & (val >= 50)
    mask = (m1 & m2).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    return mask.astype(bool)


def classify_shade(ita: float) -> tuple[str, str, str | None]:
    """Return (key, label, adjacent-band label if ITA is within 3 degrees of a boundary)."""
    idx = next(i for i, (lo, _, _) in enumerate(SHADE_BANDS) if ita > lo)
    _, key, label = SHADE_BANDS[idx]
    alt = None
    if idx > 0 and abs(ita - SHADE_BANDS[idx - 1][0]) <= 3.0:
        alt = SHADE_BANDS[idx - 1][2]
    elif idx < len(SHADE_BANDS) - 1 and abs(ita - SHADE_BANDS[idx][0]) <= 3.0:
        alt = SHADE_BANDS[idx + 1][2]
    return key, label, alt


def classify_undertone(hue: float, chroma: float) -> tuple[str, str]:
    if chroma < MIN_UNDERTONE_CHROMA:
        return "inconclusive", "Colour saturation is too low to read an undertone."
    for boundary in (COOL_MAX, NEUTRAL_MAX):
        if abs(hue - boundary) < UNDERTONE_MARGIN:
            return "inconclusive", "The measured hue sits right on a category boundary."
    if hue < COOL_MAX:
        return "cool", "Hue leans toward pink/red."
    if hue <= NEUTRAL_MAX:
        return "neutral", "Hue sits between pink/red and yellow/gold."
    return "warm", "Hue leans toward yellow/gold."


def _clip(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _confidence(skin_frac, n, spread, q, region_method) -> tuple[float, str, list[Factor]]:
    coverage = 0.9 if region_method == "user_selected_region" else _clip(skin_frac / 0.5)
    samples = _clip(n / 1500)
    uniform = _clip(1 - (spread - 4) / 12)
    exposure = _clip(1 - (q.dark_fraction + q.bright_fraction) / 0.25)
    if q.mean_l < 25 or q.mean_l > 92:
        exposure *= 0.5
    sharp = 0.5 + 0.5 * _clip(q.sharpness / 8)
    cast = 0.9 if q.cast_chroma is None else _clip(1 - (q.cast_chroma - 4) / 12)
    fs = [
        Factor("coverage", "Skin coverage", coverage,
               "Share of the crop recognised as skin." if region_method != "user_selected_region"
               else "You marked the whole crop as skin, so coverage was not checked."),
        Factor("samples", "Sample size", samples, "Number of usable pixels measured."),
        Factor("uniformity", "Colour consistency", uniform, "Low spread means a steadier patch (shadows and blemishes raise spread)."),
        Factor("exposure", "Exposure", exposure, "Penalises very dark or blown-out areas."),
        Factor("sharpness", "Image detail", sharp, "Weak signal: blur can hide uneven lighting."),
        Factor("cast", "Lighting colour", cast,
               "Checks near-neutral pixels (whites, greys) for a tint." if q.cast_chroma is not None
               else "No neutral reference found in the photo, so a colour cast cannot be ruled out."),
    ]
    weights = [2, 1, 2, 2, 0.5, 1]
    log_sum = sum(w * math.log(max(f.score, 0.02)) for w, f in zip(weights, fs))
    score = math.exp(log_sum / sum(weights))
    label = "Higher" if score >= 0.7 else "Moderate" if score >= 0.45 else "Low"
    return float(score), label, fs


def analyze_skin(rgb: np.ndarray, *, treat_as_skin: bool = False) -> SkinAnalysis:
    lab = rgb_to_lab(rgb)
    q = assess_quality(rgb, lab)
    warnings = list(q.warnings)

    if treat_as_skin:
        mask = np.ones(rgb.shape[:2], dtype=bool)
        method = "user_selected_region"
    else:
        mask = detect_skin_mask(rgb)
        method = "skin_mask"
    skin_frac = float(mask.mean())
    if method == "skin_mask" and skin_frac < MIN_SKIN_FRACTION:
        raise AppError(
            "needs_manual_region",
            "We could not find enough skin-coloured pixels. Crop tighter on a cheek or forehead, "
            "or confirm that your crop is skin and we will use it as-is.",
            422, can_override=True,
        )
    if method == "skin_mask" and skin_frac < LOW_COVERAGE:
        warnings.append({"code": "low_coverage", "message": "Only part of the crop looks like skin. Cropping tighter will improve reliability."})

    L = lab[..., 0]
    usable = mask & (L >= L_MIN) & (L <= L_MAX) & (rgb.max(axis=2) < 252)
    if int(usable.sum()) < MIN_SAMPLES:
        raise AppError("too_few_pixels", "Too few usable pixels remain after removing shadows and highlights. Choose a larger, evenly lit area.", 422)

    pts = lab[usable]
    med = np.median(pts, axis=0)
    dist = np.linalg.norm(pts - med, axis=1)
    thresh = max(2.5 * 1.4826 * float(np.median(dist)), 5.0)
    kept = pts[dist <= thresh]
    if len(kept) < MIN_SAMPLES:
        kept = pts
    rep = tuple(float(v) for v in np.median(kept, axis=0))
    spread = float(np.sqrt(kept.var(axis=0).sum()))

    L_, a_, b_ = rep
    _, C, h = lab_to_lch(rep)
    ita = ita_degrees(L_, b_)
    shade_key, shade_label, alt = classify_shade(ita)
    under_key, under_note = classify_undertone(h, C)
    score, conf_label, factors = _confidence(skin_frac, len(kept), spread, q, method)

    if q.cast_chroma is not None and q.cast_chroma > 8.0 and under_key != "inconclusive":
        under_key, under_note = "inconclusive", "A colour cast in the photo makes undertone unreliable."
    if score < 0.45 and under_key != "inconclusive":
        under_key, under_note = "inconclusive", "Overall reliability is too low to report an undertone."
    if alt:
        warnings.append({"code": "near_boundary", "message": f"The measured value is close to the boundary with “{alt}”. Small lighting changes could move it."})
    if method == "user_selected_region":
        warnings.append({"code": "unchecked_region", "message": "Skin detection was skipped at your request, so non-skin pixels in the crop would affect the result."})

    rgb_med = lab_to_rgb(rep)
    return SkinAnalysis(
        rgb=rgb_med, hex=to_hex(rgb_med), lab=rep, lch=(L_, C, h), ita=float(ita),
        shade_key=shade_key, shade_label=shade_label, shade_alternative=alt,
        undertone_key=under_key, undertone_label=UNDERTONE_LABELS[under_key], undertone_note=under_note,
        confidence=score, confidence_label=conf_label, factors=factors, warnings=warnings,
        n_samples=int(len(kept)), skin_fraction=skin_frac, region_method=method, spread=spread,
    )
