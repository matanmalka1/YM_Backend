from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.constants import ENTITY_BUSINESS
from app.audit.services.entity_audit_writer import EntityAuditWriter
from app.businesses.models.business import Business, BusinessStatus
from app.businesses.repositories.business_repository import BusinessRepository
from app.businesses.services.business_guards import (
    assert_business_belongs_to_legal_entity,
)
from app.businesses.services.business_lifecycle_service import BusinessLifecycleService
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.services.client_service import get_client_or_raise
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.users.models.user import UserRole
from app.utils.time_utils import israel_today


def _serialize(d: dict) -> dict:
    return {
        k: v.value if hasattr(v, "value") else str(v) if v is not None else None
        for k, v in d.items()
    }


class BusinessService:
    """Business management — CRUD and lifecycle logic."""

    def __init__(self, db: Session):
        self.db = db
        self.client_repo = ClientRecordRepository(db)
        self.business_repo = BusinessRepository(db)
        self._lifecycle = BusinessLifecycleService(db)
        self._audit = EntityAuditWriter(db)

    def create_business(
        self,
        client_id: int,
        opened_at: date | None = None,
        business_name: str | None = None,
        notes: str | None = None,
        actor_id: int | None = None,
    ) -> Business:
        return self.create_business_for_client_record(
            client_record_id=client_id,
            opened_at=opened_at,
            business_name=business_name,
            notes=notes,
            actor_id=actor_id,
        )

    def create_business_for_client_record(
        self,
        client_record_id: int,
        opened_at: date | None = None,
        business_name: str | None = None,
        notes: str | None = None,
        actor_id: int | None = None,
    ) -> Business:
        record = get_client_or_raise(self.db, client_record_id)

        effective_opened_at = opened_at or israel_today()

        if self.business_repo.all_non_deleted_are_closed_for_legal_entity(record.legal_entity_id):
            raise AppError(
                "כל העסקים של לקוח זה סגורים — לא ניתן להוסיף עסק חדש ללא אישור מפורש",
                "BUSINESS.CLIENT_ALL_CLOSED",
                status_code=409,
            )

        if business_name:
            for b in self.business_repo.list_by_legal_entity(
                record.legal_entity_id, page=1, page_size=10_000
            ):
                if (
                    b.business_name
                    and b.business_name.strip().lower() == business_name.strip().lower()
                ):
                    raise ConflictError(
                        f"עסק בשם '{business_name}' כבר קיים ללקוח זה",
                        "BUSINESS.NAME_CONFLICT",
                    )

        try:
            business = self.business_repo.create(
                legal_entity_id=record.legal_entity_id,
                opened_at=effective_opened_at,
                business_name=business_name,
                notes=notes,
                created_by=actor_id,
            )
        except IntegrityError as exc:
            raise ConflictError(
                f"שגיאת כפילות ביצירת עסק ללקוח {client_record_id}",
                "BUSINESS.CONFLICT",
            ) from exc

        self._audit.record_create(
            ENTITY_BUSINESS,
            business.id,
            actor_id,
            new_value={
                "client_record_id": client_record_id,
                "business_name": business_name,
                "opened_at": effective_opened_at,
            },
        )
        return business

    def get_business(self, business_id: int) -> Business | None:
        return self.business_repo.get_by_id(business_id)

    def get_business_or_raise(self, business_id: int) -> Business:
        business = self.business_repo.get_by_id(business_id)
        if not business:
            raise NotFoundError(f"עסק {business_id} לא נמצא", "BUSINESS.NOT_FOUND")
        return business

    def list_businesses_for_client(
        self, client_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[Business], int]:
        record = get_client_or_raise(self.db, client_id)
        items = self.business_repo.list_by_legal_entity(
            record.legal_entity_id,
            page=page,
            page_size=page_size,
        )
        total = self.business_repo.count_by_legal_entity(record.legal_entity_id)
        return items, total

    def update_business(
        self,
        business_id: int,
        client_id: int,
        user_role: UserRole,
        actor_id: int | None = None,
        **fields,
    ) -> Business:
        record = get_client_or_raise(self.db, client_id)

        business = self.business_repo.get_by_id(business_id)
        if not business:
            raise NotFoundError(f"עסק {business_id} לא נמצא", "BUSINESS.NOT_FOUND")
        if business.legal_entity_id is not None:
            assert_business_belongs_to_legal_entity(business, record.legal_entity_id)

        if "status" in fields and fields["status"] is not None:
            try:
                fields["status"] = BusinessStatus(fields["status"])
            except ValueError as exc:
                raise AppError(
                    f"סטטוס לא חוקי: {fields['status']}",
                    "BUSINESS.INVALID_STATUS",
                    status_code=400,
                ) from exc

        new_status = fields.get("status")
        if new_status in (BusinessStatus.FROZEN, BusinessStatus.CLOSED):
            if user_role != UserRole.ADVISOR:
                raise ForbiddenError("רק יועצים יכולים להקפיא או לסגור עסקים", "BUSINESS.FORBIDDEN")
        if new_status == BusinessStatus.CLOSED:
            fields.setdefault("closed_at", israel_today())
        if new_status == BusinessStatus.ACTIVE:
            fields["closed_at"] = None

        fields.pop("entity_type", None)

        old_snapshot = {k: getattr(business, k, None) for k in fields if hasattr(business, k)}
        updated = self.business_repo.update(business_id, **fields)
        new_snapshot = {k: getattr(updated, k, None) for k in fields if hasattr(updated, k)}

        self._audit.record_update(
            ENTITY_BUSINESS,
            business_id,
            actor_id,
            old_value=_serialize(old_snapshot),
            new_value=_serialize(new_snapshot),
        )
        return updated

    def delete_business(self, business_id: int, actor_id: int) -> None:
        self._lifecycle.delete_business(business_id, actor_id)

    def restore_business(self, business_id: int, actor_id: int, actor_role: UserRole) -> Business:
        return self._lifecycle.restore_business(business_id, actor_id, actor_role)
