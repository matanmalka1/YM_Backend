"""issue #46 — CorrespondenceResponse.updated_at.

Correspondence is mutable via PATCH. updated_at is NULL on create, set on a
real update, and set on soft-delete. Never faked from created_at.
"""

from datetime import date

from app.businesses.models.business import Business
from tests.helpers.identity import seed_client_with_business


def _business(test_db, id_number: str) -> Business:
    _client, business = seed_client_with_business(
        test_db,
        full_name="Corr UpdatedAt",
        id_number=id_number,
        business_name=f"Corr {id_number}",
        opened_at=date.today(),
    )
    test_db.commit()
    test_db.refresh(business)
    return business


def _create_entry(client, headers, business) -> int:
    res = client.post(
        f"/api/v1/clients/{business.client_id}/correspondence",
        headers=headers,
        json={
            "business_id": business.id,
            "correspondence_type": "call",
            "subject": "Initial",
            "occurred_at": "2026-02-10T10:00:00",
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


def test_updated_at_null_on_create_set_after_patch(client, test_db, advisor_headers):
    business = _business(test_db, "910910910")
    entry_id = _create_entry(client, advisor_headers, business)

    created = client.get(
        f"/api/v1/clients/{business.client_id}/correspondence/{entry_id}",
        headers=advisor_headers,
    ).json()
    assert "updated_at" in created
    assert created["updated_at"] is None

    patched = client.patch(
        f"/api/v1/clients/{business.client_id}/correspondence/{entry_id}",
        headers=advisor_headers,
        json={"subject": "Corrected"},
    )
    assert patched.status_code == 200
    assert patched.json()["subject"] == "Corrected"

    after = client.get(
        f"/api/v1/clients/{business.client_id}/correspondence/{entry_id}",
        headers=advisor_headers,
    ).json()
    assert after["updated_at"] is not None
    assert after["updated_at"] >= after["created_at"]


def test_soft_delete_bumps_updated_at(client, test_db, advisor_headers):
    business = _business(test_db, "911911911")
    entry_id = _create_entry(client, advisor_headers, business)

    assert (
        client.delete(
            f"/api/v1/clients/{business.client_id}/correspondence/{entry_id}",
            headers=advisor_headers,
        ).status_code
        in (200, 204)
    )

    from app.communications.models.correspondence import Correspondence

    row = test_db.get(Correspondence, entry_id)
    assert row.deleted_at is not None
    assert row.updated_at is not None
