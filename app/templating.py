from __future__ import annotations

from datetime import datetime

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import BASE_DIR, get_settings
from app.services.score import skin_score

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["datefmt"] = lambda v: v.strftime("%b %d, %Y") if isinstance(v, datetime) else ""
templates.env.filters["skin_score"] = skin_score
templates.env.filters["pct"] = lambda v: f"{round(float(v) * 100)}%"


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200, headers: dict | None = None):
    ctx = {"csrf_token": getattr(request.state, "csrf_token", ""), "app_version": __version__, "max_upload_mb": get_settings().max_upload_mb, "ttl_hours": get_settings().result_ttl_hours, **(context or {})}
    return templates.TemplateResponse(request=request, name=name, context=ctx, status_code=status_code, headers=headers)
