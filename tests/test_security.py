from fastapi.testclient import TestClient

from app.main import app


def test_state_changing_requests_need_csrf_token(client):
    del client.headers["X-CSRF-Token"]
    r = client.post("/settings", data={"save_by_default": "on"})
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    client.headers["X-CSRF-Token"] = "wrong" * 8
    assert client.post("/settings", data={}).status_code == 403


def test_cross_origin_post_is_blocked(client):
    r = client.post("/settings", data={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "bad_origin"


def test_cookies_are_httponly_and_headers_set():
    with TestClient(app) as c:
        r = c.get("/")
        cookies = r.headers.get_list("set-cookie")
        assert len(cookies) == 2 and all("httponly" in v.lower() and "samesite=lax" in v.lower() for v in cookies)
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_untrusted_host_is_rejected():
    with TestClient(app, base_url="http://evil.example") as c:
        assert c.get("/").status_code == 400


def test_csrf_token_is_embedded_in_pages(client):
    token = client.cookies.get("tga_csrf")
    assert f'content="{token}"' in client.get("/analyze").text


def test_owner_token_is_not_stored_in_clear(client, skin_png):
    from app.db import session_scope
    from app.models import Owner
    from sqlalchemy import select
    client.post("/api/analyze", files={"file": ("c.png", skin_png, "image/png")}, data={"name": "Test User"})
    with session_scope() as db:
        hashes = [o.token_hash for o in db.scalars(select(Owner))]
    assert hashes and client.cookies.get("tga_owner") not in hashes
