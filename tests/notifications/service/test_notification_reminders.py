"""Tests for NotificationSendService — skipped, policy, and preview behavior."""


import pytest
from sqlalchemy.orm import Session

from app.clients.enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)
from app.notifications.models.notification import NotificationStatus, NotificationTrigger
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.schemas.notification_schemas import (
    NotificationPreviewRequest,
    NotificationSendRequest,
)
from app.notifications.services.notification_send_service import NotificationSendService


def _make_client(
    db: Session,
    *,
    email: str = "client@test.com",
    phone: str | None = None,
    status: ClientStatus = ClientStatus.ACTIVE,
) -> int:
    entity = LegalEntity(
        official_name="Test Entity",
        id_number=f"SND-{id(db)}-{email}",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    db.add(entity)
    db.flush()
    record = ClientRecord(legal_entity_id=entity.id, status=status)
    db.add(record)
    db.flush()
    person = Person(
        full_name="Test Client",
        id_number=f"P-{record.id}",
        id_number_type=IdNumberType.OTHER,
        email=email,
        phone=phone,
    )
    db.add(person)
    db.flush()
    db.add(
        PersonLegalEntityLink(
            person_id=person.id,
            legal_entity_id=entity.id,
            role=PersonLegalEntityRole.OWNER,
        )
    )
    db.flush()
    return record.id


def _make_client_no_email(db: Session) -> int:
    entity = LegalEntity(
        official_name="No Email Entity",
        id_number=f"NOE-{id(db)}",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    db.add(entity)
    db.flush()
    record = ClientRecord(legal_entity_id=entity.id)
    db.add(record)
    db.flush()
    person = Person(
        full_name="No Email Client",
        id_number=f"NE-{record.id}",
        id_number_type=IdNumberType.OTHER,
        email=None,
    )
    db.add(person)
    db.flush()
    db.add(
        PersonLegalEntityLink(
            person_id=person.id,
            legal_entity_id=entity.id,
            role=PersonLegalEntityRole.OWNER,
        )
    )
    db.flush()
    return record.id


def test_send_creates_skipped_record_when_no_email(test_db):
    cr_id = _make_client_no_email(test_db)
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "נושא", "body": "גוף"},
    )
    result = svc.send(
        req,
        triggered_by=1,
        idempotency_key="00000000-0000-4000-8000-000000000201",
    )

    assert result.status == "skipped"
    assert result.notification_id is not None

    items, total = NotificationRepository(test_db).list_paginated(client_record_id=cr_id)
    assert total == 1
    assert items[0].status == NotificationStatus.SKIPPED
    assert items[0].recipient is None


def test_send_blocked_for_frozen_client_no_record(test_db):
    cr_id = _make_client(test_db, email="frozen@test.com", status=ClientStatus.FROZEN)
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "נושא", "body": "גוף"},
    )
    result = svc.send(
        req,
        triggered_by=1,
        idempotency_key="00000000-0000-4000-8000-000000000202",
    )

    assert result.status == "blocked"
    assert result.notification_id is None

    _, total = NotificationRepository(test_db).list_paginated(client_record_id=cr_id)
    assert total == 0


def test_send_allowed_for_frozen_client_with_exempt_trigger(test_db):
    cr_id = _make_client(test_db, email="frozen-exempt@test.com", status=ClientStatus.FROZEN)
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_MISSING_INFORMATION,
        overrides={"subject": "נושא", "body": "גוף"},
    )
    result = svc.send(
        req,
        triggered_by=1,
        idempotency_key="00000000-0000-4000-8000-000000000203",
    )

    # Should proceed (skipped due to stub delivery, not blocked)
    assert result.status in ("sent", "skipped", "failed")
    assert result.status != "blocked"


def test_send_validates_empty_subject(test_db):
    cr_id = _make_client(test_db, email="val@test.com")
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "   ", "body": "גוף"},
    )
    from app.core.exceptions import AppError

    with pytest.raises(AppError) as exc:
        svc.send(
            req,
            triggered_by=1,
            idempotency_key="00000000-0000-4000-8000-000000000204",
        )
    assert "נושא" in exc.value.message


def test_send_validates_visible_placeholder(test_db):
    cr_id = _make_client(test_db, email="ph@test.com")
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "שלום", "body": "הי {client_name} צריך לבדוק"},
    )
    from app.core.exceptions import AppError

    with pytest.raises(AppError) as exc:
        svc.send(
            req,
            triggered_by=1,
            idempotency_key="00000000-0000-4000-8000-000000000205",
        )
    assert "שדות" in exc.value.message


def test_preview_returns_ready_for_active_client(test_db):
    cr_id = _make_client(test_db, email="preview@test.com")
    svc = NotificationSendService(test_db)

    req = NotificationPreviewRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
    )
    result = svc.preview(req, triggered_by=1)

    assert result.can_send is True
    assert result.status == "ready"
    assert result.subject is not None
    assert result.body is not None
    assert result.recipient == "preview@test.com"


def test_preview_returns_blocked_for_frozen_client(test_db):
    cr_id = _make_client(test_db, email="frz-prev@test.com", status=ClientStatus.FROZEN)
    svc = NotificationSendService(test_db)

    req = NotificationPreviewRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
    )
    result = svc.preview(req, triggered_by=1)

    assert result.can_send is False
    assert result.status == "blocked"


def test_idempotency_returns_cached_result(test_db):
    cr_id = _make_client(test_db, email="idem@test.com")
    svc = NotificationSendService(test_db)
    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "נושא", "body": "גוף"},
    )

    first = svc.send(
        req,
        triggered_by=1,
        idempotency_key="00000000-0000-4000-8000-000000000206",
    )
    second = svc.send(
        req,
        triggered_by=1,
        idempotency_key="00000000-0000-4000-8000-000000000206",
    )

    assert first.notification_id == second.notification_id
