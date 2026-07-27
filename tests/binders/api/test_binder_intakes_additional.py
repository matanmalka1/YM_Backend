from datetime import date

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus


def _seed_binder_and_intakes(binder_factory, binder_intake_factory, user_id: int, count: int = 1):
    binder = binder_factory(
        binder_number="BIN-1",
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        commit=True,
    )

    for i in range(count):
        binder_intake_factory(
            binder=binder,
            received_by=user_id,
            received_at=date(2024, 1, i + 1),
            notes=f"docs-{i}",
        )

    return binder


def test_binder_intakes_endpoint_success_and_not_found(
    client,
    test_db,
    advisor_headers,
    test_user,
    binder_factory,
    binder_intake_factory,
):
    binder = _seed_binder_and_intakes(binder_factory, binder_intake_factory, test_user.id)

    ok = client.get(f"/api/v1/binders/{binder.id}/intakes", headers=advisor_headers)
    assert ok.status_code == 200
    payload = ok.json()
    # #42: envelope converged to PaginatedResponse — no binder_id, items not intakes.
    assert "binder_id" not in payload
    assert "intakes" not in payload
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    assert len(payload["items"]) == 1
    assert payload["items"][0]["received_by_name"] == test_user.full_name

    missing = client.get("/api/v1/binders/999999/intakes", headers=advisor_headers)
    assert missing.status_code == 404


def test_binder_intakes_pagination(
    client,
    test_db,
    advisor_headers,
    test_user,
    binder_factory,
    binder_intake_factory,
):
    binder = _seed_binder_and_intakes(binder_factory, binder_intake_factory, test_user.id, count=3)

    resp = client.get(
        f"/api/v1/binders/{binder.id}/intakes",
        params={"page": 1, "page_size": 2},
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert payload["page_size"] == 2
    assert len(payload["items"]) == 2

    resp2 = client.get(
        f"/api/v1/binders/{binder.id}/intakes",
        params={"page": 2, "page_size": 2},
        headers=advisor_headers,
    )
    assert resp2.status_code == 200
    assert len(resp2.json()["items"]) == 1
