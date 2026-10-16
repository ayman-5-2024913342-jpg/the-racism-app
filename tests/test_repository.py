from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Analysis, utcnow
from app.repositories import AnalysisRepository, OwnerRepository
from app.services.pipeline import analyze_bytes
from tests.helpers import encode, skin_image


@pytest.fixture
def db():
    from app import models  # noqa: F401
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture(scope="module")
def bundle():
    return analyze_bytes(encode(skin_image()))


def owner(db, token="a" * 40):
    return OwnerRepository(db, "pepper").get_or_create(token)


def test_owner_token_hashed_and_stable(db):
    repo = OwnerRepository(db, "pepper")
    o = repo.get_or_create("t" * 40)
    assert o.token_hash != "t" * 40 and repo.get_or_create("t" * 40).id == o.id
    assert OwnerRepository(db, "other-pepper").hash_token("t" * 40) != o.token_hash


def test_create_and_authorized_lookup(db, bundle):
    me, you = owner(db), owner(db, "b" * 40)
    repo = AnalysisRepository(db)
    row = repo.create(me.id, bundle, saved=False, shared=True, ttl_hours=24)
    assert row.shared is False and row.expires_at is not None  # cannot share an unsaved result
    assert repo.get_for_owner(row.id, me.id) is not None
    assert repo.get_for_owner(row.id, you.id) is None
    assert repo.get_for_owner("nope", me.id) is None


def test_expiry_save_and_purge(db, bundle):
    me, repo = owner(db), AnalysisRepository(db)
    row = repo.create(me.id, bundle, saved=False, shared=False, ttl_hours=24)
    row.expires_at = utcnow() - timedelta(hours=1)
    db.flush()
    assert repo.get_for_owner(row.id, me.id) is None
    repo.set_saved(row, True, 24)
    assert row.expires_at is None and repo.get_for_owner(row.id, me.id) is not None
    row2 = repo.create(me.id, bundle, saved=False, shared=False, ttl_hours=24)
    row2.expires_at = utcnow() - timedelta(minutes=1)
    db.flush()
    assert repo.purge_expired() == 1 and db.get(Analysis, row.id) is not None


def test_sharing_rules_and_aggregation_exposes_only_lightness(db, bundle):
    me, repo = owner(db), AnalysisRepository(db)
    saved = repo.create(me.id, bundle, saved=True, shared=True, ttl_hours=24)
    repo.create(me.id, bundle, saved=True, shared=False, ttl_hours=24)
    repo.create(me.id, bundle, saved=False, shared=True, ttl_hours=24)
    assert repo.shared_count() == 1
    vals = repo.shared_lightness_values()
    assert vals == [pytest.approx(bundle.analysis.lab[0])] and all(isinstance(v, float) for v in vals)
    repo.set_saved(saved, False, 24)
    assert saved.shared is False and repo.shared_count() == 0


def test_unshare_all_and_delete_all(db, bundle):
    me, you, repo = owner(db), owner(db, "c" * 40), AnalysisRepository(db)
    for _ in range(3):
        repo.create(me.id, bundle, saved=True, shared=True, ttl_hours=24)
    repo.create(you.id, bundle, saved=True, shared=True, ttl_hours=24)
    assert repo.unshare_all(me.id) == 3 and repo.shared_count() == 1
    assert repo.delete_all_for_owner(me.id) == 3 and len(repo.list_saved(you.id)) == 1


def test_owner_delete_removes_all_their_data(db, bundle):
    me, repo = owner(db), AnalysisRepository(db)
    repo.create(me.id, bundle, saved=True, shared=True, ttl_hours=24)
    OwnerRepository(db, "pepper").delete(me)
    assert repo.shared_count() == 0 and db.query(Analysis).count() == 0
