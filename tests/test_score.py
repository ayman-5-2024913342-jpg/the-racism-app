"""Name entry, 1-100 skin tone score, percentile and the normal-curve chart."""
import numpy as np

from app.services.score import curve_svg, ordinal, percentile, skin_score
from app.services.skin import L_MAX, L_MIN
from tests.conftest import analyze
from tests.helpers import encode, flat_skin


def test_score_endpoints_and_monotonic():
    assert skin_score(L_MIN) == 1.0 and skin_score(L_MAX) == 100.0
    assert skin_score(0) == 1.0 and skin_score(100) == 100.0  # clamped outside the measurable range
    vals = [skin_score(L) for L in range(10, 98, 5)]
    assert vals == sorted(vals) and len(set(vals)) == len(vals)


def test_percentile_properties():
    assert abs(percentile(50, 50, 15) - 50) < 1e-9
    assert abs(percentile(65, 50, 15) - 84.134) < 0.01  # +1 SD
    assert percentile(20, 50, 15) < percentile(60, 50, 15)
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 73)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "73rd"]


def test_curve_svg_marks_position_and_escapes_name():
    svg = str(curve_svg(62.0, 50, 15, '<script>alert(1)</script>'))
    assert svg.startswith("<svg") and "<script>" not in svg and "&lt;script&gt;" in svg[:2000] + svg
    for s in (1.0, 50.0, 100.0):  # edge positions render without error
        assert "<circle" in str(curve_svg(s, 50, 15, "Ann"))


def test_name_is_required(client, skin_png):
    for bad in ("", "   "):
        r = client.post("/api/analyze", files={"file": ("c.png", skin_png, "image/png")}, data={"name": bad})
        assert r.status_code == 422 and r.json()["code"] == "name_required"
    r = client.post("/api/analyze", files={"file": ("c.png", skin_png, "image/png")})
    assert r.status_code == 422 and r.json()["code"] == "name_required"
    r = analyze(client, skin_png, name="x" * 41)
    assert r.status_code == 422 and r.json()["code"] == "name_too_long"


def test_results_show_name_score_percentile_and_curve(client):
    dark = encode(flat_skin(skin=(110, 70, 50)))
    light = encode(flat_skin(skin=(240, 200, 180)))
    pages = {}
    for label, png in (("dark", dark), ("light", light)):
        rid = analyze(client, png, name="  Mira   Rahman ").json()["id"]
        pages[label] = client.get(f"/results/{rid}").text
    for page in pages.values():
        assert "Mira Rahman" in page and "Skin tone score" in page and "percentile" in page and "<svg" in page
    def score(page):
        import re
        return float(re.search(r"Skin tone score: ([\d.]+)", page).group(1))
    assert score(pages["dark"]) < score(pages["light"])


def test_name_is_html_escaped_on_results_page(client, skin_png):
    rid = analyze(client, skin_png, name="<b>Hi</b>").json()["id"]
    page = client.get(f"/results/{rid}").text
    assert "<b>Hi</b>" not in page and "&lt;b&gt;Hi&lt;/b&gt;" in page


def test_analyze_page_asks_for_name(client):
    page = client.get("/analyze").text
    assert 'id="user-name"' in page and "Your name" in page
