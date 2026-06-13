"""issue #46 — ChargeResponse.updated_at.

NULL on create; set on a real mutation (issue) and on soft-delete.
Never faked from created_at.
"""

from app.businesses.models.business import Business, BusinessStatus
from tests.helpers.identity import seed_client_with_business


def _business(test_db) -> Business:
    _client, business = seed_client_with_business(
        test_db, full_name="Charge UpdatedAt", id_number="318318318"
    )
    business.status = BusinessStatus.ACTIVE
    test_db.commit()
    return business


def _create_charge(client, advisor_headers, business) -> int:
    res = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": business.client_id,
            "business_id": business.id,
            "amount": 100.0,
            "charge_type": "consultation_fee",
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


def test_updated_at_null_on_create_set_after_issue(client, advisor_headers, test_db):
    business = _business(test_db)
    charge_id = _create_charge(client, advisor_headers, business)

    created = client.get(f"/api/v1/charges/{charge_id}", headers=advisor_headers).json()
    assert "updated_at" in created
    assert created["updated_at"] is None

    assert (
        client.post(f"/api/v1/charges/{charge_id}/issue", headers=advisor_headers).status_code
        == 200
    )

    issued = client.get(f"/api/v1/charges/{charge_id}", headers=advisor_headers).json()
    assert issued["updated_at"] is not None
    # Not faked from created_at: a real mutation happened at/after creation.
    assert issued["updated_at"] >= issued["created_at"]


def test_soft_delete_bumps_updated_at(client, advisor_headers, test_db):
    business = _business(test_db)
    charge_id = _create_charge(client, advisor_headers, business)

    # Soft-delete is a mutation → updated_at must be set.
    assert client.delete(f"/api/v1/charges/{charge_id}", headers=advisor_headers).status_code in (
        200,
        204,
    )

    from app.charges.models.charge import Charge

    row = test_db.get(Charge, charge_id)
    assert row.deleted_at is not None
    assert row.updated_at is not None
