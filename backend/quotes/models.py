from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core import Base


class QuoteDocument(Base):
    """One uploaded quote: its page text, what was extracted, and what failed verification."""
    __tablename__ = "quote_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(256))
    carrier: Mapped[str | None] = mapped_column(String(256), nullable=True)
    extractor: Mapped[str] = mapped_column(String(16))
    pages: Mapped[list] = mapped_column(JSON)
    extraction: Mapped[dict] = mapped_column(JSON)
    verification: Mapped[list] = mapped_column(JSON)
    rejected: Mapped[list] = mapped_column(JSON, default=list)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
