"""Repository for VatAuditLog entities."""

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
    ) -> VatAuditLog:
        return self.build_and_add(
            work_item_id=work_item_id,
            performed_by=performed_by,
            action=action,
            old_value=old_value,
            new_value=new_value,
            note=note,
            invoice_id=invoice_id,
        )

    def count_audit_trail(self, work_item_id: int) -> int:
        return (
            self.db.scalar(
                select(func.count(VatAuditLog.id)).where(VatAuditLog.work_item_id == work_item_id)
            )
            or 0
        )

    def get_audit_trail(self, work_item_id: int, limit: int, offset: int) -> list[VatAuditLog]:
        return self.db.scalars(
            select(VatAuditLog)
            .where(VatAuditLog.work_item_id == work_item_id)
            .order_by(VatAuditLog.performed_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
