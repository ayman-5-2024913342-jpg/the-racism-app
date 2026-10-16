"""Application factory for THE GREAT APP."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.config import BASE_DIR, get_settings
from app.db import create_all, get_engine, session_scope
from app.errors import AppError
from app.repositories import AnalysisRepository
from app.routes import api, pages
from app.security import SecurityMiddleware
from app.templating import render

logger = logging.getLogger("the_great_app")


def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/") or request.headers.get("hx-request") == "true"


def _error_response(request: Request, status_code: int, code: str, message: str, **extra):
    if _wants_json(request):
        return JSONResponse({"detail": message, "code": code, **extra}, status_code=status_code)
    return render(request, "error.html", {"page": "error", "title": "Something's off", "status_code": status_code, "message": message}, status_code=status_code)


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    get_engine()
    if s.auto_create_tables:
        create_all()
    try:
        with session_scope() as db:
            AnalysisRepository(db).purge_expired()
    except Exception:  # noqa: BLE001  (e.g. tables not migrated yet; do not block startup)
        logger.warning("Could not purge expired results at startup (are migrations applied?)")
    yield


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = FastAPI(
        title="THE GREAT APP", version=__version__, lifespan=lifespan,
        description="Photo-based skin tone analysis and personal color discovery.",
        docs_url=None if s.is_production else "/docs", redoc_url=None, openapi_url=None if s.is_production else "/openapi.json",
    )
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.allowed_hosts)  # added last = outermost
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(pages.router)
    app.include_router(api.router)

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return _error_response(request, exc.status_code, exc.code, exc.message, **exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        message = "We couldn't find that page." if exc.status_code == 404 else str(exc.detail)
        return _error_response(request, exc.status_code, "http_error", message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({"detail": "The request was invalid. Please check your input and try again.", "code": "invalid_request"}, status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s", request.url.path)  # path only: never log bodies or images
        return JSONResponse({"detail": "Something went wrong. Please try again.", "code": "server_error"}, status_code=500)

    return app


app = create_app()
