"""Business delete and restore operations."""

from sqlalchemy.orm import Session

from app.audit.audit_constants import ENTITY_BUSINESS
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.businesses.models.business import Business
from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.users.models.user import UserRole


class BusinessLifecycleService:
    def __init__(self, db: Session):
        self.db = db
        self.business_repo = BusinessRepository(db)
        self.client_repo = ClientRecordRepository(db)
        self._audit = EntityAuditWriter(db)

    def _client_context(self, business: Business) -> dict:
        meta: dict = {"business_id": business.id}
        client = self.client_repo.get_by_legal_entity_id(business.legal_entity_id)
        if client is not None:
            meta["client_record_id"] = client.id
        return meta

    def delete_business(
        self, business_id: int, actor_id: int, actor_name: str | None = None
    ) -> None:
        business = self.business_repo.get_by_id(business_id)
        if not business:
            raise NotFoundError(f"עסק {business_id} לא נמצא", ErrorCode.BUSINESS_NOT_FOUND)
        metadata = self._client_context(business)
        self.business_repo.soft_delete(business_id, deleted_by=actor_id)
        self._audit.record_delete(
            ENTITY_BUSINESS,
            business_id,
            actor_id,
            actor_display_name=actor_name,
            metadata_json=metadata,
        )

    def restore_business(
        self, business_id: int, actor_id: int, actor_role: UserRole, actor_name: str | None = None
    ) -> Business:
        if actor_role != UserRole.ADVISOR:
            raise ForbiddenError("רק יועצים יכולים לשחזר עסקים", ErrorCode.BUSINESS_FORBIDDEN)
        business = self.business_repo.get_by_id_including_deleted(business_id)
        if not business:
            raise NotFoundError(f"עסק {business_id} לא נמצא", ErrorCode.BUSINESS_NOT_FOUND)
        if business.deleted_at is None:
            raise ConflictError("עסק זה אינו מחוק", ErrorCode.BUSINESS_NOT_DELETED)
        restored = self.business_repo.restore(business_id, restored_by=actor_id)
        if not restored:
            raise NotFoundError(f"עסק {business_id} לא נמצא", ErrorCode.BUSINESS_NOT_FOUND)
        self._audit.record_restore(
            ENTITY_BUSINESS,
            business_id,
            actor_id,
            actor_display_name=actor_name,
            metadata_json=self._client_context(restored),
        )
        return restored
