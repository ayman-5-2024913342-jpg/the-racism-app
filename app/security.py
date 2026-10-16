"""Cookie identity, CSRF protection and security headers.

* ``tga_owner``: random token in an HttpOnly cookie. Anonymous identity; only a keyed hash is stored server-side.
* ``tga_csrf``: random token in an HttpOnly cookie (double-submit). Pages embed the same value in a <meta> tag;
  every non-GET request must echo it in the ``X-CSRF-Token`` header. An Origin check adds a second layer.
"""
from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

OWNER_COOKIE = "tga_owner"
CSRF_COOKIE = "tga_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ONE_YEAR = 60 * 60 * 24 * 365

CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def _valid(token: str | None) -> bool:
    return bool(token) and 32 <= len(token) <= 64 and all(c.isalnum() or c in "-_" for c in token)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        s = get_settings()
        owner, csrf = request.cookies.get(OWNER_COOKIE), request.cookies.get(CSRF_COOKIE)
        new_owner, new_csrf = not _valid(owner), not _valid(csrf)
        if new_owner:
            owner = secrets.token_urlsafe(32)
        if new_csrf:
            csrf = secrets.token_urlsafe(32)
        request.state.owner_token, request.state.csrf_token = owner, csrf

        response: Response | None = None
        if request.method not in SAFE_METHODS:
            response = self._reject(request, csrf, new_csrf, s)
        if response is None:
            response = await call_next(request)

        opts = dict(httponly=True, samesite="lax", secure=s.cookie_secure, max_age=ONE_YEAR, path="/")
        if new_owner:
            response.set_cookie(OWNER_COOKIE, owner, **opts)
        if new_csrf:
            response.set_cookie(CSRF_COOKIE, csrf, **opts)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if s.is_production:
            response.headers.setdefault("Content-Security-Policy", CSP)
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @staticmethod
    def _reject(request: Request, csrf: str, new_csrf: bool, s) -> Response | None:
        origin = request.headers.get("origin")
        if origin and origin != "null":
            host = urlparse(origin).netloc
            if host != request.headers.get("host") and origin not in s.trusted_origins:
                return JSONResponse({"detail": "Cross-origin request blocked.", "code": "bad_origin"}, status_code=403)
        sent = request.headers.get("x-csrf-token", "")
        if new_csrf or not hmac.compare_digest(sent.encode(), csrf.encode()):
            return JSONResponse(
                {"detail": "Your session expired. Please reload the page and try again.", "code": "csrf_failed"},
                status_code=403,
            )
        return None
