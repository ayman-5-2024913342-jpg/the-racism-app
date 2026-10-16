"""Saved results are public to view; only the creating (hashed) browser can change or delete them."""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import analyze
from tests.test_repository import bundle, db, owner  # noqa: F401  (fixtures/helpers)
from app.repositories import AnalysisRepository

HX = {"HX-Request": "true"}


def test_saved_result_is_viewable_by_anyone_including_new_visitors(client, other_client, skin_png):
    rid = analyze(client, skin_png, save="true", name="Mira").json()["id"]
    for c in (other_client, TestClient(app)):  # another browser, and a visitor who never got a cookie
        page = c.get(f"/results/{rid}")
        assert page.status_code == 200 and "Mira" in page.text and "Skin tone score" in page.text
        assert c.get(f"/results/{rid}/export.json").status_code == 200
        assert c.get(f"/results/{rid}/palette.png").status_code == 200


def test_unsaved_result_stays_private_to_its_owner(client, other_client, skin_png):
    rid = analyze(client, skin_png).json()["id"]
    assert client.get(f"/results/{rid}").status_code == 200
    assert other_client.get(f"/results/{rid}").status_code == 404
    assert TestClient(app).get(f"/results/{rid}").status_code == 404


def test_only_the_owner_can_delete_a_public_result(client, other_client, skin_png):
    rid = analyze(client, skin_png, save="true").json()["id"]
    r = other_client.delete(f"/results/{rid}", headers=HX)
    assert r.status_code == 403
    assert TestClient(app).delete(f"/results/{rid}", headers=HX).status_code in (403, 404)  # no CSRF/cookie: never succeeds
    assert client.get(f"/results/{rid}").status_code == 200  # still there
    assert other_client.post(f"/results/{rid}/unsave", headers=HX).status_code == 404  # other mutations stay owner-only
    assert client.delete(f"/results/{rid}", headers=HX).status_code == 200
    assert other_client.get(f"/results/{rid}").status_code == 404


def test_result_page_controls_depend_on_ownership(client, other_client, skin_png):
    rid = analyze(client, skin_png, save="true").json()["id"]
    mine, theirs = client.get(f"/results/{rid}").text, other_client.get(f"/results/{rid}").text
    assert "hx-delete" in mine and "Make private" in mine
    assert "hx-delete" not in theirs and "Make private" not in theirs and "PUBLIC" in theirs
    assert "your approximate" in mine and "your approximate" not in theirs


def test_making_a_result_private_hides_it_from_others(client, other_client, skin_png):
    rid = analyze(client, skin_png, save="true").json()["id"]
    assert other_client.get(f"/results/{rid}").status_code == 200
    client.post(f"/results/{rid}/unsave", headers=HX)
    assert other_client.get(f"/results/{rid}").status_code == 404
    assert client.get(f"/results/{rid}").status_code == 200


def test_history_is_a_public_list_with_delete_only_on_my_cards(client, other_client, skin_png):
    mine = analyze(client, skin_png, save="true", name="Alice").json()["id"]
    theirs = analyze(other_client, skin_png, save="true", name="Bob").json()["id"]
    hidden = analyze(other_client, skin_png, name="Carol").json()["id"]  # unsaved: never listed
    page = client.get("/history").text
    assert mine in page and theirs in page and hidden not in page
    assert "Alice" in page and "Bob" in page and "Carol" not in page
    assert f"/results/{mine}?origin=history" in page and f"/results/{theirs}?origin=history" not in page
    anon = TestClient(app).get("/history").text  # visitors see everything but get no delete buttons
    assert mine in anon and theirs in anon and "hx-delete" not in anon


def test_public_pages_are_not_indexed_and_bad_page_param_is_safe(client, skin_png):
    rid = analyze(client, skin_png, save="true").json()["id"]
    assert "noindex" in client.get("/history").headers["x-robots-tag"]
    assert "noindex" in client.get(f"/results/{rid}").headers["x-robots-tag"]
    for q in ("abc", "-5", "0", "99999999"):
        assert client.get(f"/history?page={q}").status_code == 200


def test_history_paginates(client, skin_png, monkeypatch):
    import app.routes.pages as pages
    monkeypatch.setattr(pages, "PAGE_SIZE", 2)
    ids = [analyze(client, skin_png, save="true", name=f"P{i}").json()["id"] for i in range(3)]
    p1, p2 = client.get("/history").text, client.get("/history?page=2").text
    assert "Older" in p1 and "Newer" not in p1 and "Newer" in p2 and "Older" not in p2
    assert sum(i in p1 for i in ids) == 2 and sum(i in p2 for i in ids) == 1


def test_repository_visibility_rules(db, bundle):  # noqa: F811
    me, you, repo = owner(db), owner(db, "b" * 40), AnalysisRepository(db)
    private = repo.create(me.id, bundle, saved=False, shared=False, ttl_hours=24)
    public = repo.create(me.id, bundle, saved=True, shared=False, ttl_hours=24)
    assert repo.get_visible(public.id, None) is not None and repo.get_visible(public.id, you.id) is not None
    assert repo.get_visible(private.id, me.id) is not None
    assert repo.get_visible(private.id, you.id) is None and repo.get_visible(private.id, None) is None
    assert repo.count_saved() == 1 and [r.id for r in repo.list_all_saved()] == [public.id]


def test_analyze_page_guide_sample_is_commented_out_and_new_image_referenced(client):
    html = client.get("/analyze").text
    live = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    assert 'class="guide-sample"' in html and 'class="guide-sample"' not in live  # original kept, but inactive
    tag = re.search(r'<img class="guide-photo"[^>]*>', live).group(0)
    assert 'width="1599"' in tag and 'height="868"' in tag and "loading=" not in tag  # box reserved up front, no lazy pop-in
    src = re.search(r'src="([^"]+)"', tag).group(1)
    assert client.get(src).status_code == 200, f"{src} must exist (add heroes.jpeg to static/img/)"
