from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.time_utils import utcnow


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    charge_id: Mapped[int] = mapped_column(
        ForeignKey("charges.id"), nullable=False, unique=True, index=True
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    external_invoice_id: Mapped[str] = mapped_column(String, nullable=False)
    document_url: Mapped[str | None] = mapped_column(String, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    def __repr__(self):
        return (
            f"<Invoice(id={self.id}, charge_id={self.charge_id}, "
            f"external_id='{self.external_invoice_id}')>"
        )
