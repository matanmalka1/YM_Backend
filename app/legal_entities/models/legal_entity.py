from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.legal_entities.models.person_legal_entity_link import PersonLegalEntityLink

from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class LegalEntity(Base):
    """Legal and tax identity of a registered entity (sole trader, company, etc.)."""

    __tablename__ = "legal_entities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    id_number: Mapped[str] = mapped_column(String, nullable=False)
    id_number_type: Mapped[IdNumberType] = mapped_column(pg_enum(IdNumberType), nullable=False)
    entity_type: Mapped[EntityType | None] = mapped_column(pg_enum(EntityType), nullable=True)

    official_name: Mapped[str] = mapped_column(String, nullable=False)

    vat_reporting_frequency: Mapped[VatType | None] = mapped_column(pg_enum(VatType), nullable=True)
    advance_payment_frequency: Mapped[AdvancePaymentFrequency | None] = mapped_column(
        pg_enum(AdvancePaymentFrequency, name="advance_payment_frequency"),
        nullable=True,
    )
    vat_exempt_ceiling: Mapped[Decimal | None] = mapped_column(Numeric(12, 0), nullable=True)
    advance_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    advance_rate_updated_at: Mapped[date | None] = mapped_column(nullable=True)
    annual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(15, 0), nullable=True)

    # ── Liability ranges ──────────────────────────────────────────────────────
    # When this entity was, and stopped being, liable for each obligation type.
    # NULL is unbounded on that side, so a fully unconfigured client keeps today's
    # behaviour: liable for every period the frequency implies.
    #
    # Per type, not one client-wide date: an entity can register for VAT in June,
    # receive an ITA advance rate in September, and still owe a *full-year* annual
    # report for the same year. A single date cannot express that.
    #
    # These feed the obligation plan (`app/common/obligation_plan.py`), which is
    # the only thing that decides whether a period is owed.
    vat_liable_from: Mapped[date | None] = mapped_column(nullable=True)
    vat_liable_to: Mapped[date | None] = mapped_column(nullable=True)
    advance_liable_from: Mapped[date | None] = mapped_column(nullable=True)
    advance_liable_to: Mapped[date | None] = mapped_column(nullable=True)
    annual_liable_from: Mapped[date | None] = mapped_column(nullable=True)
    annual_liable_to: Mapped[date | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    person_links: Mapped[list[PersonLegalEntityLink]] = relationship(
        "PersonLegalEntityLink",
        primaryjoin="LegalEntity.id == foreign(PersonLegalEntityLink.legal_entity_id)",
        lazy="select",
        viewonly=True,
    )

    __table_args__ = (
        UniqueConstraint("id_number_type", "id_number", name="uq_legal_entity_registration_id"),
        Index("ix_legal_entities_official_name", "official_name"),
        # The request schemas reject an inverted range with a readable message, but
        # they are not the only writer — seed builders and internal services reach
        # the repository directly. An orderable range is a data invariant, so it is
        # guaranteed here. Same shape as ck_deadline_rule_effective_range.
        CheckConstraint(
            "vat_liable_to IS NULL OR vat_liable_from IS NULL OR vat_liable_to >= vat_liable_from",
            name="ck_legal_entity_vat_liability_range",
        ),
        CheckConstraint(
            "advance_liable_to IS NULL OR advance_liable_from IS NULL "
            "OR advance_liable_to >= advance_liable_from",
            name="ck_legal_entity_advance_liability_range",
        ),
        CheckConstraint(
            "annual_liable_to IS NULL OR annual_liable_from IS NULL "
            "OR annual_liable_to >= annual_liable_from",
            name="ck_legal_entity_annual_liability_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<LegalEntity(id={self.id}, id_number='{self.id_number}', entity_type='{self.entity_type}')>"
