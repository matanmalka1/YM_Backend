from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.clients.repositories.client_identity_repository import ClientIdentityRepository


class AdvancePaymentReportService:
    def __init__(self, db: Session):
        self.repo = AdvancePaymentAggregationRepository(db)
        self.client_identity_repo = ClientIdentityRepository(db)

    def get_collections_report(self, year: int, month: int | None) -> dict:
        rows = self.repo.get_collections_aggregates(year, month)
        client_record_ids = [row.client_record_id for row in rows]
        client_profiles = self.client_identity_repo.get_display_map(client_record_ids)

        items = [
            {
                "client_record_id": r.client_record_id,
                "office_client_number": client_profiles[r.client_record_id].office_client_number,
                "client_name": client_profiles[r.client_record_id].client_name,
                "client_id_number": client_profiles[r.client_record_id].id_number,
                "total_expected": Decimal(r.total_expected or 0),
                "total_paid": Decimal(r.total_paid or 0),
                "overdue_count": int(r.overdue_count),
                "gap": Decimal(r.total_expected or 0) - Decimal(r.total_paid or 0),
            }
            for r in rows
        ]

        total_expected = sum(i["total_expected"] for i in items)
        total_paid = sum(i["total_paid"] for i in items)
        collection_rate = (
            (total_paid / total_expected * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if total_expected
            else Decimal("0")
        )
        total_gap = total_expected - total_paid

        return {
            "year": year,
            "month": month,
            "total_expected": total_expected,
            "total_paid": total_paid,
            "collection_rate": collection_rate,
            "total_gap": total_gap,
            "items": items,
        }
