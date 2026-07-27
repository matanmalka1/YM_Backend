"""DeadlineRule — versioned regulatory rule for TaxCalendar due dates.

Lookup engine only — versioned via effective_from/effective_to so that historic
calculations remain stable when the law changes. Maps to an ObligationType:

    vat_monthly       → VAT
    vat_bimonthly     → VAT
    advance_monthly   → ADVANCE_PAYMENT
    advance_bimonthly → ADVANCE_PAYMENT
    annual_report     → ANNUAL_REPORT

INV-11: Only one open-ended rule (effective_to IS NULL) per rule_type is allowed.
Enforced at DB level via uq_deadline_rule_open_ended partial unique index.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import DeadlineRuleType
from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class DeadlineRule(Base):
    """Regulatory rule for computing a TaxCalendar due date."""

    __tablename__ = "deadline_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    rule_type: Mapped[DeadlineRuleType] = mapped_column(
        pg_enum(DeadlineRuleType), nullable=False, index=True
    )

    due_day_of_month: Mapped[int] = mapped_column(nullable=False)
    offset_months: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    effective_from: Mapped[date] = mapped_column(nullable=False)
    effective_to: Mapped[date | None] = mapped_column(nullable=True)

    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_deadline_rule_effective_range",
        ),
        CheckConstraint(
            "due_day_of_month BETWEEN 1 AND 31",
            name="ck_deadline_rule_due_day_range",
        ),
        CheckConstraint(
            "offset_months >= 0",
            name="ck_deadline_rule_offset_months_non_negative",
        ),
        Index("idx_deadline_rule_type_effective", "rule_type", "effective_from"),
        Index(
            "uq_deadline_rule_open_ended",
            "rule_type",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DeadlineRule(id={self.id}, type='{self.rule_type}', "
            f"day={self.due_day_of_month}, offset={self.offset_months}, "
            f"from={self.effective_from}, to={self.effective_to})>"
        )
