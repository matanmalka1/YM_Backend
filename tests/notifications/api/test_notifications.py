from datetime import date

from sqlalchemy import select

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)
from app.common.enums import IdNumberType
from app.notifications.models.notification import (
    NotificationChannel,
    NotificationTrigger,
)
from app.notifications.repositories.notification_repository import NotificationRepository


def _business(test_db, suffix: str) -> Business:
    le = LegalEntity(
        id_number=f"7300000{suffix}",
        id_number_type=IdNumberType.INDIVIDUAL,
        official_name=f"Notification API Client {suffix}",
    )
    test_db.add(le)
    test_db.flush()

    cr = ClientRecord(legal_entity_id=le.id)
    test_db.add(cr)
    test_db.flush()

    person = Person(
        full_name=f"Notification API Client {suffix}",
        id_number=f"7300000{suffix}",
        id_number_type=IdNumberType.INDIVIDUAL,
        email=f"n{suffix}@example.com",
        phone=f"0500000{suffix}",
    )
    test_db.add(person)
    test_db.flush()

    link = PersonLegalEntityLink(
        person_id=person.id,
        legal_entity_id=le.id,
        role=PersonLegalEntityRole.OWNER,
    )
    test_db.add(link)
    test_db.flush()

    b = Business(
        legal_entity_id=le.id,
        business_name=f"Notification API Biz {suffix}",
        opened_at=date.today(),
    )
    test_db.add(b)
    test_db.commit()
    test_db.refresh(b)
    return b


def _seed_notification(test_db, business_id: int, content: str, **kwargs):
    business = test_db.get(Business, business_id)
    cr = test_db.scalars(
        select(ClientRecord).filter(ClientRecord.legal_entity_id == business.legal_entity_id)
    ).first()
    repo = NotificationRepository(test_db)
    return repo.create(
        client_record_id=cr.id,
        business_id=business_id,
        trigger=kwargs.get("trigger", NotificationTrigger.CLIENT_GENERAL_MESSAGE),
        channel=kwargs.get("channel", NotificationChannel.EMAIL),
        recipient="x@example.com",
        content_snapshot=content,
    )


def test_notifications_list(client, test_db, advisor_headers):
    b1 = _business(test_db, "1")
    b2 = _business(test_db, "2")

    n1 = _seed_notification(test_db, b1.id, "one")
    n2 = _seed_notification(test_db, b1.id, "two")
    _seed_notification(test_db, b2.id, "other")

    resp = client.get(
        f"/api/v1/notifications?business_id={b1.id}&page=1&page_size=25",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert {item["id"] for item in data["items"]} == {n1.id, n2.id}


def test_notifications_list_by_status(client, test_db, advisor_headers):
    b1 = _business(test_db, "s1")
    n_pending = _seed_notification(test_db, b1.id, "pending-one")
    n_sent = _seed_notification(test_db, b1.id, "sent-one")
    repo = NotificationRepository(test_db)
    repo.mark_sent(n_sent.id)
    test_db.commit()

    resp = client.get(
        f"/api/v1/notifications?business_id={b1.id}&status=pending",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == n_pending.id


def test_notifications_list_by_trigger(client, test_db, advisor_headers):
    b1 = _business(test_db, "t1")
    n_msg = _seed_notification(
        test_db, b1.id, "msg", trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE
    )
    _seed_notification(
        test_db, b1.id, "binder", trigger=NotificationTrigger.BINDER_MISSING_DOCUMENTS
    )

    resp = client.get(
        f"/api/v1/notifications?business_id={b1.id}&trigger=client_general_message",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == n_msg.id


def test_notifications_list_by_channel(client, test_db, advisor_headers):
    b1 = _business(test_db, "c1")
    n_email = _seed_notification(test_db, b1.id, "email-notif", channel=NotificationChannel.EMAIL)
    _seed_notification(test_db, b1.id, "wa-notif", channel=NotificationChannel.WHATSAPP)

    resp = client.get(
        f"/api/v1/notifications?business_id={b1.id}&channel=email",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == n_email.id


def test_notifications_summary(client, test_db, advisor_headers):
    b1 = _business(test_db, "sum1")
    repo = NotificationRepository(test_db)

    n_sent = _seed_notification(test_db, b1.id, "sent")
    repo.mark_sent(n_sent.id)
    n_failed = _seed_notification(test_db, b1.id, "failed")
    repo.mark_failed(n_failed.id, "err")
    _seed_notification(test_db, b1.id, "still-pending")
    test_db.commit()

    resp = client.get(
        f"/api/v1/notifications/summary?business_id={b1.id}",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] == 1
    assert data["failed"] == 1
    assert data["pending"] == 1
    assert data["total"] == 3


def test_notifications_summary_zero_for_absent_statuses(client, test_db, advisor_headers):
    b1 = _business(test_db, "sum2")
    repo = NotificationRepository(test_db)
    n = _seed_notification(test_db, b1.id, "sent-only")
    repo.mark_sent(n.id)
    test_db.commit()

    resp = client.get(
        f"/api/v1/notifications/summary?business_id={b1.id}",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending"] == 0
    assert data["failed"] == 0
    assert data["sent"] == 1
    assert data["total"] == 1


def test_secretary_can_list(client, test_db, secretary_headers):
    b1 = _business(test_db, "sec1")
    _seed_notification(test_db, b1.id, "sec-notif")

    resp = client.get(
        f"/api/v1/notifications?business_id={b1.id}",
        headers=secretary_headers,
    )
    assert resp.status_code == 200


def test_secretary_can_send(client, test_db, secretary_headers):
    """Secretary is allowed to use POST /send (both roles have access)."""
    b1 = _business(test_db, "sec2")
    cr = test_db.scalars(
        select(ClientRecord).filter(ClientRecord.legal_entity_id == b1.legal_entity_id)
    ).first()
    resp = client.post(
        "/api/v1/notifications/send",
        json={
            "client_record_id": cr.id,
            "trigger": "client_general_message",
            "overrides": {
                "subject": "נושא",
                "body": "גוף ההודעה",
            },
        },
        headers={
            **secretary_headers,
            "X-Idempotency-Key": "00000000-0000-4000-8000-000000000401",
        },
    )
    # 200 or skipped/sent — just not 403/422
    assert resp.status_code in (200, 201)
    assert resp.json()["status"] in ("sent", "skipped", "failed")


def test_send_requires_idempotency_header(client, test_db, advisor_headers):
    b1 = _business(test_db, "idem-required")
    cr = test_db.scalars(
        select(ClientRecord).filter(ClientRecord.legal_entity_id == b1.legal_entity_id)
    ).first()
    resp = client.post(
        "/api/v1/notifications/send",
        json={
            "client_record_id": cr.id,
            "trigger": "client_general_message",
            "overrides": {
                "subject": "נושא",
                "body": "גוף ההודעה",
            },
        },
        headers=advisor_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NOTIFICATION.MISSING_IDEMPOTENCY_KEY"


def test_send_rejects_legacy_subject_body_shape(client, test_db, advisor_headers):
    b1 = _business(test_db, "legacy-shape")
    cr = test_db.scalars(
        select(ClientRecord).filter(ClientRecord.legal_entity_id == b1.legal_entity_id)
    ).first()
    resp = client.post(
        "/api/v1/notifications/send",
        json={
            "client_record_id": cr.id,
            "trigger": "client_general_message",
            "subject": "נושא",
            "body": "גוף ההודעה",
        },
        headers={
            **advisor_headers,
            "X-Idempotency-Key": "00000000-0000-4000-8000-000000000402",
        },
    )

    assert resp.status_code == 422


def test_preview_returns_ready_for_active_client(client, test_db, advisor_headers):
    b1 = _business(test_db, "prev1")
    cr = test_db.scalars(
        select(ClientRecord).filter(ClientRecord.legal_entity_id == b1.legal_entity_id)
    ).first()

    resp = client.post(
        "/api/v1/notifications/preview",
        json={
            "client_record_id": cr.id,
            "trigger": "client_general_message",
        },
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_send"] is True
    assert data["status"] == "ready"
    assert data["subject"] is not None
    assert data["body"] is not None
