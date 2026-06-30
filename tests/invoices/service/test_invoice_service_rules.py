from datetime import UTC, date, datetime

import pytest

from app.businesses.models.business import Business
from app.charges.services.charge_billing_service import BillingService
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.invoices.services.invoice_service import InvoiceService
from tests.helpers.identity import seed_business, seed_client_identity


def _create_business(test_db) -> Business:
    client = seed_client_identity(
        test_db,
        full_name="Client C",
        id_number="333333333",
    )
    business = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name=client.full_name,
        opened_at=date.today(),
    )
    test_db.commit()
    test_db.refresh(business)
    business.client_id = client.id
    return business


def test_attach_invoice_succeeds_only_for_issued_charge(test_db):
    business = _create_business(test_db)
    billing = BillingService(test_db)
    invoices = InvoiceService(test_db)

    draft = billing.create_charge(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=10.0,
        charge_type="consultation_fee",
        actor_id=1,
    )
    with pytest.raises(AppError) as exc_info:
        invoices.attach_invoice_to_charge(
            draft.id,
            "icount",
            "INV-1",
            issued_at=datetime.now(UTC).replace(tzinfo=None),
        )
    assert exc_info.value.code == "INVOICE.INVALID_STATUS"

    issued = billing.issue_charge(draft.id, actor_id=1)
    inv = invoices.attach_invoice_to_charge(
        issued.id,
        provider="icount",
        external_invoice_id="INV-2",
        issued_at=datetime(2026, 2, 1, 10, 0, 0),
        document_url="https://example.com/invoice/INV-2",
    )
    assert inv.charge_id == issued.id
    assert inv.external_invoice_id == "INV-2"

    billing.mark_charge_paid(issued.id, actor_id=1)
    with pytest.raises(AppError) as exc_info:
        invoices.attach_invoice_to_charge(
            issued.id,
            "icount",
            "INV-3",
            issued_at=datetime.now(UTC).replace(tzinfo=None),
        )
    assert exc_info.value.code == "INVOICE.INVALID_STATUS"

    canceled_id = billing.issue_charge(
        billing.create_charge(
            client_record_id=business.client_id,
            business_id=business.id,
            amount=30.0,
            charge_type="consultation_fee",
            actor_id=1,
        ).id,
        actor_id=1,
    ).id
    billing.cancel_charge(canceled_id, actor_id=1)
    with pytest.raises(AppError) as exc_info:
        invoices.attach_invoice_to_charge(
            canceled_id,
            "icount",
            "INV-4",
            issued_at=datetime.now(UTC).replace(tzinfo=None),
        )
    assert exc_info.value.code == "INVOICE.INVALID_STATUS"


def test_attach_invoice_fails_if_already_attached(test_db):
    business = _create_business(test_db)
    billing = BillingService(test_db)
    invoices = InvoiceService(test_db)

    ch = billing.issue_charge(
        billing.create_charge(
            client_record_id=business.client_id,
            business_id=business.id,
            amount=20.0,
            charge_type="monthly_retainer",
            actor_id=1,
        ).id,
        actor_id=1,
    )
    invoices.attach_invoice_to_charge(
        ch.id, "icount", "INV-10", issued_at=datetime.now(UTC).replace(tzinfo=None)
    )
    with pytest.raises(ConflictError) as exc_info:
        invoices.attach_invoice_to_charge(
            ch.id, "icount", "INV-11", issued_at=datetime.now(UTC).replace(tzinfo=None)
        )
    assert exc_info.value.code == "INVOICE.CONFLICT"


def test_attach_invoice_missing_charge_returns_not_found(test_db):
    invoices = InvoiceService(test_db)
    with pytest.raises(NotFoundError) as exc_info:
        invoices.attach_invoice_to_charge(
            999999,
            provider="icount",
            external_invoice_id="INV-MISSING",
            issued_at=datetime(2026, 1, 1, 12, 0, 0),
        )
    assert exc_info.value.code == "INVOICE.NOT_FOUND"
