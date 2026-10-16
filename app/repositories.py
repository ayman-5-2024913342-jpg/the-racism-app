"""Repository layer: all database access goes through here (parameterised via SQLAlchemy)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models import Analysis, Owner, utcnow
from app.services.pipeline import AnalysisBundle


class OwnerRepository:
    def __init__(self, db: Session, pepper: str) -> None:
        self.db, self._pepper = db, pepper.encode()

    def hash_token(self, token: str) -> str:
        return hmac.new(self._pepper, token.encode(), hashlib.sha256).hexdigest()

    def get(self, token: str) -> Owner | None:
        return self.db.scalar(select(Owner).where(Owner.token_hash == self.hash_token(token)))

    def get_or_create(self, token: str) -> Owner:
        owner = self.get(token)
        if owner is None:
            owner = Owner(token_hash=self.hash_token(token))
            self.db.add(owner)
            self.db.flush()
        return owner

    def update_prefs(self, owner: Owner, *, save_by_default: bool, share_by_default: bool) -> Owner:
        owner.save_by_default = save_by_default
        owner.share_by_default = share_by_default and save_by_default  # sharing requires saving
        self.db.flush()
        return owner

    def delete(self, owner: Owner) -> None:
        self.db.execute(delete(Analysis).where(Analysis.owner_id == owner.id))
        self.db.delete(owner)
        self.db.flush()


class AnalysisRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, owner_id: str, bundle: AnalysisBundle, *, saved: bool, shared: bool, ttl_hours: int, name: str | None = None) -> Analysis:
        a = bundle.analysis
        now = utcnow()
        row = Analysis(
            id=secrets.token_urlsafe(16), owner_id=owner_id, created_at=now,
            expires_at=None if saved else now + timedelta(hours=ttl_hours),
            saved=saved, shared=saved and shared, name=name,
            r=a.rgb[0], g=a.rgb[1], b=a.rgb[2], hex=a.hex,
            lab_l=a.lab[0], lab_a=a.lab[1], lab_b=a.lab[2], lch_c=a.lch[1], lch_h=a.lch[2], ita=a.ita,
            shade_key=a.shade_key, shade_label=a.shade_label, shade_alternative=a.shade_alternative,
            undertone_key=a.undertone_key, undertone_label=a.undertone_label, undertone_note=a.undertone_note,
            confidence=a.confidence, confidence_label=a.confidence_label, n_samples=a.n_samples,
            skin_fraction=a.skin_fraction, region_method=a.region_method, algorithm_version=a.algorithm_version,
            factors=[asdict(f) for f in a.factors], warnings=list(a.warnings), palette=list(bundle.palette),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get_for_owner(self, result_id: str, owner_id: str) -> Analysis | None:
        """Returns None for unknown ids, other people's ids and expired unsaved results alike (no leakage)."""
        return self.db.scalar(
            select(Analysis).where(
                Analysis.id == result_id,
                Analysis.owner_id == owner_id,
                or_(Analysis.saved.is_(True), Analysis.expires_at > utcnow()),
            )
        )

    def get_visible(self, result_id: str, owner_id: str | None) -> Analysis | None:
        """Saved results are public: anyone may view them. Unsaved ones are visible only to their (unexpired) owner."""
        visible = Analysis.saved.is_(True)
        if owner_id is not None:
            visible = or_(visible, (Analysis.owner_id == owner_id) & (Analysis.expires_at > utcnow()))
        return self.db.scalar(select(Analysis).where(Analysis.id == result_id, visible))

    def list_all_saved(self, limit: int = 48, offset: int = 0) -> list[Analysis]:
        """Every saved result, newest first (the public list)."""
        return list(self.db.scalars(
            select(Analysis).where(Analysis.saved.is_(True)).order_by(Analysis.created_at.desc()).limit(limit).offset(offset)
        ))

    def count_saved(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Analysis).where(Analysis.saved.is_(True))) or 0)

    def list_saved(self, owner_id: str, limit: int = 100) -> list[Analysis]:
        return list(self.db.scalars(
            select(Analysis).where(Analysis.owner_id == owner_id, Analysis.saved.is_(True))
            .order_by(Analysis.created_at.desc()).limit(limit)
        ))

    def set_saved(self, row: Analysis, saved: bool, ttl_hours: int) -> Analysis:
        row.saved = saved
        row.expires_at = None if saved else utcnow() + timedelta(hours=ttl_hours)
        if not saved:
            row.shared = False
        self.db.flush()
        return row

    def set_shared(self, row: Analysis, shared: bool) -> Analysis:
        row.shared = shared and row.saved
        self.db.flush()
        return row

    def delete(self, row: Analysis) -> None:
        self.db.delete(row)
        self.db.flush()

    def delete_all_for_owner(self, owner_id: str) -> int:
        return self.db.execute(delete(Analysis).where(Analysis.owner_id == owner_id)).rowcount or 0

    def unshare_all(self, owner_id: str) -> int:
        return self.db.execute(
            update(Analysis).where(Analysis.owner_id == owner_id, Analysis.shared.is_(True)).values(shared=False)
        ).rowcount or 0

    def purge_expired(self) -> int:
        return self.db.execute(
            delete(Analysis).where(Analysis.saved.is_(False), Analysis.expires_at < utcnow())
        ).rowcount or 0

    # ---- aggregation (opt-in data only; never returns individual records) ----
    def shared_count(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Analysis).where(Analysis.shared.is_(True), Analysis.saved.is_(True))) or 0)

    def shared_lightness_values(self) -> list[float]:
        """Lightness only, no ids / owners / timestamps. Callers must aggregate before display."""
        return [float(v) for v in self.db.scalars(select(Analysis.lab_l).where(Analysis.shared.is_(True), Analysis.saved.is_(True)))]
