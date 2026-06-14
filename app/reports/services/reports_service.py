from datetime import date

from sqlalchemy.orm import Session

from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.utils.time_utils import israel_today


class AgingReportService:
    """Aging report and financial reporting service."""

    def __init__(self, db: Session):
        self.charge_repo = ChargeRepository(db)
        self.client_record_repo = ClientRecordRepository(db)
        self.legal_entity_repo = LegalEntityRepository(db)

    def generate_aging_report(
        self,
        as_of_date: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        if as_of_date is None:
            as_of_date = israel_today()

        rows, total = self.charge_repo.get_aging_buckets_paginated(
            as_of_date, page=page, page_size=page_size
        )
        totals = self.charge_repo.get_aging_totals(as_of_date)

        client_record_ids = [row["client_record_id"] for row in rows]
        record_map = {
            record.id: record for record in self.client_record_repo.list_by_ids(client_record_ids)
        }
        legal_entity_ids = {record.legal_entity_id for record in record_map.values()}
        legal_map = {
            entity.id: entity for entity in self.legal_entity_repo.list_by_ids(list(legal_entity_ids))
        }

        items = []
        for row in rows:
            record = record_map.get(row["client_record_id"])
            legal_entity = legal_map.get(record.legal_entity_id) if record else None
            if not record or not legal_entity:
                continue

            oldest_issued_at = row["oldest_issued_at"]
            oldest_date = oldest_issued_at.date() if oldest_issued_at else None
            oldest_days = (as_of_date - oldest_date).days if oldest_date else None

            items.append(
                {
                    "client_record_id": record.id,
                    "client_name": legal_entity.official_name,
                    "total_outstanding": round(float(row["total"]), 2),
                    "current": round(float(row["current"]), 2),
                    "days_30": round(float(row["days_30"]), 2),
                    "days_60": round(float(row["days_60"]), 2),
                    "days_90_plus": round(float(row["days_90_plus"]), 2),
                    "oldest_invoice_date": oldest_date,
                    "oldest_invoice_days": oldest_days,
                }
            )

        summary = {
            "total_clients": totals.total_clients,
            "total_current": round(float(totals.total_current), 2),
            "total_30_days": round(float(totals.total_30_days), 2),
            "total_60_days": round(float(totals.total_60_days), 2),
            "total_90_plus": round(float(totals.total_90_plus), 2),
        }

        return {
            "report_date": as_of_date,
            "total_outstanding": round(float(totals.grand_total), 2),
            "items": items,
            "summary": summary,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
