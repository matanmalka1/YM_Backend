from __future__ import annotations

from datetime import date, datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    Text,
    and_,
    column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.soft_delete import SoftDeletableMixin
from app.database import Base

if TYPE_CHECKING:
    from app.legal_entities.models.legal_entity import LegalEntity
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class BusinessStatus(str, PyEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class Business(SoftDeletableMixin, Base):
    """
    A specific business under a client.

    A client can hold multiple businesses (multiple operational activities under the same legal entity).
    Business-scoped records may reference this model directly, while tax/reporting workflows that are
    legally scoped to the client keep their primary ownership on Client and may only tag individual
    records to a business.

    Contact override columns are persisted here. Owner fallback is resolved in the service layer.
    """

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    legal_entity_id: Mapped[int] = mapped_column(
        ForeignKey("legal_entities.id"), nullable=False, index=True
    )

    legal_entity: Mapped[LegalEntity] = relationship(
        "LegalEntity",
        foreign_keys=[legal_entity_id],
        lazy="select",
        viewonly=True,
    )

    # Business details.
    business_name: Mapped[str] = mapped_column(
        String, nullable=False
    )  # required: every activity must have a name
    status: Mapped[BusinessStatus] = mapped_column(
        pg_enum(BusinessStatus),
        default=BusinessStatus.ACTIVE,
        nullable=False,
    )
    # Dates.
    opened_at: Mapped[date] = mapped_column(nullable=False)
    closed_at: Mapped[date | None] = mapped_column(nullable=True)

    # Business-specific contact overrides.
    phone_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email_override: Mapped[str | None] = mapped_column(String(254), nullable=True)

    # Metadata.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def full_name(self) -> str:
        if self.business_name:
            return self.business_name
        if self.legal_entity:
            return self.legal_entity.official_name
        return ""

    def __repr__(self):
        return (
            f"<Business(id={self.id}, legal_entity_id={self.legal_entity_id}, "
            f"name='{self.business_name}', status='{self.status}')>"
        )

    __table_args__ = (
        Index("ix_business_status", "status"),
        Index(
            "ix_business_legal_entity_name_active",
            "legal_entity_id",
            "business_name",
            unique=True,
            postgresql_where=and_(
                column("business_name").isnot(None), column("deleted_at").is_(None)
            ),
            sqlite_where=and_(column("business_name").isnot(None), column("deleted_at").is_(None)),
        ),
    )
