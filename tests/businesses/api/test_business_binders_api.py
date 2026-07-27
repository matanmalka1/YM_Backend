from datetime import date

from app.common.enums import IdNumberType


def _seed_client_business_and_binder(
    client_factory, business_factory, binder_factory, *, user_id: int
):
    client = client_factory(
        full_name="Binders Client",
        id_number="720000001",
        id_number_type=IdNumberType.CORPORATION,
        created_by=user_id,
    )
    business = business_factory(
        legal_entity_id=client.legal_entity_id,
        business_name="Binders Biz",
        opened_at=date(2025, 1, 1),
        created_by=user_id,
        commit=True,
    )
    binder = binder_factory(
        client_record_id=client.id,
        binder_number="BIZ-BIND-001",
        period_start=date(2026, 1, 1),
        created_by=user_id,
        commit=True,
    )

    return business, binder, client.id


def test_list_business_binders_returns_client_binders(
    client, test_db, test_user, advisor_headers, client_factory, business_factory, binder_factory
):
    business, binder, client_record_id = _seed_client_business_and_binder(
        client_factory, business_factory, binder_factory, user_id=test_user.id
    )

    response = client.get(
        f"/api/v1/clients/{client_record_id}/binders?page=1&page_size=20",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == binder.id
    assert data["items"][0]["client_record_id"] == client_record_id
    assert data["items"][0]["binder_number"] == "BIZ-BIND-001"


def test_list_business_binders_business_not_found(client, advisor_headers):
    response = client.get(
        "/api/v1/clients/999999/binders?page=1&page_size=20",
        headers=advisor_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLIENT_RECORD.NOT_FOUND"


# ── #46: BusinessResponse exposes updated_at (model has the column) ──


def test_business_response_includes_updated_at(client, advisor_headers):
    from tests.clients.helpers import create_client_via_api

    res = create_client_via_api(
        client,
        advisor_headers,
        full_name="Updated At Client",
        id_number="039337423",
        opened_at="2026-01-01",
    )
    assert res.status_code == 201
    business = res.json()["business"]
    # Field must be present in the contract (value may be null until first update).
    assert "updated_at" in business
