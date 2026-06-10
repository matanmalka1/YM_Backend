from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.charge.repositories.charge_repository import ChargeRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.alerts.services.alert_service import DashboardAttentionService
from app.dashboard.services.recent_activity_service import RecentActivityService
from app.dashboard.services.tax_status_stats_service import TaxStatusStatsService
from app.users.models.user import UserRole
from app.utils.time_utils import israel_today


def _format_ils(amount: Decimal) -> str:
    try:
        normalized = amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        normalized = Decimal("0.00")
    formatted = f"{normalized:,.2f}".rstrip("0").rstrip(".")
    return f"₪{formatted}"


class DashboardOverviewService:
    """Dashboard overview — advisor gets full data, secretary gets operational subset."""

    def __init__(self, db: Session):
        self.db = db
        self.client_record_repo = ClientRecordRepository(db)
        self.charge_repo = ChargeRepository(db)
        self.attention_service = DashboardAttentionService(db)
        self.recent_activity_service = RecentActivityService(db)
        self.vat_stats_service = TaxStatusStatsService(db)

    def get_overview(
        self,
        reference_date: date | None = None,
        user_role: UserRole | None = None,
    ) -> dict:
        if reference_date is None:
            reference_date = israel_today()

        vat_stats = self.vat_stats_service.build(reference_date)

        is_advisor = user_role == UserRole.ADVISOR

        attention_items = (
            self.attention_service.build(user_role=user_role, reference_date=reference_date)
            if is_advisor
            else []
        )

        open_charges_count, open_charges_amount_ils = self._open_charges_stats(is_advisor)

        has_clients = self.client_record_repo.count() > 0
        return {
            "is_empty": not has_clients,
            "open_charges_count": open_charges_count,
            "open_charges_amount_ils": open_charges_amount_ils,
            "vat_stats": vat_stats,
            "attention": {
                "items": attention_items,
                "total": len(attention_items),
            },
            "recent_activity": self.recent_activity_service.build() if is_advisor else [],
        }

    def _open_charges_stats(self, is_advisor: bool) -> tuple[int, str | None]:
        if not is_advisor:
            return 0, None
        count, total = self.charge_repo.open_charges_stats()
        if count == 0:
            return 0, None
        amount_ils = _format_ils(total) if total is not None else None
        return count, amount_ils

