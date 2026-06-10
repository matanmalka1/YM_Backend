"""Tests for NotificationService.list_paginated and get_summary."""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.clients.models.client_record import ClientRecord
from app.clients.models.legal_entity import LegalEntity
from app.clients.models.person import Person
from app.clients.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)
from app.common.enums import IdNumberType
from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.services.notification_service import NotificationService


def _make_client(db, *, email: str = "owner@test.com") -> int:
    entity = LegalEntity(
        official_name="Test Entity",
        id_number=f"SVC-{id(db)}-{email}",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    db.add(entity)
    db.flush()
    record = ClientRecord(legal_entity_id=entity.id)
    db.add(record)
    db.flush()
    person = Person(
        full_name="Test Client",
        id_number=f"P-{record.id}",
        id_number_type=IdNumberType.OTHER,
        email=email,
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


def test_list_paginated_enriches_business_name(test_db):
    svc = NotificationService(test_db)
    n1 = SimpleNamespace(
        id=1,
        client_record_id=8,
        business_id=4,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="x",
        subject_snapshot=None,
        status=NotificationStatus.PENDING,
        sent_at=None,
        failed_at=None,
        error_message=None,
        retry_count=0,
        triggered_by=None,
        created_at=datetime.now(UTC),
    )
    svc.repo = SimpleNamespace(
        list_paginated=lambda **_: ([n1], 1),
    )
    svc.business_repo = SimpleNamespace(
        list_by_ids=lambda _: [SimpleNamespace(id=4, full_name="Biz 4", business_name=None)],
    )

    items, total = svc.list_paginated(page=2, page_size=10, business_id=4)
    assert total == 1
    assert items[0].business_name == "Biz 4"


def test_get_summary_returns_correct_counts(test_db):
    client_record_id = _make_client(test_db, email="sum@test.com")
    repo = NotificationRepository(test_db)

    n_sent = repo.create(
        client_record_id=client_record_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="sum@test.com",
        content_snapshot="sent",
    )
    repo.mark_sent(n_sent.id)

    n_failed = repo.create(
        client_record_id=client_record_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="sum@test.com",
        content_snapshot="failed",
    )
    repo.mark_failed(n_failed.id, "err")

    repo.create(
        client_record_id=client_record_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="sum@test.com",
        content_snapshot="pending",
    )

    svc = NotificationService(test_db)
    summary = svc.get_summary(client_record_id=client_record_id)
    assert summary.sent == 1
    assert summary.failed == 1
    assert summary.pending == 1
    assert summary.total == 3


def test_get_summary_returns_zeros_for_absent_statuses(test_db):
    client_record_id = _make_client(test_db, email="zero@test.com")
    repo = NotificationRepository(test_db)
    n = repo.create(
        client_record_id=client_record_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="zero@test.com",
        content_snapshot="sent-only",
    )
    repo.mark_sent(n.id)

    svc = NotificationService(test_db)
    summary = svc.get_summary(client_record_id=client_record_id)
    assert summary.pending == 0
    assert summary.failed == 0
    assert summary.sent == 1
    assert summary.total == 1
