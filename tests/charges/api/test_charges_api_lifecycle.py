from app.businesses.models.business import Business, BusinessStatus
from tests.helpers.identity import seed_client_with_business


def _create_business(test_db) -> Business:
    _client, business = seed_client_with_business(
        test_db,
        full_name="Client B",
        id_number="222222222",
    )
    business.status = BusinessStatus.ACTIVE
    test_db.commit()
    return business


def _create_charge_via_api(client, advisor_headers, business) -> int:
    res = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": business.client_id,
            "business_id": business.id,
            "amount": 120.0,
            "charge_type": "consultation_fee",
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


def test_charge_lifecycle_draft_to_issued_to_paid(client, advisor_headers, test_db):
    business = _create_business(test_db)
    charge_id = _create_charge_via_api(client, advisor_headers, business)

    issue_res = client.post(f"/api/v1/charges/{charge_id}/issue", headers=advisor_headers)
    assert issue_res.status_code == 200
    issued = issue_res.json()
    assert issued["status"] == "issued"
    assert issued["issued_at"] is not None
    assert issued["paid_at"] is None

    paid_res = client.post(f"/api/v1/charges/{charge_id}/mark-paid", headers=advisor_headers)
    assert paid_res.status_code == 200
    paid = paid_res.json()
    assert paid["status"] == "paid"
    assert paid["paid_at"] is not None


def test_charge_lifecycle_issued_to_canceled(client, advisor_headers, test_db):
    business = _create_business(test_db)
    charge_id = _create_charge_via_api(client, advisor_headers, business)
    assert (
        client.post(f"/api/v1/charges/{charge_id}/issue", headers=advisor_headers).status_code
        == 200
    )

    cancel_res = client.post(f"/api/v1/charges/{charge_id}/cancel", headers=advisor_headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "canceled"


def test_invalid_transitions_return_400(client, advisor_headers, test_db):
    business = _create_business(test_db)
    charge_id = _create_charge_via_api(client, advisor_headers, business)

    pay_draft = client.post(f"/api/v1/charges/{charge_id}/mark-paid", headers=advisor_headers)
    assert pay_draft.status_code == 400
    assert pay_draft.json()["error"]["code"] == "CHARGE.INVALID_STATUS"

    assert (
        client.post(f"/api/v1/charges/{charge_id}/cancel", headers=advisor_headers).status_code
        == 200
    )
    issue_canceled = client.post(f"/api/v1/charges/{charge_id}/issue", headers=advisor_headers)
    assert issue_canceled.status_code == 400
    assert issue_canceled.json()["error"]["code"] == "CHARGE.INVALID_STATUS"

    charge_id_2 = _create_charge_via_api(client, advisor_headers, business)
    assert (
        client.post(f"/api/v1/charges/{charge_id_2}/issue", headers=advisor_headers).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/charges/{charge_id_2}/mark-paid", headers=advisor_headers).status_code
        == 200
    )
    cancel_paid = client.post(f"/api/v1/charges/{charge_id_2}/cancel", headers=advisor_headers)
    assert cancel_paid.status_code == 400
    assert cancel_paid.json()["error"]["code"] == "CHARGE.INVALID_STATUS"


def test_charge_not_found_responses(client, advisor_headers, test_db):
    assert client.get("/api/v1/charges/9999", headers=advisor_headers).status_code == 404
    issue_missing = client.post("/api/v1/charges/9999/issue", headers=advisor_headers)
    assert issue_missing.status_code == 404
    assert issue_missing.json()["error"]["code"] == "CHARGE.NOT_FOUND"
