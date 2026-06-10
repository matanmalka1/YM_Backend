from app.businesses.models.business import Business, BusinessStatus
from tests.helpers.identity import seed_client_with_business


def _create_business(test_db) -> Business:
    _client, business = seed_client_with_business(
        test_db,
        full_name="Client Inv",
        id_number="444444444",
    )
    business.status = BusinessStatus.ACTIVE
    test_db.commit()
    return business


def _issued_charge_id(client, advisor_headers, business) -> int:
    res = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": business.client_id,
            "business_id": business.id,
            "amount": 150.0,
            "charge_type": "consultation_fee",
        },
    )
    assert res.status_code == 201
    charge_id = res.json()["id"]
    assert (
        client.post(f"/api/v1/charges/{charge_id}/issue", headers=advisor_headers).status_code
        == 200
    )
    return charge_id


def test_attach_invoice_and_fetch_by_charge(client, advisor_headers, test_db):
    business = _create_business(test_db)
    charge_id = _issued_charge_id(client, advisor_headers, business)

    res = client.post(
        "/api/v1/invoices",
        headers=advisor_headers,
        json={
            "charge_id": charge_id,
            "provider": "icount",
            "external_invoice_id": "INV-API-1",
            "issued_at": "2026-02-01T10:00:00",
            "document_url": "https://example.com/invoice/INV-API-1",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["charge_id"] == charge_id
    assert body["external_invoice_id"] == "INV-API-1"
    assert body["provider"] == "icount"

    fetched = client.get(f"/api/v1/invoices/charge/{charge_id}", headers=advisor_headers)
    assert fetched.status_code == 200
    assert fetched.json()["external_invoice_id"] == "INV-API-1"


def test_attach_invoice_on_draft_charge_returns_400(client, advisor_headers, test_db):
    business = _create_business(test_db)
    res = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": business.client_id,
            "business_id": business.id,
            "amount": 90.0,
            "charge_type": "consultation_fee",
        },
    )
    assert res.status_code == 201
    draft_id = res.json()["id"]

    attach = client.post(
        "/api/v1/invoices",
        headers=advisor_headers,
        json={
            "charge_id": draft_id,
            "provider": "icount",
            "external_invoice_id": "INV-DRAFT",
            "issued_at": "2026-02-01T10:00:00",
        },
    )
    assert attach.status_code == 400
    assert attach.json()["error"]["code"] == "INVOICE.INVALID_STATUS"


def test_attach_invoice_twice_returns_409(client, advisor_headers, test_db):
    business = _create_business(test_db)
    charge_id = _issued_charge_id(client, advisor_headers, business)

    payload = {
        "charge_id": charge_id,
        "provider": "icount",
        "external_invoice_id": "INV-DUP",
        "issued_at": "2026-02-01T10:00:00",
    }
    assert client.post("/api/v1/invoices", headers=advisor_headers, json=payload).status_code == 201
    dup = client.post("/api/v1/invoices", headers=advisor_headers, json=payload)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "INVOICE.CONFLICT"


def test_attach_invoice_missing_charge_returns_404(client, advisor_headers):
    res = client.post(
        "/api/v1/invoices",
        headers=advisor_headers,
        json={
            "charge_id": 999999,
            "provider": "icount",
            "external_invoice_id": "INV-MISSING",
            "issued_at": "2026-01-01T12:00:00",
        },
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "INVOICE.NOT_FOUND"


def test_get_charge_invoice_missing_returns_404(client, advisor_headers, test_db):
    business = _create_business(test_db)
    charge_id = _issued_charge_id(client, advisor_headers, business)
    res = client.get(f"/api/v1/invoices/charge/{charge_id}", headers=advisor_headers)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "INVOICE.NOT_FOUND"


def test_attach_invoice_requires_auth(client):
    res = client.post(
        "/api/v1/invoices",
        json={
            "charge_id": 1,
            "provider": "icount",
            "external_invoice_id": "INV-NOAUTH",
            "issued_at": "2026-01-01T12:00:00",
        },
    )
    assert res.status_code == 401
