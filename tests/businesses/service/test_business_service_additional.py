from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.audit.constants import ACTION_RESTORED, ENTITY_BUSINESS
from app.audit.models.entity_audit_log import EntityAuditLog
from app.businesses.models.business import Business, BusinessStatus
from app.businesses.services.business_service import BusinessService
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.users.models.user import UserRole
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_identity


def _create_business_row(
    test_db,
    *,
    status: BusinessStatus = BusinessStatus.ACTIVE,
    legal_entity_id: int | None = None,
) -> Business:
    if legal_entity_id is None:
        client = seed_client_identity(
            test_db,
            full_name=f"Additional Service Client {status.value}",
            id_number=f"BADD-{status.value}",
        )
        legal_entity_id = client.legal_entity_id
    business = Business(
        business_name="Additional Service Business",
        opened_at=date(2026, 1, 1),
        status=status,
        legal_entity_id=legal_entity_id,
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)
    return business


def test_create_business_defaults_opened_at_to_today_when_missing_everywhere(test_db):
    client = seed_client_identity(test_db, full_name="Today Client", id_number="BTODAY1")
    service = BusinessService(test_db)

    with patch("app.businesses.services.business_service.israel_today") as mock_today:
        mock_today.return_value = date(2026, 4, 9)
        result = service.create_business(
            client_id=client.id,
            business_name="Uses Today",
        )

    assert result.opened_at == date(2026, 4, 9)


def test_update_business_rejects_invalid_status_value(test_db):
    client = seed_client_identity(test_db, full_name="Additional Client", id_number="BADD001")
    business = _create_business_row(test_db, legal_entity_id=client.legal_entity_id)
    service = BusinessService(test_db)

    with pytest.raises(AppError) as exc:
        service.update_business(
            business_id=business.id,
            client_id=client.id,
            user_role=UserRole.ADVISOR,
            status="not-a-real-status",
        )

    assert exc.value.code == "BUSINESS.INVALID_STATUS"


def test_update_business_rejects_wrong_client_id(test_db):
    client = seed_client_identity(test_db, full_name="Additional Client", id_number="BADD002")
    business = _create_business_row(test_db, legal_entity_id=client.legal_entity_id)
    service = BusinessService(test_db)

    with pytest.raises(NotFoundError) as exc:
        service.update_business(
            business_id=business.id,
            client_id=1 + 999,
            user_role=UserRole.ADVISOR,
            status=BusinessStatus.ACTIVE.value,
        )

    assert exc.value.code == "BUSINESS.NOT_FOUND"


def test_update_business_to_active_clears_closed_at(test_db):
    client = seed_client_identity(test_db, full_name="Additional Client", id_number="BADD003")
    business = _create_business_row(
        test_db,
        status=BusinessStatus.CLOSED,
        legal_entity_id=client.legal_entity_id,
    )
    business.closed_at = date(2026, 2, 1)
    test_db.commit()

    result = BusinessService(test_db).update_business(
        business_id=business.id,
        client_id=client.id,
        user_role=UserRole.ADVISOR,
        status=BusinessStatus.ACTIVE.value,
    )

    assert result.status == BusinessStatus.ACTIVE
    assert result.closed_at is None


def test_delete_business_raises_when_missing(test_db):
    service = BusinessService(test_db)

    with pytest.raises(NotFoundError) as exc:
        service.delete_business(123, actor_id=1)

    assert exc.value.code == "BUSINESS.NOT_FOUND"


def test_restore_business_requires_advisor_role(test_db):
    service = BusinessService(test_db)

    with pytest.raises(ForbiddenError) as exc:
        service.restore_business(1, actor_id=5, actor_role=UserRole.SECRETARY)

    assert exc.value.code == "BUSINESS.FORBIDDEN"


def test_restore_business_not_deleted_raises_conflict(test_db):
    service = BusinessService(test_db)
    service._lifecycle.business_repo = SimpleNamespace(
        get_by_id_including_deleted=lambda _business_id: SimpleNamespace(deleted_at=None)
    )

    with pytest.raises(ConflictError) as exc:
        service.restore_business(1, actor_id=5, actor_role=UserRole.ADVISOR)

    assert exc.value.code == "BUSINESS.NOT_DELETED"


def test_restore_business_raises_when_repo_restore_returns_none(test_db):
    service = BusinessService(test_db)
    service._lifecycle.business_repo = SimpleNamespace(
        get_by_id_including_deleted=lambda _business_id: SimpleNamespace(
            deleted_at=date(2026, 1, 1),
        ),
        restore=lambda _business_id, restored_by: None,
    )

    with pytest.raises(NotFoundError) as exc:
        service.restore_business(2, actor_id=5, actor_role=UserRole.ADVISOR)

    assert exc.value.code == "BUSINESS.NOT_FOUND"


def test_restore_business_restores_soft_deleted_business_and_writes_audit(test_db):
    business = _create_business_row(test_db, status=BusinessStatus.CLOSED)
    business.deleted_at = utcnow()
    business.deleted_by = 4
    test_db.commit()

    restored = BusinessService(test_db).restore_business(
        business.id,
        actor_id=9,
        actor_role=UserRole.ADVISOR,
    )

    assert restored.id == business.id
    assert restored.deleted_at is None
    assert restored.status == BusinessStatus.ACTIVE
    assert restored.restored_by == 9

    audit = test_db.scalars(
        select(EntityAuditLog).filter(
            EntityAuditLog.entity_type == ENTITY_BUSINESS,
            EntityAuditLog.entity_id == business.id,
            EntityAuditLog.action == ACTION_RESTORED,
        )
    ).one()
    assert audit.performed_by == 9


def test_list_businesses_for_client_raises_when_client_missing(test_db):
    service = BusinessService(test_db)
    service.client_repo = SimpleNamespace(get_by_id=lambda _client_id: None)

    with pytest.raises(NotFoundError) as exc:
        service.list_businesses_for_client(777)

    assert exc.value.code == "CLIENT.NOT_FOUND"
