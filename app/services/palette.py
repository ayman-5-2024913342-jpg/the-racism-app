"""Complementary colour suggestions generated in CIE LCh.

These are *design suggestions* derived from colour-wheel relationships around the measured hue.
They are not rules about what "suits" anyone; taste, context and fabric matter far more.
"""
from __future__ import annotations

from app.services.color import gamut_map, lab_to_lch, lab_to_rgb, on_color, to_hex


def _swatch(name: str, role: str, L: float, C: float, h: float) -> dict:
    lab = gamut_map(L, C, h % 360.0)
    rgb = lab_to_rgb(lab)
    return {"name": name, "role": role, "hex": to_hex(rgb), "text": on_color(rgb)}


def build_palette(lab: tuple[float, float, float], undertone: str = "inconclusive") -> list[dict]:
    _, _, h = lab_to_lch(lab)
    warm_bias = {"warm": 8, "cool": -8}.get(undertone, 0)
    return [
        _swatch("Complement", "Opposite on the colour wheel", 45, 42, h + 180),
        _swatch("Split complement A", "Softer contrast", 52, 38, h + 150),
        _swatch("Split complement B", "Softer contrast", 52, 38, h + 210),
        _swatch("Analogous A", "Close neighbour", 58, 42, h + 30 + warm_bias),
        _swatch("Analogous B", "Close neighbour", 55, 36, h - 30 + warm_bias),
        _swatch("Deep neutral", "Grounding dark", 24, 8, h),
        _swatch("Soft neutral", "Light base", 90, 6, h),
    ]
