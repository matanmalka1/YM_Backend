"""Repository for VatAuditLog entities."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.vat.models.vat_audit_log import VatAuditLog


class VatAuditLogRepository(BaseRepository[VatAuditLog]):
    model = VatAuditLog

    def __init__(self, db: Session):
        super().__init__(db)

    def append(
        self,
        work_item_id: int,
        performed_by: int,
        action: str,
        old_value: str | None = None,
        new_value: str | None = None,
        note: str | None = None,
        invoice_id: int | None = None,
        performed_at: datetime | None = None,
    ) -> VatAuditLog:
        fields: dict[str, object] = {
            "work_item_id": work_item_id,
            "performed_by": performed_by,
            "action": action,
            "old_value": old_value,
            "new_value": new_value,
            "note": note,
            "invoice_id": invoice_id,
        }
        if performed_at is not None:
            fields["performed_at"] = performed_at
        return self.build_and_add(
            **fields,
        )

    def count_audit_trail(self, work_item_id: int) -> int:
        return (
            self.db.scalar(
                select(func.count(VatAuditLog.id)).where(VatAuditLog.work_item_id == work_item_id)
            )
            or 0
        )

    def get_audit_trail(
        self, work_item_id: int, page: int = 1, page_size: int = 20
    ) -> list[VatAuditLog]:
        stmt = self.apply_pagination(
            select(VatAuditLog)
            .where(VatAuditLog.work_item_id == work_item_id)
            .order_by(VatAuditLog.performed_at.desc()),
            page,
            page_size,
        )
        return self.db.scalars(stmt).all()
