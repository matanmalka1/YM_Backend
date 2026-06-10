"""Write operations and audit delegation for VatWorkItem entities."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import SubmissionMethod
from app.common.repositories.base_repository import BaseRepository
from app.utils.time_utils import utcnow
from app.vat.models.vat_audit_log import VatAuditLog
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_audit_log_repository import VatAuditLogRepository
from app.vat.repositories.vat_work_item_query_repository import (
    VatWorkItemQueryRepository,
)


class VatWorkItemWriteRepository(BaseRepository[VatWorkItem]):
    model = VatWorkItem

    def __init__(self, db: Session):
        super().__init__(db)
        self._query = VatWorkItemQueryRepository(db)
        self._audit = VatAuditLogRepository(db)

    # ── Read delegation ───────────────────────────────────────────────────────

    def get_by_client_record_period(self, client_record_id: int, period: str) -> VatWorkItem | None:
        return self._query.get_by_client_record_period(client_record_id, period)

    def list_by_client_record(self, client_record_id: int, limit: int = 200) -> list[VatWorkItem]:
        return self._query.list_by_client_record(client_record_id, limit=limit)

    def list_by_client_record_paginated(
        self,
        client_record_id: int,
        page: int = 1,
        page_size: int = 200,
    ) -> list[VatWorkItem]:
        return self._query.list_by_client_record_paginated(
            client_record_id,
            page=page,
            page_size=page_size,
        )

    def count_by_client_record(self, client_record_id: int) -> int:
        return self._query.count_by_client_record(client_record_id)

    def list_by_business_activity(
        self, business_activity_id: int, limit: int = 200
    ) -> list[VatWorkItem]:
        return self._query.list_by_business_activity(business_activity_id, limit=limit)

    def list_by_status(self, status, **kwargs) -> list[VatWorkItem]:
        return self._query.list_by_status(status, **kwargs)

    def count_by_status(self, status, **kwargs) -> int:
        return self._query.count_by_status(status, **kwargs)

    def count_by_status_summary(self, **kwargs) -> dict[VatWorkItemStatus, int]:
        return self._query.count_by_status_summary(**kwargs)

    def list_all(self, **kwargs) -> list[VatWorkItem]:
        return self._query.list_all(**kwargs)

    def count_all(self, **kwargs) -> int:
        return self._query.count_all(**kwargs)

    def count_by_period_not_filed(self, period: str) -> int:
        return self._query.count_by_period_not_filed(period)

    def sum_net_vat_by_client_record_year(self, client_record_id: int, tax_year: int):
        return self._query.sum_net_vat_by_client_record_year(client_record_id, tax_year)

    def list_not_filed_for_period(self, period: str, limit: int = 3) -> list[VatWorkItem]:
        return self._query.list_not_filed_for_period(period, limit=limit)

    def list_open_up_to_period(self, up_to_period: str, limit: int = 50) -> list[VatWorkItem]:
        return self._query.list_open_up_to_period(up_to_period, limit=limit)

    def create(
        self,
        *,
        client_record_id: int,
        period: str,
        period_type=None,
        created_by: int,
        status: VatWorkItemStatus = VatWorkItemStatus.MATERIAL_RECEIVED,
        pending_materials_note: str | None = None,
        assigned_to: int | None = None,
        tax_calendar_entry_id: int,
        due_date_original: date,
        due_date_effective: date,
    ) -> VatWorkItem:
        if tax_calendar_entry_id is None or due_date_original is None or due_date_effective is None:
            raise TypeError(
                "tax_calendar_entry_id, due_date_original, and due_date_effective are required"
            )
        if client_record_id is None or period is None or period_type is None or created_by is None:
            raise TypeError("client_record_id, period, period_type, and created_by are required")
        return self.build_and_add(
            client_record_id=client_record_id,
            period=period,
            period_type=period_type,
            created_by=created_by,
            status=status,
            pending_materials_note=pending_materials_note,
            assigned_to=assigned_to,
            tax_calendar_entry_id=tax_calendar_entry_id,
            due_date_original=due_date_original,
            due_date_effective=due_date_effective,
        )

    def update_status(
        self,
        item_id: int,
        new_status: VatWorkItemStatus,
        item: VatWorkItem | None = None,
        **extra_fields,
    ) -> VatWorkItem | None:
        """Update status. Pass a pre-fetched (optionally locked) ``item`` to
        avoid a second SELECT and keep the lock from get_by_id_for_update() alive."""
        item = item or self.get_by_id(item_id)
        if not item:
            return None
        item.status = new_status
        item.updated_at = utcnow()
        for key, value in extra_fields.items():
            if hasattr(item, key):
                setattr(item, key, value)
        self.db.flush()
        return item

    def cancel_open_by_client_record(self, client_record_id: int) -> int:
        rows = self.db.scalars(
            select(VatWorkItem).where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.deleted_at.is_(None),
                VatWorkItem.status.notin_([VatWorkItemStatus.FILED]),
            )
        ).all()
        for row in rows:
            row.status = VatWorkItemStatus.CANCELED
            row.updated_at = utcnow()
        if rows:
            self.db.flush()
        return len(rows)

    def update_vat_totals(
        self,
        item_id: int,
        total_output_vat,
        total_input_vat,
        total_output_net,
        total_input_net,
    ) -> VatWorkItem | None:
        from decimal import Decimal

        item = self.get_by_id(item_id)
        if not item:
            return None
        item.total_output_vat = Decimal(str(total_output_vat))
        item.total_input_vat = Decimal(str(total_input_vat))
        item.net_vat = Decimal(str(total_output_vat)) - Decimal(str(total_input_vat))
        item.total_output_net = Decimal(str(total_output_net))
        item.total_input_net = Decimal(str(total_input_net))
        item.updated_at = utcnow()
        self.db.flush()
        return item

    def mark_filed(
        self,
        item_id: int,
        final_vat_amount: float,
        submission_method: SubmissionMethod,
        filed_by: int,
        is_overridden: bool = False,
        override_justification: str | None = None,
        submission_reference: str | None = None,
        is_amendment: bool = False,
        amends_item_id: int | None = None,
        item: VatWorkItem | None = None,
    ) -> VatWorkItem | None:
        """File the work item. Pass a pre-fetched (optionally locked) ``item`` to
        avoid a second SELECT and keep the lock from get_by_id_for_update() alive."""
        item = item or self.get_by_id(item_id)
        if not item:
            return None
        item.status = VatWorkItemStatus.FILED
        item.final_vat_amount = final_vat_amount
        item.submission_method = submission_method
        item.filed_at = utcnow()
        item.filed_by = filed_by
        item.is_overridden = is_overridden
        item.override_justification = override_justification
        item.submission_reference = submission_reference
        item.is_amendment = is_amendment
        item.amends_item_id = amends_item_id
        item.updated_at = utcnow()
        self.db.flush()
        return item

    def append_audit(self, **kwargs) -> VatAuditLog:
        return self._audit.append(**kwargs)

    def count_audit_trail(self, work_item_id: int) -> int:
        return self._audit.count_audit_trail(work_item_id)

    def get_audit_trail(self, work_item_id: int, limit: int, offset: int) -> list[VatAuditLog]:
        return self._audit.get_audit_trail(work_item_id, limit, offset)
