"""Database models. Only computed colour values and metadata are stored: never the uploaded image."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    """Naive UTC (portable between SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_owner_id() -> str:
    return uuid.uuid4().hex


class Owner(Base):
    """An anonymous browser identity (no accounts). Only a keyed hash of the cookie token is stored."""
    __tablename__ = "owners"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_owner_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    save_by_default: Mapped[bool] = mapped_column(Boolean, default=False)
    share_by_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # secrets.token_urlsafe(16)
    owner_id: Mapped[str] = mapped_column(String(32), ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)  # None once saved
    saved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    shared: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # opt-in anonymous aggregation
    name: Mapped[str | None] = mapped_column(String(40), nullable=True)  # entered before analysis; null on older rows

    r: Mapped[int] = mapped_column(Integer)
    g: Mapped[int] = mapped_column(Integer)
    b: Mapped[int] = mapped_column(Integer)
    hex: Mapped[str] = mapped_column(String(7))
    lab_l: Mapped[float] = mapped_column(Float)
    lab_a: Mapped[float] = mapped_column(Float)
    lab_b: Mapped[float] = mapped_column(Float)
    lch_c: Mapped[float] = mapped_column(Float)
    lch_h: Mapped[float] = mapped_column(Float)
    ita: Mapped[float] = mapped_column(Float)
    shade_key: Mapped[str] = mapped_column(String(16))
    shade_label: Mapped[str] = mapped_column(String(32))
    shade_alternative: Mapped[str | None] = mapped_column(String(32), nullable=True)
    undertone_key: Mapped[str] = mapped_column(String(16))
    undertone_label: Mapped[str] = mapped_column(String(48))
    undertone_note: Mapped[str] = mapped_column(String(200))
    confidence: Mapped[float] = mapped_column(Float)
    confidence_label: Mapped[str] = mapped_column(String(16))
    n_samples: Mapped[int] = mapped_column(Integer)
    skin_fraction: Mapped[float] = mapped_column(Float)
    region_method: Mapped[str] = mapped_column(String(24))
    algorithm_version: Mapped[str] = mapped_column(String(16))
    factors: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    palette: Mapped[list] = mapped_column(JSON, default=list)
