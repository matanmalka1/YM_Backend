"""Service layer for read-only entity audit trail queries."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.audit.constants import (
    ALLOWED_READ_ENTITY_TYPES,
    ENTITY_ANNUAL_REPORT,
    ENTITY_BUSINESS,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
    ENTITY_NOT_FOUND_ERROR,
    INVALID_ENTITY_TYPE_ERROR,
)
from app.audit.repositories.entity_audit_log_repository import EntityAuditLogRepository
from app.audit.schemas.entity_audit_log import (
    EntityAuditLogResponse,
    EntityAuditTrailResponse,
)
from app.businesses.repositories.business_repository import BusinessRepository
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import AppError
from app.users.repositories.user_repository import UserRepository


class AuditTrailService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_repo = EntityAuditLogRepository(db)
        self.user_repo = UserRepository(db)
        self.client_repo = ClientRecordRepository(db)

    def _validate_entity_type(self, entity_type: str) -> None:
        if entity_type not in ALLOWED_READ_ENTITY_TYPES:
            raise AppError(INVALID_ENTITY_TYPE_ERROR, "AUDIT.INVALID_ENTITY_TYPE")

    def _entity_exists(self, entity_type: str, entity_id: int) -> bool:
        if entity_type == ENTITY_CLIENT:
            return self.client_repo.get_by_id(entity_id) is not None
        if entity_type == ENTITY_BUSINESS:
            return BusinessRepository(self.db).get_by_id(entity_id) is not None
        if entity_type == ENTITY_CHARGE:
            return ChargeRepository(self.db).get_by_id(entity_id) is not None
        if entity_type == ENTITY_ANNUAL_REPORT:
            return AnnualReportRepository(self.db).get_by_id(entity_id) is not None
        return False

    def _assert_entity_readable(self, entity_type: str, entity_id: int) -> None:
        self._validate_entity_type(entity_type)
        if not self._entity_exists(entity_type, entity_id):
            raise AppError(ENTITY_NOT_FOUND_ERROR, "AUDIT.ENTITY_NOT_FOUND", status_code=404)

    def get_entity_audit_trail(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = 20,
        *,
        action: str | None = None,
        user_id: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> EntityAuditTrailResponse:
        self._assert_entity_readable(entity_type, entity_id)
        offset = (page - 1) * page_size
        filters = {
            "action": action,
            "user_id": user_id,
            "created_after": created_after,
            "created_before": created_before,
        }
        entries = self.audit_repo.get_audit_trail(
            entity_type, entity_id, page_size, offset, **filters
        )
        total = self.audit_repo.count_audit_trail(entity_type, entity_id, **filters)
        user_ids = list({entry.performed_by for entry in entries})
        users = self.user_repo.list_by_ids(user_ids) if user_ids else []
        user_map = {user.id: user.full_name for user in users}

        items = []
        for entry in entries:
            row = EntityAuditLogResponse.model_validate(entry)
            row.performed_by_name = user_map.get(entry.performed_by)
            items.append(row)
        return EntityAuditTrailResponse(items=items, total=total, page=page, page_size=page_size)
