"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import Owner
from app.repositories import AnalysisRepository, OwnerRepository


def owners_repo(db: Session = Depends(get_db)) -> OwnerRepository:
    return OwnerRepository(db, get_settings().secret_key)


def analyses_repo(db: Session = Depends(get_db)) -> AnalysisRepository:
    return AnalysisRepository(db)


def existing_owner(request: Request, owners: OwnerRepository = Depends(owners_repo)) -> Owner | None:
    """The caller's owner row if one exists. Browsing never creates rows."""
    return owners.get(request.state.owner_token)


def require_owner(owner: Owner | None = Depends(existing_owner)) -> Owner:
    if owner is None:
        raise AppError("not_found", "We couldn't find that page.", 404)
    return owner
