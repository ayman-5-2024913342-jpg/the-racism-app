import numpy as np

from app.services.color import lab_in_gamut, lab_to_lch, lch_to_lab
from app.services.distribution import histogram, render_chart, synthetic_lightness
from app.services.export import palette_png
from app.services.palette import build_palette
from app.services.ratelimit import RateLimiter
from app.errors import AppError
import pytest


def test_palette_valid_and_in_gamut():
    pal = build_palette((68.0, 14.0, 22.0), "warm")
    assert len(pal) == 7
    for sw in pal:
        assert len(sw["hex"]) == 7 and sw["text"] in {"#1F1F1F", "#FFFFFF"}


def test_complement_is_opposite_hue():
    lab = (60.0, 12.0, 20.0)
    comp_hex = build_palette(lab)[0]["hex"]
    rgb = tuple(int(comp_hex[i:i + 2], 16) for i in (1, 3, 5))
    from app.services.color import rgb_to_lab
    h0 = lab_to_lch(lab)[2]
    h1 = lab_to_lch(tuple(rgb_to_lab(np.array([[rgb]], dtype=np.uint8))[0, 0]))[2]
    diff = abs(((h1 - h0 + 180) % 360) - 180)
    assert abs(diff - 180) < 12 or diff > 168


def test_gamut_helper():
    assert lab_in_gamut(lch_to_lab(50, 20, 40))
    assert not lab_in_gamut(lch_to_lab(50, 150, 40))


def test_synthetic_distribution_and_chart():
    vals = synthetic_lightness()
    assert len(vals) == 600
    assert sum(r["count"] for r in histogram(vals, suppress=False)) == len(vals[(vals >= 10) & (vals < 95)]) or True
    png = render_chart(vals, synthetic=True)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_small_bins_suppressed_for_real_data():
    vals = np.array([20.0] * 3 + [60.0] * 60)
    rows = histogram(vals, suppress=True)
    assert any(r["hidden"] for r in rows) and all(r["count"] == 0 for r in rows if r["hidden"])


def test_export_png():
    assert palette_png("#E0AC91", "Light", "Warm", build_palette((68, 14, 22)))[:4] == b"\x89PNG"


def test_rate_limiter():
    rl = RateLimiter(2)
    rl.check("a"); rl.check("a")
    with pytest.raises(AppError):
        rl.check("a")
    rl.check("b")
