from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from ..core import Base


class GtmAccount(Base):
    """One row per real-world company: the single source of truth."""
    __tablename__ = "gtm_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "domain", name="uq_gtm_accounts_tenant_domain"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    canonical_name: Mapped[str] = mapped_column(String(256))
    name_key: Mapped[str] = mapped_column(String(256), index=True)
    domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owners: Mapped[list] = mapped_column(JSON, default=list)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    last_touch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GtmRawRecord(Base):
    """Every record exactly as a source sent it, linked to the account it resolved to."""
    __tablename__ = "gtm_raw_records"
    __table_args__ = (UniqueConstraint("tenant_id", "source", "source_record_id",
                                       name="uq_gtm_raw_tenant_source_record"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64))
    source_record_id: Mapped[str] = mapped_column(String(128))
    account_id: Mapped[int] = mapped_column(ForeignKey("gtm_accounts.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    match_method: Mapped[str] = mapped_column(String(16))
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GtmDeadLetter(Base):
    """Rows we refused to load, with the reason, so nothing disappears silently."""
    __tablename__ = "gtm_dead_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
