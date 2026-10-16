"""Page, upload and health tests (Milestone 2 tests kept; updated for CSRF and later milestones)."""
import base64
import io

from PIL import Image


def make_image(fmt="PNG", size=(120, 100), color=(190, 130, 95)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def test_home_page_loads_with_preview_method_and_privacy(client):
    r = client.get("/")
    assert r.status_code == 200 and "THE RACISM" in r.text
    assert "SAMPLE" in r.text and "How the estimate works" in r.text.replace("HOW THE ESTIMATE WORKS", "How the estimate works")
    assert 'id="privacy"' in r.text and "off by default" in r.text


def test_analyze_page_has_upload_camera_and_analysis_controls(client):
    r = client.get("/analyze")
    assert r.status_code == 200
    for needle in ("Choose a photo", "/static/js/analyze.js", "Open camera", "Analyze this crop", "How to crop"):
        assert needle in r.text


def test_distribution_page_discloses_synthetic_data(client):
    r = client.get("/distribution")
    assert r.status_code == 200
    assert "NOT REAL USER DATA" in r.text and "0 real participants" in r.text


def test_history_page_loads_empty(client):
    r = client.get("/history")
    assert r.status_code == 200 and "clean slate" in r.text.lower()


def test_settings_page_loads(client):
    assert client.get("/settings").status_code == 200


def test_unknown_result_is_404_html(client):
    r = client.get("/results/does-not-exist")
    assert r.status_code == 404 and "text/html" in r.headers["content-type"]


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["database"] == "ok"


def test_upload_accepts_valid_png_and_reencodes(client):
    r = client.post("/api/upload", files={"file": ("sample.png", make_image("PNG"), "image/png")})
    assert r.status_code == 200
    data = r.json()
    assert data["mime_type"] == "image/jpeg" and data["width"] == 120 and data["height"] == 100
    assert base64.b64decode(data["image_data_url"].split(",", 1)[1])[:2] == b"\xff\xd8"


def test_upload_accepts_webp(client):
    r = client.post("/api/upload", files={"file": ("sample.webp", make_image("WEBP"), "image/webp")})
    assert r.status_code == 200 and r.json()["mime_type"] == "image/jpeg"


def test_upload_rejects_fake_image_content(client):
    r = client.post("/api/upload", files={"file": ("fake.png", b"this is not an image", "image/png")})
    assert r.status_code == 422 and "couldn't read" in r.json()["detail"].lower()


def test_upload_rejects_unsupported_actual_format(client):
    r = client.post("/api/upload", files={"file": ("sample.bmp", make_image("BMP"), "image/bmp")})
    assert r.status_code == 422 and "jpeg, png, or webp" in r.json()["detail"].lower()


def test_upload_rejects_tiny_image(client):
    r = client.post("/api/upload", files={"file": ("tiny.png", make_image(size=(10, 10)), "image/png")})
    assert r.status_code == 422 and "too small" in r.json()["detail"].lower()


def test_upload_rejects_empty_file(client):
    r = client.post("/api/upload", files={"file": ("empty.png", b"", "image/png")})
    assert r.status_code == 422 and "empty" in r.json()["detail"].lower()


def test_confirm_crop_reencodes_valid_jpeg(client):
    encoded = base64.b64encode(make_image("JPEG", (80, 80))).decode("ascii")
    r = client.post("/api/confirm-crop", json={"image_data_url": f"data:image/jpeg;base64,{encoded}"})
    assert r.status_code == 200 and r.json()["width"] == 80 and "not saved" in r.json()["message"].lower()


def test_confirm_crop_rejects_malformed_payload(client):
    r = client.post("/api/confirm-crop", json={"image_data_url": "data:image/jpeg;base64,not base64!!"})
    assert r.status_code == 422
    assert client.post("/api/confirm-crop", json={"nope": 1}).status_code == 422


def test_every_static_asset_on_home_page_resolves_with_a_root_relative_url(client):
    import re
    html = client.get("/").text
    urls = re.findall(r'(?:href|src)="([^"]*/static/[^"]*)"', html)
    assert "/static/img/hero.jpeg" in urls and "/static/css/styles.css" in urls
    for url in urls:
        assert url.startswith("/static/"), f"{url} must be root-relative (absolute http:// URLs break behind HTTPS proxies)"
        assert client.get(url).status_code == 200, url
