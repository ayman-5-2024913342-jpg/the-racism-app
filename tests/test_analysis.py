import numpy as np
import pytest

from app.errors import AppError
from app.services.skin import analyze_skin, classify_shade, classify_undertone, detect_skin_mask
from tests.helpers import flat_skin, skin_image


@pytest.mark.parametrize("ita,key", [(60, "very_light"), (45, "light"), (30, "intermediate"), (15, "tan"), (-10, "brown"), (-45, "deep")])
def test_shade_bands(ita, key):
    assert classify_shade(ita)[0] == key


def test_shade_near_boundary_reports_alternative():
    assert classify_shade(41.5)[2] is not None
    assert classify_shade(48)[2] is None


@pytest.mark.parametrize("hue,chroma,key", [(40, 20, "cool"), (54, 20, "neutral"), (65, 20, "warm"), (65, 3, "inconclusive"), (50.5, 20, "inconclusive")])
def test_undertone_rules(hue, chroma, key):
    assert classify_undertone(hue, chroma)[0] == key


def test_mask_finds_skin_and_ignores_blue_background():
    img = skin_image()
    mask = detect_skin_mask(img)
    assert mask[120, 120] and not mask[5, 5]
    assert 0.3 < mask.mean() < 0.7


def test_analysis_ignores_background_and_is_light_skin():
    res = analyze_skin(skin_image())
    assert res.region_method == "skin_mask"
    assert res.shade_key in {"very_light", "light", "intermediate"}
    assert abs(res.rgb[0] - 224) < 8 and abs(res.rgb[2] - 145) < 8  # background (blue) did not leak in
    assert 0 <= res.confidence <= 1 and res.hex.startswith("#") and len(res.hex) == 7


def test_darker_patch_gets_darker_band():
    light = analyze_skin(flat_skin((234, 192, 170)), treat_as_skin=True)
    dark = analyze_skin(flat_skin((110, 70, 52)), treat_as_skin=True)
    assert dark.ita < light.ita and dark.lab[0] < light.lab[0]


def test_no_skin_requests_manual_region_and_override_works():
    blue = np.full((200, 200, 3), (30, 80, 170), dtype=np.uint8)
    with pytest.raises(AppError) as e:
        analyze_skin(blue)
    assert e.value.code == "needs_manual_region" and e.value.status_code == 422
    assert analyze_skin(blue, treat_as_skin=True).region_method == "user_selected_region"


def test_too_few_pixels():
    tiny = flat_skin(size=8)
    with pytest.raises(AppError):
        analyze_skin(tiny, treat_as_skin=True)


def test_noise_lowers_reliability():
    clean = analyze_skin(flat_skin(noise=3), treat_as_skin=True)
    noisy = analyze_skin(flat_skin(noise=30, seed=5), treat_as_skin=True)
    assert noisy.confidence < clean.confidence


def test_clipped_highlights_are_excluded_from_sampling():
    blown = flat_skin((254, 250, 245), noise=0)  # every pixel has a channel >= 252
    with pytest.raises(AppError) as e:
        analyze_skin(blown, treat_as_skin=True)
    assert e.value.code == "too_few_pixels"


def test_color_cast_forces_inconclusive_undertone():
    img = skin_image()
    img[:30, :] = (230, 218, 200)  # tinted near-neutral (e.g. a warm-lit white wall)
    res = analyze_skin(img)
    assert any(w["code"] == "color_cast" for w in res.warnings)
    assert res.undertone_key == "inconclusive"


def test_deterministic():
    a, b = analyze_skin(skin_image()), analyze_skin(skin_image())
    assert a.rgb == b.rgb and a.confidence == b.confidence
