from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository


class AdvancePaymentReportService:
    def __init__(self, db: Session):
        self.repo = AdvancePaymentAggregationRepository(db)
        self.client_record_repo = ClientRecordRepository(db)
        self.legal_entity_repo = LegalEntityRepository(db)

    def get_collections_report(self, year: int, month: int | None) -> dict:
        rows = self.repo.get_collections_aggregates(year, month)
        client_record_ids = [row.client_record_id for row in rows]
        records = {
            record.id: record for record in self.client_record_repo.list_by_ids(client_record_ids)
        }
        legal_entity_ids = {record.legal_entity_id for record in records.values()}
        legal_entities = {
            entity.id: entity
            for entity in self.legal_entity_repo.list_by_ids(list(legal_entity_ids))
        }

        items = [
            {
                "client_record_id": r.client_record_id,
                "office_client_number": (
                    records[r.client_record_id].office_client_number
                    if r.client_record_id in records
                    else None
                ),
                "client_name": (
                    legal_entities[records[r.client_record_id].legal_entity_id].official_name
                    if r.client_record_id in records
                    and legal_entities.get(records[r.client_record_id].legal_entity_id)
                    else f"לקוח #{r.client_record_id}"
                ),
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
