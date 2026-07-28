"""TaxCalendarEntry — regulatory deadline fact for a period.

Generic per-period regulatory fact, not per-client. One entry per
(obligation_type, period, period_months_count) for periodic obligations,
or per (obligation_type, tax_year) for ANNUAL_REPORT.

Validation strategy:
- @validates handlers reject obviously bad single-field values early.
- before_insert / before_update event listeners run the full cross-field
  consistency check (covers cases that bypass individual @validates,
  e.g. when a field is left at its default).
- Bulk-insert paths (session.execute, Core inserts) bypass ORM events;
  DB-level CheckConstraints + partial unique indexes provide that backstop.

Compatibility matrix (obligation_type → allowed rule_type):
    VAT             : vat_monthly, vat_bimonthly
    ADVANCE_PAYMENT : advance_monthly, advance_bimonthly
    ANNUAL_REPORT   : annual_report
    NATIONAL_INSURANCE: <unsupported in PR 1 — no matching DeadlineRuleType>
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.common.enums import DeadlineRuleType, ObligationType
from app.common.period_utils import PERIOD_PATTERN, parse_period_year
from app.database import Base
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow

_RULE_COMPATIBILITY: dict[ObligationType, set[DeadlineRuleType]] = {
    ObligationType.VAT: {DeadlineRuleType.VAT_MONTHLY, DeadlineRuleType.VAT_BIMONTHLY},
    ObligationType.ADVANCE_PAYMENT: {
        DeadlineRuleType.ADVANCE_MONTHLY,
        DeadlineRuleType.ADVANCE_BIMONTHLY,
    },
    ObligationType.ANNUAL_REPORT: {DeadlineRuleType.ANNUAL_REPORT},
}


def _coerce_obligation(value):
    if value is None or isinstance(value, ObligationType):
        return value
    return ObligationType(value)


def _coerce_rule_type(value):
    if value is None or isinstance(value, DeadlineRuleType):
        return value
    return DeadlineRuleType(value)


class TaxCalendarEntry(Base):
    """Per-period regulatory deadline fact, shared across all clients."""

    __tablename__ = "tax_calendar_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    obligation_type: Mapped[ObligationType] = mapped_column(
        pg_enum(ObligationType), nullable=False, index=True
    )
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    period_months_count: Mapped[int | None] = mapped_column(nullable=True)
    tax_year: Mapped[int] = mapped_column(nullable=False)
    due_date: Mapped[date] = mapped_column(nullable=False, index=True)

    deadline_rule_id: Mapped[int] = mapped_column(
        ForeignKey("deadline_rules.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint(
            "(obligation_type = 'annual_report' AND period IS NULL) "
            "OR (obligation_type <> 'annual_report' AND period IS NOT NULL)",
            name="ck_tax_calendar_entry_period_nullability",
        ),
        CheckConstraint(
            "(obligation_type = 'annual_report' AND period_months_count IS NULL) "
            "OR (obligation_type <> 'annual_report' "
            "    AND period_months_count IN (1, 2))",
            name="ck_tax_calendar_entry_months_count",
        ),
        Index(
            "uq_tax_calendar_entry_periodic",
            "obligation_type",
            "period",
            "period_months_count",
            unique=True,
            postgresql_where=text("obligation_type <> 'annual_report'"),
        ),
        Index(
            "uq_tax_calendar_entry_annual",
            "obligation_type",
            "tax_year",
            unique=True,
            postgresql_where=text("obligation_type = 'annual_report'"),
        ),
        Index(
            "idx_tax_calendar_entries_year_obligation",
            "tax_year",
            "obligation_type",
        ),
    )

    @validates("period")
    def _validate_period(self, _key, value):
        if value is not None and not PERIOD_PATTERN.match(value):
            raise ValueError(f"Invalid period format '{value}'. Expected 'YYYY-MM' (month 01-12).")
        return value

    @validates("period_months_count")
    def _validate_months_count(self, _key, value):
        if value is not None and value not in (1, 2):
            raise ValueError(f"period_months_count must be 1 or 2, got {value}.")
        return value

    def __repr__(self) -> str:
        return (
            f"<TaxCalendarEntry(id={self.id}, type='{self.obligation_type}', "
            f"period='{self.period}', months={self.period_months_count}, "
            f"tax_year={self.tax_year}, due={self.due_date})>"
        )


def _validate_consistency(entry: TaxCalendarEntry, db_session=None) -> None:
    """Full cross-field validation. Called by ORM events; safe to call ad-hoc.

    Covers all rules that cannot be expressed cleanly as single-column
    @validates. Raises ValueError on the first failure.
    """
    obligation = _coerce_obligation(entry.obligation_type)
    if obligation is None:
        raise ValueError("obligation_type is required.")

    if obligation is ObligationType.NATIONAL_INSURANCE:
        raise ValueError(
            "NATIONAL_INSURANCE is not yet supported in TaxCalendarEntry. "
            "No matching DeadlineRuleType exists."
        )

    period = entry.period
    months_count = entry.period_months_count

    if obligation is ObligationType.ANNUAL_REPORT:
        if period is not None:
            raise ValueError("ANNUAL_REPORT entries must have period=NULL.")
        if months_count is not None:
            raise ValueError("ANNUAL_REPORT entries must have period_months_count=NULL.")
    else:
        if period is None:
            raise ValueError(f"{obligation.value} entries require a period.")
        if not PERIOD_PATTERN.match(period):
            raise ValueError(f"Invalid period format '{period}'. Expected 'YYYY-MM' (month 01-12).")
        if months_count is None or months_count not in (1, 2):
            raise ValueError(f"{obligation.value} entries require period_months_count in (1, 2).")
        if entry.tax_year is None:
            raise ValueError("tax_year is required.")
        if parse_period_year(period) != int(entry.tax_year):
            raise ValueError(
                f"period year ({period[:4]}) does not match tax_year ({entry.tax_year})."
            )

    rule_id = entry.deadline_rule_id
    if rule_id is None:
        raise ValueError("deadline_rule_id is required.")

    if db_session is not None:
        rule = db_session.get(DeadlineRule, rule_id)
        if rule is None:
            raise ValueError(f"DeadlineRule id={rule_id} does not exist.")
        rule_type = _coerce_rule_type(rule.rule_type)
        allowed = _RULE_COMPATIBILITY.get(obligation, set())
        if rule_type not in allowed:
            raise ValueError(
                f"DeadlineRule rule_type '{rule_type.value}' is not compatible "
                f"with obligation_type '{obligation.value}'. "
                f"Allowed: {sorted(r.value for r in allowed)}."
            )


@event.listens_for(TaxCalendarEntry, "before_insert")
def _before_insert(_mapper, _connection, target):
    from sqlalchemy.orm import Session

    session = Session.object_session(target)
    _validate_consistency(target, db_session=session)


@event.listens_for(TaxCalendarEntry, "before_update")
def _before_update(_mapper, _connection, target):
    from sqlalchemy.orm import Session

    session = Session.object_session(target)
    _validate_consistency(target, db_session=session)
