from datetime import date
from decimal import Decimal
from itertools import count

import pytest

from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import AdvancePaymentFrequency
from app.core.exceptions import ConflictError, NotFoundError

_seq = count(1)


def _client_record(
    test_db, client_factory, *, status: ClientStatus = ClientStatus.ACTIVE
) -> ClientRecord:
    idx = next(_seq)
    seeded = client_factory(
        full_name=f"AP Create Client {idx}",
        id_number=f"991199{idx:03d}",
        status=status,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    record = test_db.get(ClientRecord, seeded.id)
    assert record is not None
    return record


def test_create_payment_success_sets_defaults(test_db, client_factory):
    client_record = _client_record(test_db, client_factory)
    service = AdvancePaymentService(test_db)

    payment = service.create_payment_for_client(
        client_record_id=client_record.id,
        period="2026-02",
        period_months_count=1,
        expected_amount=Decimal("250.50"),
        paid_amount=Decimal("100.00"),
        notes="first advance",
    )

    assert payment.id is not None
    assert payment.client_record_id == client_record.id
    # Status is derived, never defaulted: 100 paid against 250.50 expected is partial.
    assert payment.status.value == "partial"
    assert payment.expected_amount == Decimal("250.50")
    assert payment.paid_amount == Decimal("100.00")
    assert payment.due_date == date(2026, 3, 26)
    assert payment.due_date_original == date(2026, 3, 26)
    assert payment.due_date_effective == date(2026, 3, 26)
    assert payment.due_date_override_reason is None
    assert payment.notes == "first advance"


def test_due_date_original_cannot_change_after_first_set(test_db, client_factory):
    client_record = _client_record(test_db, client_factory)
    service = AdvancePaymentService(test_db)
    payment = service.create_payment_for_client(
        client_record_id=client_record.id,
        period="2026-01",
        period_months_count=1,
    )
    test_db.commit()

    payment.due_date_original = date(2026, 2, 20)
    with pytest.raises(ValueError):
        test_db.commit()
    test_db.rollback()


def test_due_date_effective_can_change_with_override_reason(test_db, client_factory):
    client_record = _client_record(test_db, client_factory)
    service = AdvancePaymentService(test_db)
    payment = service.create_payment_for_client(
        client_record_id=client_record.id,
        period="2026-01",
        period_months_count=1,
    )
    test_db.commit()

    payment.due_date_effective = date(2026, 2, 20)
    payment.due_date_override_reason = "אישור דחייה"
    test_db.commit()

    assert payment.due_date_original == date(2026, 2, 16)
    assert payment.due_date_effective == date(2026, 2, 20)


def test_due_date_effective_requires_reason_when_changed(test_db, client_factory):
    client_record = _client_record(test_db, client_factory)
    service = AdvancePaymentService(test_db)
    payment = service.create_payment_for_client(
        client_record_id=client_record.id,
        period="2026-01",
        period_months_count=1,
    )
    test_db.commit()

    payment.due_date_effective = date(2026, 2, 20)
    with pytest.raises(ValueError):
        test_db.commit()
    test_db.rollback()


def test_due_date_effective_equal_original_does_not_require_reason(test_db, client_factory):
    client_record = _client_record(test_db, client_factory)
    service = AdvancePaymentService(test_db)
    payment = service.create_payment_for_client(
        client_record_id=client_record.id,
        period="2026-01",
        period_months_count=1,
    )
    test_db.commit()

    payment.due_date_effective = payment.due_date_original
    payment.notes = "touch row"
    test_db.commit()

    assert payment.due_date_effective == payment.due_date_original


def test_create_payment_missing_business_raises(test_db):
    service = AdvancePaymentService(test_db)
    with pytest.raises(NotFoundError):
        service.create_payment_for_client(
            client_record_id=999,
            period="2026-01",
            period_months_count=1,
        )


@pytest.mark.parametrize("status", [ClientStatus.CLOSED, ClientStatus.FROZEN])
def test_create_payment_ineligible_client_raises_shared_guard_code(test_db, client_factory, status):
    """One code and status across domains; only the message says which state it was.

    This domain used to raise 403 CLIENT.CLOSED / CLIENT.FROZEN of its own. The block
    is a fact about the client record's state, not the caller's permissions, so it is
    a 409 from the shared guard.
    """
    client_record = _client_record(test_db, client_factory, status=status)
    service = AdvancePaymentService(test_db)

    with pytest.raises(ConflictError) as exc_info:
        service.create_payment_for_client(
            client_record_id=client_record.id,
            period="2026-05",
            period_months_count=1,
        )

    assert getattr(exc_info.value, "code", None) == "CLIENT_RECORD.CLOSED"


def test_ineligible_client_messages_distinguish_closed_from_frozen(test_db, client_factory):
    """A frozen client can be thawed and a closed one generally cannot — the advisor
    has to be able to tell which one blocked them, even though the code is uniform."""
    service = AdvancePaymentService(test_db)
    messages = {}
    for status in (ClientStatus.CLOSED, ClientStatus.FROZEN):
        record = _client_record(test_db, client_factory, status=status)
        with pytest.raises(ConflictError) as exc_info:
            service.create_payment_for_client(
                client_record_id=record.id,
                period="2026-05",
                period_months_count=1,
            )
        messages[status] = str(exc_info.value)

    assert messages[ClientStatus.CLOSED] != messages[ClientStatus.FROZEN]
