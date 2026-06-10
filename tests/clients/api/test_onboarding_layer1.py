"""Layer 1 onboarding tests: LegalEntity + ClientRecord creation."""

from datetime import date

from sqlalchemy import select

from app.advance_payments.models.advance_payment import AdvancePayment
from app.binders.models.binder import Binder
from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from app.vat.models.vat_work_item import VatWorkItem

_CREATE_PAYLOAD = {
    "client": {
        "full_name": "Layer1 Test Client",
        "id_number": "514713288",
        "id_number_type": "corporation",
        "entity_type": "company_ltd",
        "phone": "050-0000001",
        "email": "layer1@example.com",
        "address_street": "Test St",
        "address_building_number": "1",
        "address_apartment": "1",
        "address_city": "Tel Aviv",
        "address_zip_code": "0000001",
        "vat_reporting_frequency": "monthly",
        "advance_payment_frequency": "monthly",
        "advance_rate": "5.0",
        "accountant_id": 1,
    },
    "business": {
        "business_name": "Layer1 Business",
        "opened_at": str(date.today()),
    },
}


def _post_create(client, headers, payload=None):
    return client.post("/api/v1/clients", headers=headers, json=payload or _CREATE_PAYLOAD)


def test_full_onboarding_creates_all_entities(client, test_db, advisor_headers):
    """Full onboarding creates LegalEntity, ClientRecord, Business, and Binder."""
    resp = _post_create(client, advisor_headers)
    assert resp.status_code == 201, resp.json()
    data = resp.json()

    assert "client_record_id" in data
    cr_id = data["client_record_id"]
    assert isinstance(cr_id, int)

    cr = test_db.scalars(select(ClientRecord).filter(ClientRecord.id == cr_id)).first()
    assert cr is not None

    le = test_db.scalars(select(LegalEntity).filter(LegalEntity.id == cr.legal_entity_id)).first()
    assert le is not None
    assert le.id_number == "514713288"

    binder = test_db.scalars(select(Binder).filter(Binder.client_record_id == cr_id)).first()
    assert binder is not None


def test_duplicate_id_number_raises_conflict(client, test_db, advisor_headers):
    """Second onboarding with same id_number raises 409."""
    resp1 = _post_create(client, advisor_headers)
    assert resp1.status_code == 201

    import copy

    payload2 = copy.deepcopy(_CREATE_PAYLOAD)
    payload2["client"]["full_name"] = "Duplicate Client"
    payload2["business"]["business_name"] = "Duplicate Business"

    resp2 = _post_create(client, advisor_headers, payload2)
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] in {
        "CLIENT.CONFLICT",
        "CLIENT.DELETED_EXISTS",
    }


def test_obligations_created_with_client_record_id(client, test_db, advisor_headers):
    """VAT work items and advance payments created during onboarding carry client_record_id."""
    resp = _post_create(client, advisor_headers)
    assert resp.status_code == 201
    cr_id = resp.json()["client_record_id"]

    vat_items = test_db.scalars(
        select(VatWorkItem).filter(VatWorkItem.client_record_id == cr_id)
    ).all()
    advance_payments = test_db.scalars(
        select(AdvancePayment).filter(AdvancePayment.client_record_id == cr_id)
    ).all()
    assert len(vat_items) > 0 or len(advance_payments) > 0, (
        "No VAT work items or advance payments created during onboarding"
    )
