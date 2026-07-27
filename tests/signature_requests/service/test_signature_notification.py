from __future__ import annotations

import datetime as dt

import pytest

from app.core.exceptions import AppError
from app.notifications.models.notification import NotificationStatus
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.schemas.notification_schemas import (
    NotificationPreviewRequest,
    NotificationSendRequest,
)
from app.notifications.services.notification_send_service import NotificationSendService
from app.signature_requests.models.signature_request import SignatureRequestStatus
from app.utils.time_utils import utcnow


def _client(client_factory, suffix: str, *, email: str | None = "client@example.com"):
    return client_factory(
        full_name=f"Signature Notification {suffix}",
        id_number=f"SN-{suffix}",
        email=email,
    )


def _signature(
    signature_request_factory,
    client_record_id: int,
    user_id: int,
    *,
    signer_email: str | None = "signer@example.com",
    expires_at: dt.datetime | None = None,
    status: SignatureRequestStatus = SignatureRequestStatus.PENDING_SIGNATURE,
    signing_token: str | None = "sig-token",
):
    return signature_request_factory(
        client_record_id=client_record_id,
        created_by=user_id,
        title="אישור מסמך",
        signer_name="לקוח",
        signer_email=signer_email,
        status=status,
        signing_token=signing_token,
        expires_at=expires_at if expires_at is not None else utcnow() + dt.timedelta(days=7),
    )


def test_signature_request_sent_preview_blocked_no_entity_id(test_db, test_user):
    svc = NotificationSendService(test_db)
    request = NotificationPreviewRequest(
        client_record_id=1,
        trigger="signature_request_sent",  # type: ignore[arg-type]
        entity_id=None,
    )

    with pytest.raises(AppError) as exc:
        svc.preview(request, triggered_by=test_user.id)

    assert exc.value.code == "NOTIFICATION.MISSING_ENTITY_ID"


def test_signature_request_sent_preview_blocked_expired(
    test_db, test_user, client_factory, signature_request_factory
):
    client = _client(client_factory, "expired")
    sig = _signature(
        signature_request_factory,
        client.id,
        test_user.id,
        expires_at=utcnow() - dt.timedelta(days=1),
    )
    svc = NotificationSendService(test_db)

    result = svc.preview(
        NotificationPreviewRequest(
            client_record_id=client.id,
            trigger="signature_request_sent",  # type: ignore[arg-type]
            entity_id=sig.id,
        ),
        triggered_by=test_user.id,
    )

    assert result.status == "blocked"
    assert result.can_send is False


def test_signature_request_sent_send_saves_signature_request_id(
    test_db, test_user, client_factory, signature_request_factory
):
    client = _client(client_factory, "valid")
    sig = _signature(signature_request_factory, client.id, test_user.id)
    svc = NotificationSendService(test_db)

    result = svc.send(
        NotificationSendRequest(
            client_record_id=client.id,
            trigger="signature_request_sent",  # type: ignore[arg-type]
            overrides={"subject": "בקשה לחתימה", "body": "נא לחתום"},
            entity_id=sig.id,
        ),
        triggered_by=test_user.id,
        idempotency_key="00000000-0000-4000-8000-000000000301",
    )

    assert result.status in ("sent", "failed")
    assert result.notification_id is not None
    record = NotificationRepository(test_db).get_by_id(result.notification_id)
    assert record is not None
    assert record.signature_request_id == sig.id


def test_signature_request_sent_skipped_when_no_signer_email(
    test_db, test_user, client_factory, signature_request_factory
):
    # Client has an email — skip must be driven by missing signer_email, not client email.
    client = _client(client_factory, "no-signer-email", email="client@example.com")
    sig = _signature(signature_request_factory, client.id, test_user.id, signer_email=None)
    svc = NotificationSendService(test_db)

    result = svc.send(
        NotificationSendRequest(
            client_record_id=client.id,
            trigger="signature_request_sent",  # type: ignore[arg-type]
            overrides={"subject": "בקשה לחתימה", "body": "נא לחתום"},
            entity_id=sig.id,
        ),
        triggered_by=test_user.id,
        idempotency_key="00000000-0000-4000-8000-000000000302",
    )

    assert result.status == "skipped"
    assert result.notification_id is not None
    record = NotificationRepository(test_db).get_by_id(result.notification_id)
    assert record is not None
    assert record.status == NotificationStatus.SKIPPED
    assert record.recipient is None
    assert record.signature_request_id == sig.id


def test_signature_request_sent_uses_signer_email_not_client_email(
    test_db, test_user, client_factory, signature_request_factory
):
    # signer_email differs from client contact email — recipient must be signer_email.
    client = _client(client_factory, "signer-email", email="client@example.com")
    sig = _signature(
        signature_request_factory, client.id, test_user.id, signer_email="signer@different.com"
    )
    svc = NotificationSendService(test_db)

    result = svc.send(
        NotificationSendRequest(
            client_record_id=client.id,
            trigger="signature_request_sent",  # type: ignore[arg-type]
            overrides={"subject": "בקשה לחתימה", "body": "נא לחתום"},
            entity_id=sig.id,
        ),
        triggered_by=test_user.id,
        idempotency_key="00000000-0000-4000-8000-000000000303",
    )

    assert result.status in ("sent", "failed")
    record = NotificationRepository(test_db).get_by_id(result.notification_id)
    assert record is not None
    assert record.recipient == "signer@different.com"
