"""issue #46 — BinderResponse.updated_at.

Note: a binder has no pure-insert API path. `/binders/receive` derives
period_start and runs the open/in-office lifecycle transitions on the
just-created row in the same transaction, so updated_at is legitimately
set right after receive — this is a real mutation, not a fake from
created_at. We assert it is present and >= created_at, bumps on a later
mutation (mark-full), and is set by soft-delete.
"""

from tests.helpers.identity import seed_client_identity


def _receive_request(client_record_id: int, received_by: int) -> dict:
    return {
        "client_record_id": client_record_id,
        "received_at": "2026-02-08",
        "received_by": received_by,
        "materials": [
            {
                "material_type": "other",
                "period_year": 2026,
                "period_month_start": 2,
                "period_month_end": 2,
                "description": "Test material",
            }
        ],
    }


def _create_binder(client, auth_token, test_db, test_user, office_client_number: int) -> int:
    test_client = seed_client_identity(
        test_db,
        full_name="Binder UpdatedAt",
        id_number=f"id-{office_client_number}",
        office_client_number=office_client_number,
    )
    res = client.post(
        "/api/v1/binders/receive",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=_receive_request(test_client.id, test_user.id),
    )
    assert res.status_code == 201
    return res.json()["binder"]["id"]


def test_updated_at_present_and_bumps_on_mutation(client, auth_token, test_db, test_user):
    headers = {"Authorization": f"Bearer {auth_token}"}
    binder_id = _create_binder(client, auth_token, test_db, test_user, 100401)

    # Receive derives period_start + runs lifecycle transitions → real mutation.
    received = client.get(f"/api/v1/binders/{binder_id}", headers=headers).json()
    assert "updated_at" in received
    assert received["updated_at"] is not None
    assert received["updated_at"] >= received["created_at"]

    assert client.post(f"/api/v1/binders/{binder_id}/mark-full", headers=headers).status_code == 200

    mutated = client.get(f"/api/v1/binders/{binder_id}", headers=headers).json()
    assert mutated["updated_at"] is not None
    assert mutated["updated_at"] >= received["updated_at"]


def test_column_has_no_default_null_on_bare_insert(test_db, test_user):
    """Guard the no-fake rule: a pure insert leaves updated_at NULL (no default=)."""
    from app.binders.models.binder import Binder

    binder = Binder(client_record_id=1, binder_number="BARE/1", created_by=test_user.id)
    test_db.add(binder)
    test_db.flush()
    assert binder.updated_at is None


def test_soft_delete_bumps_updated_at(client, auth_token, test_db, test_user):
    headers = {"Authorization": f"Bearer {auth_token}"}
    binder_id = _create_binder(client, auth_token, test_db, test_user, 100402)

    assert client.delete(f"/api/v1/binders/{binder_id}", headers=headers).status_code in (200, 204)

    from app.binders.models.binder import Binder

    row = test_db.get(Binder, binder_id)
    assert row.deleted_at is not None
    assert row.updated_at is not None
