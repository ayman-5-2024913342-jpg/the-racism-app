"""Environment-based configuration. Secrets come from the environment, never from source control.

Variable names are unchanged from Milestone 2 (APP_ENV, APP_SECRET_KEY, DATABASE_URL, MAX_UPLOAD_MB, LOG_LEVEL).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_PLACEHOLDER_SECRETS = {"", "replace-this-before-deployment", "dev-only-insecure-secret"}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    return default if not raw else [p.strip() for p in raw.split(",") if p.strip()]


def normalize_db_url(url: str) -> str:
    """Hosting providers often hand out postgres:// URLs; SQLAlchemy needs a driver name (psycopg 3)."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@dataclass(frozen=True)
class Settings:
    env: str
    secret_key: str
    database_url: str
    allowed_hosts: list[str]
    trusted_origins: list[str]
    max_upload_mb: int
    max_image_side: int
    max_image_pixels: int
    min_image_side: int
    max_preview_side: int
    max_analysis_side: int
    result_ttl_hours: int
    distribution_min_n: int
    cookie_secure: bool
    auto_create_tables: bool
    rate_limit_per_minute: int
    max_concurrent_analyses: int
    log_level: str
    score_mean: float
    score_sd: float

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    _load_dotenv(BASE_DIR / ".env")
    env = os.environ.get("APP_ENV", "development").lower()
    secret = os.environ.get("APP_SECRET_KEY") or os.environ.get("SECRET_KEY", "dev-only-insecure-secret")
    if env == "production" and (secret in _PLACEHOLDER_SECRETS or len(secret) < 32):
        raise RuntimeError("APP_SECRET_KEY must be set to a random value of 32+ characters in production.")
    return Settings(
        env=env,
        secret_key=secret,
        database_url=normalize_db_url(os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'the_great_app.db'}")),
        allowed_hosts=_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"]),
        trusted_origins=_list("TRUSTED_ORIGINS", ["http://localhost:8000", "http://127.0.0.1:8000"]),
        max_upload_mb=max(1, min(_int("MAX_UPLOAD_MB", 10), 20)),
        max_image_side=_int("MAX_IMAGE_SIDE", 6000),
        max_image_pixels=_int("MAX_IMAGE_PIXELS", 24_000_000),
        min_image_side=_int("MIN_IMAGE_SIDE", 32),
        max_preview_side=_int("MAX_PREVIEW_SIDE", 3000),
        max_analysis_side=_int("MAX_ANALYSIS_SIDE", 640),
        result_ttl_hours=_int("RESULT_TTL_HOURS", 24),
        distribution_min_n=_int("DISTRIBUTION_MIN_N", 50),
        cookie_secure=_bool("COOKIE_SECURE", env == "production"),
        auto_create_tables=_bool("AUTO_CREATE_TABLES", env != "production"),
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 20),
        max_concurrent_analyses=_int("MAX_CONCURRENT_ANALYSES", 2),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        score_mean=_float("SCORE_MEAN", 50.0),
        score_sd=max(1.0, _float("SCORE_SD", 15.0)),
    )
