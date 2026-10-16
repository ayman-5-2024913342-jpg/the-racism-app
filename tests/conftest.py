"""Test configuration. Environment is set BEFORE the app is imported (settings are cached)."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="tga-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["DISTRIBUTION_MIN_N"] = "5"
os.environ["APP_ENV"] = "development"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from tests.helpers import encode, skin_image  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    from app import models  # noqa: F401
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def make_client() -> TestClient:
    c = TestClient(app)
    c.__enter__()
    c.get("/")  # receives the owner + CSRF cookies
    c.headers["X-CSRF-Token"] = c.cookies.get("tga_csrf")
    return c


@pytest.fixture
def client():
    c = make_client()
    yield c
    c.__exit__(None, None, None)


@pytest.fixture
def other_client():
    c = make_client()
    yield c
    c.__exit__(None, None, None)


@pytest.fixture
def skin_png() -> bytes:
    return encode(skin_image())


def analyze(c, png: bytes, **form):
    form.setdefault("name", "Test User")  # a name is now required before analysis
    return c.post("/api/analyze", files={"file": ("crop.png", png, "image/png")}, data=form)
