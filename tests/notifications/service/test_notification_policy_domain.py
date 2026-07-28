from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.common.enums import EntityType, IdNumberType, ObligationStatus, VatType
from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notifications.services.notification_policy_service import NotificationPolicyService
from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.utils.time_utils import utcnow
from app.vat.models.vat_work_item import VatWorkItem


def _client(client_factory, suffix: str, *, entity_type: EntityType = EntityType.OSEK_MURSHE):
    return client_factory(
        full_name=f"Policy Client {suffix}",
        id_number=f"NPC-{suffix}",
        id_number_type=IdNumberType.INDIVIDUAL,
        entity_type=entity_type,
        email=f"policy-{suffix}@example.com",
        vat_reporting_frequency=VatType.MONTHLY,
    )


def _vat_item(
    vat_work_item_factory,
    client_record_id: int,
    user_id: int,
    *,
    status: ObligationStatus = ObligationStatus.AWAITING_INPUT,
    due_date_effective: dt.date | None = None,
) -> VatWorkItem:
    return vat_work_item_factory(
        client_record_id=client_record_id,
        created_by=user_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        status=status,
        due_date_original=due_date_effective or dt.date.today(),
        due_date_effective=due_date_effective or dt.date.today(),
    )


def _charge(
    charge_factory,
    client_record_id: int,
    *,
    status: ChargeStatus,
) -> Charge:
    return charge_factory(
        client_record_id=client_record_id,
        charge_type=ChargeType.OTHER,
        status=status,
        amount=Decimal("120.00"),
        description="בדיקת חיוב",
        issued_at=utcnow() if status in (ChargeStatus.ISSUED, ChargeStatus.PAID) else None,
    )


def _signature(
    signature_request_factory,
    client_record_id: int,
    user_id: int,
    *,
    status: SignatureRequestStatus = SignatureRequestStatus.PENDING_SIGNATURE,
    expires_at: dt.datetime | None = None,
    signing_token: str | None = "token-123",
) -> SignatureRequest:
    return signature_request_factory(
        client_record_id=client_record_id,
        created_by=user_id,
        request_type=SignatureRequestType.CUSTOM,
        title="מסמך לחתימה",
        signer_name="חותם",
        signer_email="signer@example.com",
        status=status,
        signing_token=signing_token,
        expires_at=expires_at if expires_at is not None else utcnow() + dt.timedelta(days=7),
    )


def _policy(test_db, client, trigger, entity_id, **kwargs):
    from app.clients.models.client_record import ClientRecord

    record = test_db.get(ClientRecord, client.id)
    return NotificationPolicyService().can_send(
        record,
        trigger,
        db=test_db,
        entity_id=entity_id,
        **kwargs,
    )


def test_vat_osek_patur_blocked(test_db, test_user, client_factory, vat_work_item_factory):
    client = _client(client_factory, "vat-patur", entity_type=EntityType.OSEK_PATUR)
    item = _vat_item(vat_work_item_factory, client.id, test_user.id)

    result = _policy(test_db, client, NotificationTrigger.VAT_DOCUMENTS_REMINDER, item.id)

    assert result.blocked is True


def test_vat_already_filed_blocked(test_db, test_user, client_factory, vat_work_item_factory):
    client = _client(client_factory, "vat-filed")
    item = _vat_item(
        vat_work_item_factory,
        client.id,
        test_user.id,
        status=ObligationStatus.SUBMITTED,
    )

    result = _policy(test_db, client, NotificationTrigger.VAT_DOCUMENTS_REMINDER, item.id)

    assert result.blocked is True


def test_vat_deadline_passed_blocked(test_db, test_user, client_factory, vat_work_item_factory):
    client = _client(client_factory, "vat-past")
    item = _vat_item(
        vat_work_item_factory,
        client.id,
        test_user.id,
        due_date_effective=dt.date.today() - dt.timedelta(days=1),
    )

    result = _policy(test_db, client, NotificationTrigger.VAT_DOCUMENTS_REMINDER, item.id)

    assert result.blocked is True


def test_vat_too_far_out_blocked(test_db, test_user, client_factory, vat_work_item_factory):
    client = _client(client_factory, "vat-far")
    item = _vat_item(
        vat_work_item_factory,
        client.id,
        test_user.id,
        due_date_effective=dt.date.today() + dt.timedelta(days=20),
    )

    result = _policy(test_db, client, NotificationTrigger.VAT_DOCUMENTS_REMINDER, item.id)

    assert result.blocked is True


def test_vat_day_of_deadline_allowed(test_db, test_user, client_factory, vat_work_item_factory):
    client = _client(client_factory, "vat-today")
    item = _vat_item(
        vat_work_item_factory, client.id, test_user.id, due_date_effective=dt.date.today()
    )

    result = _policy(test_db, client, NotificationTrigger.VAT_DOCUMENTS_REMINDER, item.id)

    assert result.blocked is False


def test_vat_within_window_allowed(test_db, test_user, client_factory, vat_work_item_factory):
    client = _client(client_factory, "vat-window")
    item = _vat_item(
        vat_work_item_factory,
        client.id,
        test_user.id,
        due_date_effective=dt.date.today() + dt.timedelta(days=7),
    )

    result = _policy(test_db, client, NotificationTrigger.VAT_DOCUMENTS_REMINDER, item.id)

    assert result.blocked is False


def test_payment_reminder_draft_blocked(test_db, client_factory, charge_factory):
    client = _client(client_factory, "pay-draft")
    charge = _charge(charge_factory, client.id, status=ChargeStatus.DRAFT)

    result = _policy(test_db, client, NotificationTrigger.PAYMENT_REMINDER, charge.id)

    assert result.blocked is True


def test_payment_reminder_issued_allowed(test_db, client_factory, charge_factory):
    client = _client(client_factory, "pay-issued")
    charge = _charge(charge_factory, client.id, status=ChargeStatus.ISSUED)

    result = _policy(test_db, client, NotificationTrigger.PAYMENT_REMINDER, charge.id)

    assert result.blocked is False
    assert result.warnings == []


def test_payment_reminder_within_7_days_warning(
    test_db, client_factory, charge_factory, notification_factory
):
    client = _client(client_factory, "pay-warn")
    charge = _charge(charge_factory, client.id, status=ChargeStatus.ISSUED)
    notification = notification_factory(
        client_record_id=client.id,
        trigger=NotificationTrigger.PAYMENT_REMINDER,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="body",
        entity_type="charge",
        entity_id=charge.id,
        status=NotificationStatus.SENT,
    )
    notification.created_at = utcnow() - dt.timedelta(days=3)
    test_db.flush()

    result = _policy(test_db, client, NotificationTrigger.PAYMENT_REMINDER, charge.id)

    assert result.blocked is False
    assert len(result.warnings) > 0


def test_payment_reminder_confirm_overrides_warning(
    test_db, client_factory, charge_factory, notification_factory
):
    client = _client(client_factory, "pay-confirm")
    charge = _charge(charge_factory, client.id, status=ChargeStatus.ISSUED)
    notification = notification_factory(
        client_record_id=client.id,
        trigger=NotificationTrigger.PAYMENT_REMINDER,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="body",
        entity_type="charge",
        entity_id=charge.id,
        status=NotificationStatus.SENT,
    )
    notification.created_at = utcnow() - dt.timedelta(days=3)
    test_db.flush()

    result = _policy(
        test_db,
        client,
        NotificationTrigger.PAYMENT_REMINDER,
        charge.id,
        confirm_recent_duplicate=True,
    )

    assert result.blocked is False
    assert result.warnings == []


def test_signature_expired_blocked(test_db, test_user, client_factory, signature_request_factory):
    client = _client(client_factory, "sig-expired")
    sig = _signature(
        signature_request_factory,
        client.id,
        test_user.id,
        expires_at=utcnow() - dt.timedelta(days=1),
    )

    result = _policy(test_db, client, NotificationTrigger.SIGNATURE_REQUEST_SENT, sig.id)

    assert result.blocked is True


def test_signature_not_pending_blocked(
    test_db, test_user, client_factory, signature_request_factory
):
    client = _client(client_factory, "sig-signed")
    sig = _signature(
        signature_request_factory,
        client.id,
        test_user.id,
        status=SignatureRequestStatus.SIGNED,
        signing_token=None,
    )

    result = _policy(test_db, client, NotificationTrigger.SIGNATURE_REQUEST_SENT, sig.id)

    assert result.blocked is True


def test_signature_valid_allowed(test_db, test_user, client_factory, signature_request_factory):
    client = _client(client_factory, "sig-valid")
    sig = _signature(signature_request_factory, client.id, test_user.id)

    result = _policy(test_db, client, NotificationTrigger.SIGNATURE_REQUEST_SENT, sig.id)

    assert result.blocked is False


def test_invoice_issued_draft_blocked(test_db, client_factory, charge_factory):
    client = _client(client_factory, "invoice-draft")
    charge = _charge(charge_factory, client.id, status=ChargeStatus.DRAFT)

    result = _policy(test_db, client, NotificationTrigger.INVOICE_ISSUED, charge.id)

    assert result.blocked is True


def test_invoice_issued_allowed(test_db, client_factory, charge_factory):
    client = _client(client_factory, "invoice-issued")
    charge = _charge(charge_factory, client.id, status=ChargeStatus.ISSUED)

    result = _policy(test_db, client, NotificationTrigger.INVOICE_ISSUED, charge.id)

    assert result.blocked is False
