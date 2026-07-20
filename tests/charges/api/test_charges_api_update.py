from app.businesses.models.business import BusinessStatus
from tests.helpers.identity import seed_client_with_business


def _business(test_db):
    _client, business = seed_client_with_business(
        test_db,
        full_name="Charge Update",
        id_number="700000009",
    )
    business.status = BusinessStatus.ACTIVE
    test_db.commit()
    return business


def _create_draft(client, advisor_headers, business, **overrides):
    payload = {
        "client_record_id": business.client_id,
        "business_id": business.id,
        "amount": 100.0,
        "charge_type": "consultation_fee",
        **overrides,
    }
    response = client.post("/api/v1/charges", headers=advisor_headers, json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def test_update_draft_charge_applies_only_sent_fields(client, advisor_headers, test_db):
    business = _business(test_db)
    charge_id = _create_draft(client, advisor_headers, business, period="2026-03")

    response = client.patch(
        f"/api/v1/charges/{charge_id}",
        headers=advisor_headers,
        json={"amount": 250.5, "description": "תיקון סכום"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["amount"] == "250.50"
    assert payload["description"] == "תיקון סכום"
    # Untouched fields survive the partial update.
    assert payload["period"] == "2026-03"
    assert payload["charge_type"] == "consultation_fee"
    assert payload["status"] == "draft"
    assert payload["updated_at"] is not None


def test_update_charge_clears_business_scope_on_explicit_null(client, advisor_headers, test_db):
    business = _business(test_db)
    charge_id = _create_draft(client, advisor_headers, business)

    response = client.patch(
        f"/api/v1/charges/{charge_id}",
        headers=advisor_headers,
        json={"business_id": None},
    )

    assert response.status_code == 200
    assert response.json()["business_id"] is None


def test_update_rejects_explicit_null_on_not_null_field(client, advisor_headers, test_db):
    business = _business(test_db)
    charge_id = _create_draft(client, advisor_headers, business)

    response = client.patch(
        f"/api/v1/charges/{charge_id}",
        headers=advisor_headers,
        json={"amount": None},
    )

    assert response.status_code == 422


def test_update_rejects_non_positive_amount(client, advisor_headers, test_db):
    business = _business(test_db)
    charge_id = _create_draft(client, advisor_headers, business)

    response = client.patch(
        f"/api/v1/charges/{charge_id}",
        headers=advisor_headers,
        json={"amount": 0},
    )

    assert response.status_code == 422


def test_update_rejects_issued_charge(client, advisor_headers, test_db):
    business = _business(test_db)
    charge_id = _create_draft(client, advisor_headers, business)
    assert (
        client.post(f"/api/v1/charges/{charge_id}/issue", headers=advisor_headers).status_code
        == 200
    )

    response = client.patch(
        f"/api/v1/charges/{charge_id}",
        headers=advisor_headers,
        json={"amount": 300.0},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CHARGE.INVALID_STATUS"


def test_update_missing_charge_returns_404(client, advisor_headers):
    response = client.patch(
        "/api/v1/charges/999999",
        headers=advisor_headers,
        json={"amount": 10.0},
    )

    assert response.status_code == 404


def test_update_records_audit_diff(client, advisor_headers, test_db):
    business = _business(test_db)
    charge_id = _create_draft(client, advisor_headers, business)

    client.patch(
        f"/api/v1/charges/{charge_id}",
        headers=advisor_headers,
        json={"amount": 175.0},
    )

    audit = client.get(f"/api/v1/audit/charge/{charge_id}", headers=advisor_headers)
    assert audit.status_code == 200
    entries = audit.json()["items"]
    updates = [entry for entry in entries if entry["action"].endswith("updated")]
    assert len(updates) == 1
    assert updates[0]["old_value"] == {"amount": "100.00"}
    assert updates[0]["new_value"] == {"amount": "175.0"}
