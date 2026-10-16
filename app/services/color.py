"""Colour-space helpers.

All conversions assume sRGB input and the D65 white point, going through CIELAB (CIE 1976 L*a*b*).
CIELAB is *approximately* perceptually uniform: equal numeric distances look roughly similar in
size, but it is not exact, and it models viewing conditions that an uncalibrated phone photo
does not provide. Values here describe the photo, not the person's true skin colour.
"""
from __future__ import annotations

import math

import numpy as np
from skimage import color as skcolor

_RGB_FROM_XYZ = np.array(
    [[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]]
)


def rgb_to_lab(rgb_u8: np.ndarray) -> np.ndarray:
    return skcolor.rgb2lab(rgb_u8.astype(np.float64) / 255.0)


def lab_in_gamut(lab: tuple[float, float, float], tol: float = 1e-3) -> bool:
    xyz = skcolor.lab2xyz(np.array(lab, dtype=np.float64).reshape(1, 1, 3))[0, 0]
    linear = _RGB_FROM_XYZ @ xyz
    return bool(np.all(linear >= -tol) and np.all(linear <= 1 + tol))


def lab_to_rgb(lab: tuple[float, float, float]) -> tuple[int, int, int]:
    arr = skcolor.lab2rgb(np.array(lab, dtype=np.float64).reshape(1, 1, 3))[0, 0]
    r, g, b = (int(round(float(np.clip(v, 0.0, 1.0)) * 255)) for v in arr)
    return r, g, b


def lab_to_lch(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = lab
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0


def lch_to_lab(L: float, C: float, h: float) -> tuple[float, float, float]:
    rad = math.radians(h)
    return L, C * math.cos(rad), C * math.sin(rad)


def gamut_map(L: float, C: float, h: float) -> tuple[float, float, float]:
    """Reduce chroma until the colour fits inside sRGB (keeps lightness and hue)."""
    if lab_in_gamut(lch_to_lab(L, C, h)):
        return lch_to_lab(L, C, h)
    lo, hi = 0.0, C
    for _ in range(24):
        mid = (lo + hi) / 2
        if lab_in_gamut(lch_to_lab(L, mid, h)):
            lo = mid
        else:
            hi = mid
    return lch_to_lab(L, lo, h)


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def lin(c: int) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def on_color(rgb: tuple[int, int, int]) -> str:
    """Readable text colour (charcoal or white) for a swatch background."""
    return "#1F1F1F" if relative_luminance(rgb) > 0.4 else "#FFFFFF"


def ita_degrees(L: float, b: float) -> float:
    """Individual Typology Angle: atan((L*-50)/b*) in degrees (Chardon et al., 1991)."""
    return math.degrees(math.atan2(L - 50.0, b if abs(b) > 1e-9 else 1e-9))
