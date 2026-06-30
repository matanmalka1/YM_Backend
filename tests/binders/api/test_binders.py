from tests.helpers.identity import SeededClient, seed_client_identity


def _seed_client(test_db, id_number: str, office_client_number: int) -> SeededClient:
    return seed_client_identity(
        test_db,
        full_name="Test Client",
        id_number=id_number,
        office_client_number=office_client_number,
    )


def _receive_request(
    client_record_id: int, received_by: int, received_at: str = "2026-02-08"
) -> dict:
    return {
        "client_record_id": client_record_id,
        "received_at": received_at,
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


def test_binder_receive_creates_initial_lifecycle_log(client, auth_token, test_db, test_user):
    test_client = _seed_client(test_db, "111222333", office_client_number=100101)

    response = client.post(
        "/api/v1/binders/receive",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={**_receive_request(test_client.id, test_user.id), "notes": "Test binder"},
    )

    assert response.status_code == 201
    binder_data = response.json()["binder"]
    binder_id = binder_data["id"]
    assert binder_data["binder_number"] == "100101/1"
    assert binder_data["period_start"] == "2026-02-01"
    assert binder_data["location_status"] == "in_office"
    assert binder_data["capacity_status"] == "open"
    assert binder_data["available_actions"] == [
        "mark_ready_for_handover",
        "receive_material",
        "mark_full",
    ]

    from app.audit.audit_constants import ACTION_BINDER_CREATED, ENTITY_BINDER
    from app.audit.repositories.audit_entity_audit_log_repository import (
        EntityAuditLogRepository,
    )

    rows = EntityAuditLogRepository(test_db).list_by_entity(ENTITY_BINDER, binder_id)

    # A new binder records one binder.created row (both initial statuses in new_value),
    # replacing the two legacy null->in_office / null->open lifecycle-log rows.
    assert len(rows) == 1
    created = rows[0]
    assert created.action == ACTION_BINDER_CREATED
    assert created.new_value == {"location_status": "in_office", "capacity_status": "open"}
    assert created.performed_by == test_user.id
    assert created.actor_display_name == test_user.full_name
    assert created.metadata_json["client_record_id"] == test_client.id


def test_lifecycle_endpoints_return_final_contract(client, auth_token, test_db, test_user):
    test_client = _seed_client(test_db, "444555666", office_client_number=100102)

    receive_response = client.post(
        "/api/v1/binders/receive",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=_receive_request(test_client.id, test_user.id),
    )
    assert receive_response.status_code == 201
    binder_id = receive_response.json()["binder"]["id"]

    full_response = client.post(
        f"/api/v1/binders/{binder_id}/mark-full",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert full_response.status_code == 200
    assert full_response.json()["capacity_status"] == "full"
    assert full_response.json()["available_actions"] == [
        "mark_ready_for_handover",
        "reopen_capacity",
    ]

    ready_response = client.post(
        f"/api/v1/binders/{binder_id}/mark-ready-for-handover",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert ready_response.status_code == 200
    ready_data = ready_response.json()
    assert ready_data["binder"]["location_status"] == "ready_for_handover"
    assert ready_data["binder"]["available_actions"] == [
        "revert_ready_for_handover",
        "handover_to_client",
    ]
    assert ready_data["notification"]["status"] in ("sent", "skipped", "failed", "blocked")

    handover_response = client.post(
        f"/api/v1/binders/{binder_id}/handover-to-client",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"handover_recipient_name": "Dana", "handed_over_at": "2026-03-03"},
    )

    assert handover_response.status_code == 200
    handed_over = handover_response.json()
    assert handed_over["location_status"] == "handed_over"
    assert handed_over["capacity_status"] == "full"
    assert handed_over["handover_recipient_name"] == "Dana"
    assert handed_over["available_actions"] == []


def test_binder_list_filters_and_counters_use_lifecycle_fields(
    client, auth_token, test_db, test_user
):
    test_client = _seed_client(test_db, "777888999", office_client_number=100103)

    receive_response = client.post(
        "/api/v1/binders/receive",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=_receive_request(test_client.id, test_user.id),
    )
    binder_id = receive_response.json()["binder"]["id"]
    client.post(
        f"/api/v1/binders/{binder_id}/mark-ready-for-handover",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    list_response = client.get(
        "/api/v1/binders?location_status=ready_for_handover",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert list_response.status_code == 200
    data = list_response.json()
    assert [item["id"] for item in data["items"]] == [binder_id]
    assert set(data["counters"]) == {
        "total",
        "location_in_office",
        "location_ready_for_handover",
        "location_handed_over",
        "capacity_open",
        "capacity_full",
    }


def test_mark_ready_for_handover_bulk_marks_matching_client_binders(
    client,
    auth_token,
    test_db,
    test_user,
):
    test_client = _seed_client(test_db, "999000111", office_client_number=100104)

    first_receive = client.post(
        "/api/v1/binders/receive",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "client_record_id": test_client.id,
            "received_at": "2026-02-08",
            "received_by": test_user.id,
            "materials": [
                {
                    "material_type": "other",
                    "period_year": 2026,
                    "period_month_start": 2,
                    "period_month_end": 2,
                }
            ],
        },
    )
    assert first_receive.status_code == 201
    first_binder_id = first_receive.json()["binder"]["id"]

    second_receive = client.post(
        "/api/v1/binders/receive",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "client_record_id": test_client.id,
            "received_at": "2026-03-10",
            "received_by": test_user.id,
            "open_new_binder": True,
            "materials": [
                {
                    "material_type": "other",
                    "period_year": 2026,
                    "period_month_start": 3,
                    "period_month_end": 3,
                }
            ],
        },
    )
    assert second_receive.status_code == 201
    second_binder_id = second_receive.json()["binder"]["id"]

    bulk_ready = client.post(
        "/api/v1/binders/mark-ready-for-handover-bulk",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "client_record_id": test_client.id,
            "until_period_year": 2026,
            "until_period_month": 2,
        },
    )

    assert bulk_ready.status_code == 200
    data = bulk_ready.json()
    assert [item["binder"]["id"] for item in data] == [first_binder_id]
    assert data[0]["binder"]["location_status"] == "ready_for_handover"
    assert data[0]["notification"]["status"] in ("sent", "skipped", "failed", "blocked")

    binders = client.get(
        f"/api/v1/binders?client_record_id={test_client.id}&location_status=ready_for_handover",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert binders.status_code == 200
    ready_ids = {item["id"] for item in binders.json()["items"]}
    assert first_binder_id in ready_ids
    assert second_binder_id not in ready_ids


def test_handover_to_client_bulk_records_group_and_transitions_binders(
    client,
    auth_token,
    test_db,
    test_user,
):
    test_client = _seed_client(test_db, "888000111", office_client_number=100105)
    receive_response = client.post(
        "/api/v1/binders/receive",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=_receive_request(test_client.id, test_user.id),
    )
    assert receive_response.status_code == 201
    binder_id = receive_response.json()["binder"]["id"]
    ready_response = client.post(
        f"/api/v1/binders/{binder_id}/mark-ready-for-handover",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert ready_response.status_code == 200

    response = client.post(
        "/api/v1/binders/handover-to-client-bulk",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "client_record_id": test_client.id,
            "binder_ids": [binder_id],
            "received_by_name": "Dana",
            "handed_over_at": "2026-03-03",
            "until_period_year": 2026,
            "until_period_month": 2,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["binder_ids"] == [binder_id]
    assert payload["received_by_name"] == "Dana"

    binder = client.get(
        f"/api/v1/binders/{binder_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert binder.status_code == 200
    assert binder.json()["location_status"] == "handed_over"
