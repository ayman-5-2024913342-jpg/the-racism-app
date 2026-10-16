"""End-to-end tests for analysis, results, saving, sharing, export, deletion and authorization."""
import io
import json

import numpy as np
from PIL import Image

from tests.conftest import analyze, make_client
from tests.helpers import encode

HX = {"HX-Request": "true"}


def test_analyze_returns_result_and_page_renders(client, skin_png):
    r = analyze(client, skin_png)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["result_url"] == f"/results/{data['id']}" and len(data["id"]) >= 20
    assert data["saved"] is False and data["hex"].startswith("#")
    page = client.get(data["result_url"])
    assert page.status_code == 200
    for needle in (data["hex"], "Reliability", "Colors to explore", "CIELAB", "Export JSON"):
        assert needle in page.text


def test_results_are_private_to_their_browser(client, other_client, skin_png):
    rid = analyze(client, skin_png).json()["id"]
    assert other_client.get(f"/results/{rid}").status_code == 404
    assert other_client.get(f"/results/{rid}/export.json").status_code == 404
    assert other_client.delete(f"/results/{rid}", headers=HX).status_code == 404
    assert other_client.post(f"/results/{rid}/save", headers=HX).status_code == 404
    assert client.get(f"/results/{rid}").status_code == 200


def test_no_skin_requests_manual_region_then_override_works(client):
    blue = encode(np.full((200, 200, 3), (30, 80, 170), dtype=np.uint8))
    r = analyze(client, blue)
    assert r.status_code == 422 and r.json()["code"] == "needs_manual_region" and r.json()["can_override"] is True
    assert analyze(client, blue, treat_as_skin="true").status_code == 200


def test_invalid_uploads_are_rejected_cleanly(client):
    for blob, name in ((b"garbage", "x.png"), (b"", "e.png")):
        r = client.post("/api/analyze", files={"file": (name, blob, "image/png")}, data={"name": "Test User"})
        assert r.status_code == 422 and r.json()["code"] in {"invalid_image", "empty_file"}
    assert client.post("/api/analyze").status_code == 422


def test_save_unsave_share_and_delete_flow(client, skin_png):
    rid = analyze(client, skin_png).json()["id"]
    assert client.post(f"/results/{rid}/share", headers=HX).status_code == 409  # must save first
    assert "SAVED" in client.post(f"/results/{rid}/save", headers=HX).text
    assert rid in client.get("/history").text
    assert "Stop contributing" in client.post(f"/results/{rid}/share", headers=HX).text
    assert "Contribute anonymously" in client.post(f"/results/{rid}/unshare", headers=HX).text
    client.post(f"/results/{rid}/share", headers=HX)
    client.post(f"/results/{rid}/unsave", headers=HX)  # unsaving also withdraws sharing
    assert rid not in client.get("/history").text
    r = client.delete(f"/results/{rid}", headers=HX)
    assert r.status_code == 200 and r.headers["HX-Redirect"] == "/history"
    assert client.get(f"/results/{rid}").status_code == 404


def test_history_delete_card_returns_empty_body(client, skin_png):
    rid = analyze(client, skin_png, save="true").json()["id"]
    r = client.delete(f"/results/{rid}?origin=history", headers=HX)
    assert r.status_code == 200 and r.text == "" and "HX-Redirect" not in r.headers


def test_export_json_and_png(client, skin_png):
    rid = analyze(client, skin_png).json()["id"]
    j = client.get(f"/results/{rid}/export.json")
    assert j.status_code == 200 and "attachment" in j.headers["content-disposition"]
    body = j.json()
    assert body["sampled_color"]["hex"].startswith("#") and "disclaimer" in body and len(body["palette"]) == 7
    assert "id" not in body and "owner" not in json.dumps(body).lower()
    p = client.get(f"/results/{rid}/palette.png")
    assert p.status_code == 200 and p.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(p.content)).size[0] > 200


def test_settings_save_by_default_and_delete_all(client, skin_png):
    r = client.post("/settings", data={"save_by_default": "on"}, headers=HX)
    assert r.status_code == 200 and "Preferences saved" in r.text
    data = analyze(client, skin_png).json()
    assert data["saved"] is True and data["shared"] is False  # sharing stays off unless explicitly enabled
    r = client.post("/settings/delete-all", headers=HX)
    assert r.status_code == 200 and r.headers["HX-Redirect"] == "/"
    assert client.get(f"/results/{data['id']}").status_code == 404


def test_share_by_default_requires_save_default(client):
    client.post("/settings", data={"share_by_default": "on"}, headers=HX)
    assert 'name="share_by_default" checked' not in client.get("/settings").text


def test_distribution_is_synthetic_until_enough_opt_in_data(client, skin_png):
    assert client.get("/distribution/chart.png").headers["content-type"] == "image/png"
    assert client.get("/distribution/chart.png?source=real").status_code == 409
    client.post("/settings", data={"save_by_default": "on", "share_by_default": "on"}, headers=HX)
    for _ in range(4):
        analyze(client, skin_png)
    page = client.get("/distribution").text
    assert "NOT REAL USER DATA" in page and "4 real participants" in page  # below threshold (5)
    analyze(client, skin_png)
    page = client.get("/distribution").text
    assert "ANONYMOUS OPT-IN CONTRIBUTIONS" in page and "5 real participants" in page
    assert client.get("/distribution/chart.png?source=real").status_code == 200
    # withdrawing returns the page to synthetic data and the page never lists individual records
    client.post("/settings/withdraw-shared", headers=HX)
    assert "NOT REAL USER DATA" in client.get("/distribution").text
