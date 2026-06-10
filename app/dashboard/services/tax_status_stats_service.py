from datetime import date

from sqlalchemy.orm import Session

from app.advance_payments.repositories.advance_payment_dashboard_repository import (
    AdvancePaymentDashboardRepository,
)
from app.clients.repositories.client_vat_stats_repository import (
    ClientVatStatsRepository,
)
from app.common.enums import ObligationType, VatType
from app.common.period_utils import (
    bimonthly_advance_payment_period,
    bimonthly_vat_period,
    monthly_vat_period,
)
from app.tax_calendar.services.materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.repositories.vat_work_item_stats_repository import (
    VatWorkItemStatsRepository,
)


class TaxStatusStatsService:
    def __init__(self, db: Session):
        self.client_repo = ClientVatStatsRepository(db)
        self.vat_repo = VatWorkItemStatsRepository(db)
        self.advance_repo = AdvancePaymentDashboardRepository(db)
        self.materializer = TaxCalendarMaterializationService(db)

    def build(self, reference_date: date) -> dict:
        monthly_period, monthly_label = monthly_vat_period(reference_date)
        bimonthly_period, bimonthly_label = bimonthly_vat_period(reference_date)
        required_by_type = self.client_repo.count_active_by_vat_types(
            [VatType.MONTHLY, VatType.BIMONTHLY]
        )
        submitted_by_period_type = self.vat_repo.count_filed_by_period_types(
            [
                (monthly_period, VatType.MONTHLY),
                (bimonthly_period, VatType.BIMONTHLY),
            ]
        )
        monthly_required = required_by_type.get(VatType.MONTHLY, 0)
        monthly_submitted = submitted_by_period_type.get((monthly_period, VatType.MONTHLY), 0)
        bimonthly_required = required_by_type.get(VatType.BIMONTHLY, 0)
        bimonthly_submitted = submitted_by_period_type.get((bimonthly_period, VatType.BIMONTHLY), 0)
        due_dates = self._due_dates(
            [
                (monthly_period, 1, monthly_required, monthly_submitted),
                (bimonthly_period, 2, bimonthly_required, bimonthly_submitted),
            ]
        )
        return {
            "monthly": self._build_stat(
                VatType.MONTHLY,
                monthly_period,
                monthly_label,
                reference_date,
                monthly_required,
                monthly_submitted,
                due_dates.get((monthly_period, 1)),
            ),
            "bimonthly": self._build_stat(
                VatType.BIMONTHLY,
                bimonthly_period,
                bimonthly_label,
                reference_date,
                bimonthly_required,
                bimonthly_submitted,
                due_dates.get((bimonthly_period, 2)),
            ),
            "advance_payments": self._build_advance_stats(reference_date),
        }

    def _build_advance_stats(self, reference_date: date) -> dict:
        monthly_period, monthly_label = monthly_vat_period(reference_date)
        bimonthly_period, bimonthly_label = bimonthly_advance_payment_period(reference_date)
        completion_by_period = self.advance_repo.completion_for_periods(
            [
                (monthly_period, 1),
                (bimonthly_period, 2),
            ]
        )
        return {
            "monthly": self._build_advance_stat(
                monthly_period,
                monthly_label,
                *completion_by_period.get((monthly_period, 1), (0, 0)),
            ),
            "bimonthly": self._build_advance_stat(
                bimonthly_period,
                bimonthly_label,
                *completion_by_period.get((bimonthly_period, 2), (0, 0)),
            ),
        }

    def _build_advance_stat(self, period: str, label: str, completed: int, total: int) -> dict:
        pending = max(total - completed, 0)
        percent = round((completed / total) * 100) if total else 0
        return {
            "period": period,
            "period_label": label,
            "status_label": "",
            "submitted": completed,
            "required": total,
            "pending": pending,
            "completion_percent": percent,
        }

    def _build_stat(
        self,
        vat_type: VatType,
        period: str,
        label: str,
        reference_date: date,
        required: int,
        submitted: int,
        due_date: date | None,
    ) -> dict:
        pending = max(required - submitted, 0)
        percent = round((submitted / required) * 100) if required else 0
        return {
            "period": period,
            "period_label": label,
            "status_label": self._status_label(required, pending, reference_date, due_date),
            "submitted": submitted,
            "required": required,
            "pending": pending,
            "completion_percent": percent,
        }

    def _status_label(
        self,
        required: int,
        pending: int,
        reference_date: date,
        due_date: date | None,
    ) -> str:
        if required == 0:
            return "אין דוחות נדרשים"
        if pending == 0:
            return "הושלמה"
        if due_date is None:
            return "ממתינה להגשה"
        if reference_date > due_date:
            return "מועד הגשה עבר"
        return "ממתינה להגשה"

    def _due_dates(self, periods: list[tuple[str, int, int, int]]) -> dict[tuple[str, int], date]:
        needed = [
            (period, months_count)
            for period, months_count, required, _submitted in periods
            if required > 0
        ]
        entries = self.materializer.get_periodic_entries(ObligationType.VAT, needed)
        due_dates: dict[tuple[str, int], date] = {}
        for period, months_count in needed:
            entry = entries.get((period, months_count))
            if entry is None:
                entry = self.materializer.ensure_periodic_entry(
                    ObligationType.VAT,
                    period,
                    months_count,
                )
            due_dates[(period, months_count)] = entry.due_date
        return due_dates
