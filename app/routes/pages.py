"""Server-rendered pages and HTMX partials."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.db import get_db
from app.deps import analyses_repo, existing_owner, owners_repo, require_owner
from app.errors import AppError
from app.models import Analysis, Owner
from app.repositories import AnalysisRepository, OwnerRepository
from app.security import OWNER_COOKIE
from app.services.distribution import histogram, render_chart, synthetic_lightness
from app.services.export import DISCLAIMER, palette_png
from app.services.score import curve_svg, ordinal, percentile, skin_score
from app.templating import render

router = APIRouter()


def _get_result(result_id: str, owner: Owner, repo: AnalysisRepository) -> Analysis:
    row = repo.get_for_owner(result_id, owner.id)
    if row is None:
        raise AppError("not_found", "We couldn't find that result. It may have expired or been deleted.", 404)
    return row


def _get_visible(result_id: str, owner: Owner | None, repo: AnalysisRepository) -> Analysis:
    """Saved results can be viewed by anyone; unsaved ones only by their owner. Unknown/expired ids give 404."""
    row = repo.get_visible(result_id, owner.id if owner else None)
    if row is None:
        raise AppError("not_found", "We couldn't find that result. It may have expired or been deleted.", 404)
    return row


NOINDEX = {"X-Robots-Tag": "noindex, nofollow"}  # public results/list should not be crawled by search engines
PAGE_SIZE = 48


def _actions(request: Request, row: Analysis):
    return render(request, "partials/result_actions.html", {"r": row, "is_owner": True})  # only owners reach the action routes


# ------------------------------------------------------------------ static-ish pages
@router.get("/", name="home")
async def home(request: Request):
    return render(request, "index.html", {"page": "home", "title": "Discover your colors"})


@router.get("/analyze", name="analyze")
def analyze_page(request: Request, owner: Owner | None = Depends(existing_owner)):
    s = get_settings()
    return render(request, "analyze.html", {
        "page": "analyze", "title": "Analyze a photo", "max_upload_mb": s.max_upload_mb,
        "save_default": bool(owner and owner.save_by_default), "ttl_hours": s.result_ttl_hours,
    })


# ------------------------------------------------------------------ results
@router.get("/results/{result_id}", name="results")
def results_page(request: Request, result_id: str, owner: Owner | None = Depends(existing_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    row = _get_visible(result_id, owner, repo)
    s = get_settings()
    score = skin_score(row.lab_l)
    pct = percentile(score, s.score_mean, s.score_sd)
    return render(request, "results.html", {
        "page": "results", "title": "Your results" if (owner and row.owner_id == owner.id) else "Saved result", "r": row, "disclaimer": DISCLAIMER, "ttl_hours": s.result_ttl_hours,
        "is_owner": bool(owner and row.owner_id == owner.id),
        "score": score, "pct": pct, "pct_ordinal": ordinal(min(99, max(1, round(pct)))),
        "score_mean": s.score_mean, "score_sd": s.score_sd,
        "curve": curve_svg(score, s.score_mean, s.score_sd, row.name),
    }, headers=NOINDEX)


@router.post("/results/{result_id}/save", name="save_result")
def save_result(request: Request, result_id: str, db: Session = Depends(get_db), owner: Owner = Depends(require_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    row = repo.set_saved(_get_result(result_id, owner, repo), True, get_settings().result_ttl_hours)
    db.commit()
    return _actions(request, row)


@router.post("/results/{result_id}/unsave", name="unsave_result")
def unsave_result(request: Request, result_id: str, db: Session = Depends(get_db), owner: Owner = Depends(require_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    row = repo.set_saved(_get_result(result_id, owner, repo), False, get_settings().result_ttl_hours)
    db.commit()
    return _actions(request, row)


@router.post("/results/{result_id}/share", name="share_result")
def share_result(request: Request, result_id: str, db: Session = Depends(get_db), owner: Owner = Depends(require_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    row = _get_result(result_id, owner, repo)
    if not row.saved:
        raise AppError("save_first", "Save this result first. Only saved results can be contributed.", 409)
    repo.set_shared(row, True)
    db.commit()
    return _actions(request, row)


@router.post("/results/{result_id}/unshare", name="unshare_result")
def unshare_result(request: Request, result_id: str, db: Session = Depends(get_db), owner: Owner = Depends(require_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    row = repo.set_shared(_get_result(result_id, owner, repo), False)
    db.commit()
    return _actions(request, row)


@router.delete("/results/{result_id}", name="delete_result")
def delete_result(result_id: str, origin: str = "result", db: Session = Depends(get_db), owner: Owner | None = Depends(existing_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    row = _get_visible(result_id, owner, repo)
    if owner is None or row.owner_id != owner.id:  # public to view, but only the creating browser may delete
        raise AppError("forbidden", "Only the browser that created this result can delete it.", 403)
    repo.delete(row)
    db.commit()
    if origin == "history":
        return Response(status_code=200)  # htmx swaps the card out
    return Response(status_code=200, headers={"HX-Redirect": "/history"})


def _export_dict(r: Analysis) -> dict:
    return {
        "generated_by": f"THE GREAT APP v{__version__}", "algorithm_version": r.algorithm_version,
        "created_at": r.created_at.replace(tzinfo=timezone.utc).isoformat(),
        "sampled_color": {
            "hex": r.hex, "rgb": [r.r, r.g, r.b],
            "cielab_d65": {"L": round(r.lab_l, 2), "a": round(r.lab_a, 2), "b": round(r.lab_b, 2)},
            "lch": {"L": round(r.lab_l, 2), "C": round(r.lch_c, 2), "h_deg": round(r.lch_h, 1)},
        },
        "shade_band": {"label": r.shade_label, "ita_deg": round(r.ita, 1), "near_boundary_with": r.shade_alternative},
        "undertone": {"label": r.undertone_label, "note": r.undertone_note},
        "reliability": {"score": round(r.confidence, 3), "label": r.confidence_label, "factors": r.factors,
                        "samples": r.n_samples, "skin_fraction": round(r.skin_fraction, 3), "region_method": r.region_method},
        "warnings": r.warnings, "palette": r.palette, "disclaimer": DISCLAIMER,
    }


@router.get("/results/{result_id}/export.json", name="export_json")
def export_json(result_id: str, owner: Owner | None = Depends(existing_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    row = _get_visible(result_id, owner, repo)
    return JSONResponse(_export_dict(row), headers={"Content-Disposition": 'attachment; filename="the-great-app-result.json"', "Cache-Control": "no-store"})


@router.get("/results/{result_id}/palette.png", name="export_png")
def export_png(result_id: str, owner: Owner | None = Depends(existing_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    r = _get_visible(result_id, owner, repo)
    png = palette_png(r.hex, r.shade_label, r.undertone_label, r.palette)
    return Response(png, media_type="image/png", headers={"Content-Disposition": 'attachment; filename="the-great-app-palette.png"', "Cache-Control": "no-store"})


# ------------------------------------------------------------------ history & settings
@router.get("/history", name="history")
def history_page(request: Request, page: str = "1", owner: Owner | None = Depends(existing_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    """Public list of every saved result. Anyone can view; only each result's owner sees a Delete button."""
    try:
        page_no = min(max(int(page), 1), 100_000)
    except ValueError:
        page_no = 1
    total = repo.count_saved()
    rows = repo.list_all_saved(PAGE_SIZE, (page_no - 1) * PAGE_SIZE)
    return render(request, "history.html", {
        "page": "history", "title": "Saved results", "rows": rows, "me": owner.id if owner else None,
        "total": total, "page_no": page_no, "has_prev": page_no > 1, "has_next": page_no * PAGE_SIZE < total,
    }, headers=NOINDEX)


@router.get("/settings", name="settings")
def settings_page(request: Request, owner: Owner | None = Depends(existing_owner)):
    return render(request, "settings.html", {
        "page": "settings", "title": "Settings",
        "save_default": bool(owner and owner.save_by_default), "share_default": bool(owner and owner.share_by_default),
        "ttl_hours": get_settings().result_ttl_hours,
    })


@router.post("/settings", name="update_settings")
def update_settings(
    request: Request,
    save_by_default: bool = Form(False),
    share_by_default: bool = Form(False),
    db: Session = Depends(get_db),
    owners: OwnerRepository = Depends(owners_repo),
):
    owner = owners.get_or_create(request.state.owner_token)
    owners.update_prefs(owner, save_by_default=save_by_default, share_by_default=share_by_default)
    db.commit()
    return render(request, "partials/flash.html", {"message": "Preferences saved.", "kind": "success"})


@router.post("/settings/withdraw-shared", name="withdraw_shared")
def withdraw_shared(request: Request, db: Session = Depends(get_db), owner: Owner | None = Depends(existing_owner), repo: AnalysisRepository = Depends(analyses_repo)):
    n = repo.unshare_all(owner.id) if owner else 0
    db.commit()
    return render(request, "partials/flash.html", {"message": f"Withdrawn {n} contribution{'s' if n != 1 else ''} from the distribution.", "kind": "success"})


@router.post("/settings/delete-all", name="delete_all")
def delete_all(owner: Owner | None = Depends(existing_owner), db: Session = Depends(get_db), owners: OwnerRepository = Depends(owners_repo)):
    if owner:
        owners.delete(owner)
        db.commit()
    resp = Response(status_code=200, headers={"HX-Redirect": "/"})
    resp.delete_cookie(OWNER_COOKIE, path="/")
    return resp


# ------------------------------------------------------------------ distribution
def _distribution_values(repo: AnalysisRepository, source: str | None):
    s = get_settings()
    n_real = repo.shared_count()
    real_ok = n_real >= s.distribution_min_n
    if source == "real" and not real_ok:
        raise AppError("not_enough_data", "There is not yet enough opt-in data to show a real distribution.", 409)
    mode = "real" if real_ok and source != "synthetic" else "synthetic"
    values = repo.shared_lightness_values() if mode == "real" else synthetic_lightness()
    return mode, values, n_real, real_ok, s.distribution_min_n


@router.get("/distribution", name="distribution")
def distribution_page(request: Request, source: str | None = None, repo: AnalysisRepository = Depends(analyses_repo)):
    mode, values, n_real, real_ok, min_n = _distribution_values(repo, source if source in ("real", "synthetic") else None)
    return render(request, "distribution.html", {
        "page": "distribution", "title": "Color distribution", "mode": mode, "n_shown": int(len(values)),
        "n_real": n_real, "real_ok": real_ok, "min_n": min_n, "rows": histogram(values, suppress=(mode == "real")),
    })


@router.get("/distribution/chart.png", name="distribution_chart")
def distribution_chart(source: str | None = None, repo: AnalysisRepository = Depends(analyses_repo)):
    mode, values, *_ = _distribution_values(repo, source if source in ("real", "synthetic") else None)
    png = render_chart(values, synthetic=(mode == "synthetic"))
    cache = "public, max-age=3600" if mode == "synthetic" else "no-store"
    return Response(png, media_type="image/png", headers={"Cache-Control": cache})


# ------------------------------------------------------------------ health
@router.get("/health", name="health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "database": "unavailable"}, status_code=503)
    return {"status": "ok", "app": "THE GREAT APP", "version": __version__, "database": database}
