from __future__ import annotations

from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.enums import DeadlineRuleType as DRT
from app.common.enums import ObligationType
from app.common.period_utils import parse_period
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.repositories.tax_calendar_deadline_rule_repository import (
    DeadlineRuleRepository,
)
from app.tax_calendar.repositories.tax_calendar_entry_repository import TaxCalendarEntryRepository
from app.tax_calendar.services.tax_calendar_entry_service import (
    _resolve_rule,
    annual_due_date,
    periodic_due_date,
)

_PERIODIC_RULES = {
    (ObligationType.VAT, 1): DRT.VAT_MONTHLY,
    (ObligationType.VAT, 2): DRT.VAT_BIMONTHLY,
    (ObligationType.ADVANCE_PAYMENT, 1): DRT.ADVANCE_MONTHLY,
    (ObligationType.ADVANCE_PAYMENT, 2): DRT.ADVANCE_BIMONTHLY,
}


class TaxCalendarMaterializationService:
    def __init__(self, db: Session):
        self.db = db
        self.entry_repo = TaxCalendarEntryRepository(db)

    def ensure_periodic_entry(
        self, obligation_type, period: str, period_months_count: int
    ) -> TaxCalendarEntry:
        obligation_type = self._obligation(obligation_type)
        year, month = parse_period(period)
        rule_type = self._periodic_rule_type(obligation_type, period_months_count)
        self._validate_period_alignment(month, period_months_count)
        existing = self._find_periodic(obligation_type, period, period_months_count)
        if existing:
            return existing
        rule = self._resolve_required_rule(rule_type, date(year, 1, 1))
        entry = TaxCalendarEntry(
            obligation_type=obligation_type,
            period=period,
            period_months_count=period_months_count,
            tax_year=year,
            due_date=periodic_due_date(rule, year, month),
            deadline_rule_id=rule.id,
        )
        return self._insert_or_refetch(
            entry,
            lambda: self._find_periodic(obligation_type, period, period_months_count),
        )

    def get_periodic_entry(
        self, obligation_type, period: str, period_months_count: int
    ) -> TaxCalendarEntry | None:
        obligation_type = self._obligation(obligation_type)
        _year, month = parse_period(period)
        self._periodic_rule_type(obligation_type, period_months_count)
        self._validate_period_alignment(month, period_months_count)
        return self._find_periodic(obligation_type, period, period_months_count)

    def get_periodic_entries(
        self, obligation_type, periods: list[tuple[str, int]]
    ) -> dict[tuple[str, int], TaxCalendarEntry]:
        obligation_type = self._obligation(obligation_type)
        if not periods:
            return {}
        for period, months in periods:
            _year, month = parse_period(period)
            self._periodic_rule_type(obligation_type, months)
            self._validate_period_alignment(month, months)
        rows = self.entry_repo.list_periodic(obligation_type, periods)
        return {(row.period, row.period_months_count): row for row in rows}

    def ensure_annual_entry(self, tax_year: int) -> TaxCalendarEntry:
        tax_year = self._parse_tax_year(tax_year)
        existing = self._find_annual(tax_year)
        if existing:
            return existing
        rule = self._resolve_required_rule(DRT.ANNUAL_REPORT, date(tax_year + 1, 1, 1))
        entry = TaxCalendarEntry(
            obligation_type=ObligationType.ANNUAL_REPORT,
            period=None,
            period_months_count=None,
            tax_year=tax_year,
            due_date=annual_due_date(rule, tax_year),
            deadline_rule_id=rule.id,
        )
        return self._insert_or_refetch(entry, lambda: self._find_annual(tax_year))

    def link_vat_work_item(self, item):
        period_type = (
            item.period_type.value if hasattr(item.period_type, "value") else item.period_type
        )
        months = 2 if period_type == "bimonthly" else 1
        entry = self.ensure_periodic_entry(ObligationType.VAT, item.period, months)
        self._assign_entry(item, entry)
        if item.due_date_original is None:
            item.due_date_original = entry.due_date
        if item.due_date_effective is None:
            item.due_date_effective = entry.due_date
        self.db.flush()
        return item

    def link_advance_payment(self, payment):
        entry = self.ensure_periodic_entry(
            ObligationType.ADVANCE_PAYMENT, payment.period, payment.period_months_count
        )
        self._assign_entry(payment, entry)
        if payment.due_date_original is None:
            payment.due_date_original = entry.due_date
        if payment.due_date_effective is None:
            payment.due_date_effective = entry.due_date
        self.db.flush()
        return payment

    def link_annual_report(self, report):
        entry = self.ensure_annual_entry(report.tax_year)
        self._assign_entry(report, entry)
        self.db.flush()
        return report

    def _resolve_required_rule(self, rule_type, on_date: date):
        try:
            return _resolve_rule(
                DeadlineRuleRepository(self.db), rule_type=rule_type, on_date=on_date
            )
        except LookupError as exc:
            raise AppError(
                "לא מוגדר כלל מועד מתאים ליומן המס",
                ErrorCode.TAX_CALENDAR_DEADLINE_RULE_MISSING,
            ) from exc

    def _insert_or_refetch(self, entity, refetch):
        savepoint = self.db.begin_nested()
        try:
            self.entry_repo.add(entity)
            self.entry_repo.flush()
            savepoint.commit()
            return entity
        except IntegrityError:
            savepoint.rollback()
            existing = refetch()
            if existing:
                return existing
            raise

    def _find_periodic(self, obligation_type, period, months):
        obligation_type = self._obligation(obligation_type)
        return self.entry_repo.find_periodic(obligation_type, period, months)

    def _find_annual(self, tax_year: int):
        return self.entry_repo.find_annual(tax_year)

    @staticmethod
    def _periodic_rule_type(obligation_type, months):
        obligation_type = TaxCalendarMaterializationService._obligation(obligation_type)
        rule_type = _PERIODIC_RULES.get((obligation_type, months))
        if rule_type is None:
            raise AppError(
                "תקופת החובה אינה נתמכת", ErrorCode.TAX_CALENDAR_INVALID_PERIOD_FREQUENCY
            )
        return rule_type

    @staticmethod
    def _obligation(value):
        try:
            return value if isinstance(value, ObligationType) else ObligationType(value)
        except ValueError as exc:
            raise AppError(
                "סוג החובה אינו נתמך", ErrorCode.TAX_CALENDAR_INVALID_OBLIGATION_TYPE
            ) from exc

    @staticmethod
    def _validate_period_alignment(month: int, months: int) -> None:
        if months == 2 and month % 2 == 0:
            raise AppError(
                "תקופה דו-חודשית חייבת להתחיל בחודש אי-זוגי",
                ErrorCode.TAX_CALENDAR_INVALID_PERIOD_ALIGNMENT,
            )

    @staticmethod
    def _parse_tax_year(tax_year) -> int:
        try:
            year = int(tax_year)
        except (TypeError, ValueError) as exc:
            raise AppError("שנת המס אינה תקינה", ErrorCode.TAX_CALENDAR_INVALID_TAX_YEAR) from exc
        if year < 1900 or year > 2200:
            raise AppError("שנת המס אינה תקינה", ErrorCode.TAX_CALENDAR_INVALID_TAX_YEAR)
        return year

    @staticmethod
    def _assign_entry(entity, entry: TaxCalendarEntry) -> None:
        current = entity.tax_calendar_entry_id
        if current is None:
            entity.tax_calendar_entry_id = entry.id
            return
        if int(current) != int(entry.id):
            raise ConflictError(
                "רשומת יומן המס אינה תואמת לחובה", ErrorCode.TAX_CALENDAR_LINK_CONFLICT
            )
