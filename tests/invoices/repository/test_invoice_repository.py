from datetime import UTC, date, datetime
from decimal import Decimal

from app.charges.models.charge import ChargeType
from app.charges.repositories.charge_repository import ChargeRepository
from app.invoices.repositories.invoice_repository import InvoiceRepository
from tests.helpers.identity import seed_business, seed_client_identity


def _business(test_db):
    client = seed_client_identity(
        test_db,
        full_name="Invoice Client",
        id_number="INV001",
    )
    business = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name=client.full_name,
        opened_at=date(2024, 1, 1),
    )
    test_db.commit()
    test_db.refresh(business)
    business.client_id = client.id
    return business


def test_invoice_repository_getters(test_db):
    business = _business(test_db)
    charge_repo = ChargeRepository(test_db)
    invoice_repo = InvoiceRepository(test_db)

    charge = charge_repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("123.45"),
        charge_type=ChargeType.MONTHLY_RETAINER,
    )

    created = invoice_repo.create(
        charge_id=charge.id,
        provider="stripe",
        external_invoice_id="INV-EXT-1",
        issued_at=datetime(2024, 3, 1, tzinfo=UTC),
        document_url="https://example.com/inv.pdf",
    )

    assert invoice_repo.get_by_charge_id(charge.id).id == created.id
    assert invoice_repo.exists_for_charge(charge.id) is True
    assert invoice_repo.get_by_id(created.id).external_invoice_id == "INV-EXT-1"

    assert invoice_repo.get_by_charge_id(9999) is None
    assert invoice_repo.exists_for_charge(9999) is False


def test_invoice_repository_list_by_charge_ids(test_db):
    business = _business(test_db)
    charge_repo = ChargeRepository(test_db)
    invoice_repo = InvoiceRepository(test_db)

    charge_a = charge_repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("10.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
    )
    charge_b = charge_repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("20.00"),
        charge_type=ChargeType.OTHER,
    )

    inv_a = invoice_repo.create(
        charge_id=charge_a.id,
        provider="icount",
        external_invoice_id="INV-A",
        issued_at=datetime(2026, 2, 1, 10, 0, 0),
    )
    invoice_repo.create(
        charge_id=charge_b.id,
        provider="icount",
        external_invoice_id="INV-B",
        issued_at=datetime(2026, 2, 2, 10, 0, 0),
    )

    listed = invoice_repo.list_by_charge_ids([charge_a.id])
    assert [inv.id for inv in listed] == [inv_a.id]
    assert invoice_repo.list_by_charge_ids([]) == []
