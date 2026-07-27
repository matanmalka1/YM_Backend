from datetime import date

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus


def _seed(binder_factory, binder_intake_factory, user_id: int, *, binder_number: str):
    binder = binder_factory(
        binder_number=binder_number,
        period_start=date(2026, 1, 1),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        commit=True,
    )

    intake = binder_intake_factory(
        binder=binder,
        received_by=user_id,
        received_at=date(2026, 3, 1),
        notes="original notes",
        commit=True,
    )

    return binder, intake


def test_patch_binder_intake_updates_notes(
    client,
    test_db,
    advisor_headers,
    test_user,
    binder_factory,
    binder_intake_factory,
):
    binder, intake = _seed(
        binder_factory, binder_intake_factory, test_user.id, binder_number="BPATCH-001"
    )

    resp = client.patch(
        f"/api/v1/binders/{binder.id}/intakes/{intake.id}",
        json={"notes": "updated notes"},
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == intake.id
    assert payload["notes"] == "updated notes"
    assert payload["binder_id"] == binder.id


def test_patch_binder_intake_wrong_binder_returns_404(
    client,
    test_db,
    advisor_headers,
    test_user,
    binder_factory,
    binder_intake_factory,
):
    binder_a, intake_a = _seed(
        binder_factory, binder_intake_factory, test_user.id, binder_number="BPATCH-002"
    )
    binder_b, _ = _seed(
        binder_factory, binder_intake_factory, test_user.id, binder_number="BPATCH-003"
    )

    resp = client.patch(
        f"/api/v1/binders/{binder_b.id}/intakes/{intake_a.id}",
        json={"notes": "should not update"},
        headers=advisor_headers,
    )

    assert resp.status_code == 404


def test_patch_binder_intake_nonexistent_intake_returns_404(
    client,
    test_db,
    advisor_headers,
    test_user,
    binder_factory,
    binder_intake_factory,
):
    binder, _ = _seed(
        binder_factory, binder_intake_factory, test_user.id, binder_number="BPATCH-004"
    )

    resp = client.patch(
        f"/api/v1/binders/{binder.id}/intakes/999999",
        json={"notes": "x"},
        headers=advisor_headers,
    )

    assert resp.status_code == 404


def test_patch_binder_intake_updates_received_at(
    client,
    test_db,
    advisor_headers,
    test_user,
    binder_factory,
    binder_intake_factory,
):
    binder, intake = _seed(
        binder_factory, binder_intake_factory, test_user.id, binder_number="BPATCH-005"
    )

    resp = client.patch(
        f"/api/v1/binders/{binder.id}/intakes/{intake.id}",
        json={"received_at": "2026-04-15"},
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["received_at"] == "2026-04-15"
