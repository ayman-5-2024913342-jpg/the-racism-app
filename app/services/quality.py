"""Image-quality and lighting assessment. Each check is a measurable heuristic, not a calibration."""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

BLUR_WARN = 4.0          # variance of Laplacian at 256px; skin is smooth, so this is a weak signal
DARK_L = 12.0
CAST_WARN_CHROMA = 8.0   # chroma of near-neutral pixels above this suggests a colour cast
SMALL_CROP = 96


@dataclass
class QualityReport:
    sharpness: float
    mean_l: float
    dark_fraction: float
    bright_fraction: float
    cast_chroma: float | None
    neutral_fraction: float
    warnings: list[dict] = field(default_factory=list)


def _w(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def assess_quality(rgb: np.ndarray, lab: np.ndarray) -> QualityReport:
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    scale = 256 / max(h, w)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    L = lab[..., 0]
    dark = float((L < DARK_L).mean())
    bright = float(((rgb.max(axis=2) >= 250) & (L > 92)).mean())

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    neutral = (hsv[..., 1] < 40) & (hsv[..., 2] > 130) & (hsv[..., 2] < 250)
    neutral_frac = float(neutral.mean())
    cast = None
    if neutral_frac >= 0.02:
        cast = float(np.hypot(lab[..., 1][neutral], lab[..., 2][neutral]).mean())

    rep = QualityReport(sharp, float(L.mean()), dark, bright, cast, neutral_frac)
    if min(h, w) < SMALL_CROP:
        rep.warnings.append(_w("small_crop", "The selected area is small; a larger skin patch gives steadier results."))
    if sharp < BLUR_WARN:
        rep.warnings.append(_w("low_detail", "The image looks very smooth or blurry, which can hide lighting problems."))
    if dark > 0.15 or rep.mean_l < 25:
        rep.warnings.append(_w("underexposed", "Parts of the image are very dark. Shadows lower lightness and distort colour."))
    if bright > 0.05 or rep.mean_l > 92:
        rep.warnings.append(_w("overexposed", "Parts of the image are blown out. Highlights wash out colour."))
    if cast is not None and cast > CAST_WARN_CHROMA:
        rep.warnings.append(_w("color_cast", "Neutral areas in the photo are tinted, which suggests coloured lighting or a filter. Undertone is the most affected."))
    return rep
