"""VAT Compliance Report: per-client period coverage and stale pending flags."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.models.legal_entity import LegalEntity
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.reports.constants import VAT_STALE_PENDING_DAYS
from app.utils.time_utils import utcnow
from app.vat.repositories.vat_compliance_repository import (
    VatComplianceRepository,
)


class VatComplianceReportService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = VatComplianceRepository(db)
        self.client_repo = ClientRecordRepository(db)

    def get_vat_compliance_report(self, year: int, page: int = 1, page_size: int = 50) -> dict:
        rows, total = self.repo.get_compliance_aggregates_paginated(year, page=page, page_size=page_size)
        page_client_ids = list({r["client_record_id"] for r in rows})
        filed_items = self.repo.get_filed_items_for_clients(year, page_client_ids)
        client_name_map = self._client_name_map(page_client_ids)

        # ── On-time / late counts per business ───────────────────────────────
        on_time_map: dict[tuple[int, str], int] = {}
        late_map: dict[tuple[int, str], int] = {}
        for fi in filed_items:
            deadline = fi.due_date_effective
            filed_date = fi.filed_at.date() if hasattr(fi.filed_at, "date") else fi.filed_at
            is_late = filed_date > deadline
            bucket = late_map if is_late else on_time_map
            period_type = str(fi.period_type.value)
            key = (fi.client_record_id, period_type)
            bucket[key] = bucket.get(key, 0) + 1

        items = []
        for r in rows:
            client_record_id = r["client_record_id"]
            client_name = client_name_map.get(client_record_id)
            if client_name is None:
                continue
            period_type = str(r["period_type"].value)
            grouping_key = f"{client_record_id}:{year}:{period_type}"
            count_key = (client_record_id, period_type)
            expected = int(r["periods_expected"])
            filed = int(r["periods_filed"] or 0)
            on_time = on_time_map.get(count_key, 0)
            late = late_map.get(count_key, 0)
            items.append(
                {
                    "client_record_id": client_record_id,
                    "client_name": client_name,
                    "year": year,
                    "period_type": period_type,
                    "grouping_key": grouping_key,
                    "periods_expected": expected,
                    "periods_filed": filed,
                    "periods_open": expected - filed,
                    "on_time_count": on_time,
                    "late_count": late,
                    "compliance_rate": round(filed / expected * 100, 2) if expected else 0.0,
                }
            )

        # ── Stale PENDING_MATERIALS ───────────────────────────────────────────
        threshold = utcnow().replace(tzinfo=None)
        stale_pending = []
        stale_rows = self.repo.get_stale_pending(year)
        stale_name_map = self._client_name_map([r.client_record_id for r in stale_rows])
        for sr in stale_rows:
            client_name = stale_name_map.get(sr.client_record_id)
            if client_name is None:
                continue
            days_pending = (threshold - sr.updated_at).days
            if days_pending >= VAT_STALE_PENDING_DAYS:
                stale_pending.append(
                    {
                        "client_record_id": sr.client_record_id,
                        "client_name": client_name,
                        "period": sr.period,
                        "days_pending": days_pending,
                    }
                )

        return {
            "year": year,
            "total_clients": total,
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
            "stale_pending": stale_pending,
        }

    def _client_name_map(self, client_record_ids: list[int]) -> dict[int, str]:
        records = self.client_repo.list_by_ids(list(set(client_record_ids)))
        legal_entity_ids = list({record.legal_entity_id for record in records})
        entities = (
            self.db.scalars(select(LegalEntity).where(LegalEntity.id.in_(legal_entity_ids))).all()
            if legal_entity_ids
            else []
        )
        entity_map = {entity.id: entity.official_name for entity in entities}
        return {
            record.id: entity_map[record.legal_entity_id]
            for record in records
            if record.legal_entity_id in entity_map
        }
