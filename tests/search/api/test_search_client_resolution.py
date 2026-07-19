"""Phase one of search: resolving the typed term and filters to client records."""

from datetime import date

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.clients.client_enums import ClientStatus


def _make_binder(
    db,
    client_record_id: int,
    binder_number: str,
    user_id: int,
    *,
    capacity_status: BinderCapacityStatus = BinderCapacityStatus.OPEN,
) -> Binder:
    binder = Binder(
        client_record_id=client_record_id,
        binder_number=binder_number,
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=capacity_status,
    )
    db.add(binder)
    db.commit()
    db.refresh(binder)
    return binder


def test_client_matches_are_paginated(client, advisor_headers, create_client_with_business):
    for i in range(5):
        create_client_with_business(full_name=f"Paginate Client {i:02d}", id_number=f"PAG{i:07d}")

    first = client.get("/api/v1/search?search=Paginate&page=1&page_size=3", headers=advisor_headers)
    second = client.get(
        "/api/v1/search?search=Paginate&page=2&page_size=3", headers=advisor_headers
    )

    page_one = first.json()["clients"]
    page_two = second.json()["clients"]
    assert page_one["total"] == 5
    assert len(page_one["items"]) == 3
    assert len(page_two["items"]) == 2
    assert {row["id"] for row in page_one["items"]}.isdisjoint(
        {row["id"] for row in page_two["items"]}
    )


def test_client_appears_once_regardless_of_binder_count(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """The old projection emitted one row per client/binder pair; a client is one row."""
    crm_client, _ = create_client_with_business(full_name="Many Binder Client")
    _make_binder(test_db, crm_client.id, "MB-001", test_user.id)
    _make_binder(test_db, crm_client.id, "MB-002", test_user.id)
    _make_binder(test_db, crm_client.id, "MB-003", test_user.id)

    response = client.get("/api/v1/search?search=Many%20Binder", headers=advisor_headers)

    clients = response.json()["clients"]
    assert clients["total"] == 1
    assert [row["id"] for row in clients["items"]] == [crm_client.id]


def test_binder_number_resolves_to_the_owning_client(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Binder Owner")
    _make_binder(test_db, crm_client.id, "OPS-BINDER-991", test_user.id)

    response = client.get("/api/v1/search?search=OPS-BINDER-991", headers=advisor_headers)

    match = response.json()["clients"]["items"][0]
    assert match["id"] == crm_client.id
    assert match["matched_binder_numbers"] == ["OPS-BINDER-991"]
    assert match["href"] == f"/clients/{crm_client.id}"


def test_matched_binder_numbers_stay_empty_for_a_name_search(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Unique Client Name")
    _make_binder(test_db, crm_client.id, "UNRELATED-777", test_user.id)

    response = client.get("/api/v1/search?search=Unique%20Client", headers=advisor_headers)

    assert response.json()["clients"]["items"][0]["matched_binder_numbers"] == []


def test_binder_number_filter_selects_owning_clients(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    owner, _ = create_client_with_business(full_name="Binder Filter Client")
    other, _ = create_client_with_business(full_name="Unmatched Binder Client")
    _make_binder(test_db, owner.id, "ALPHA-001", test_user.id)
    _make_binder(test_db, other.id, "BETA-002", test_user.id)

    response = client.get("/api/v1/search?binder_number=ALPHA", headers=advisor_headers)

    assert [row["id"] for row in response.json()["clients"]["items"]] == [owner.id]


def test_combined_client_and_binder_filters_are_intersected(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    matching, _ = create_client_with_business(
        full_name="Matching Active Full", id_number="MATCH-100", status=ClientStatus.ACTIVE
    )
    wrong_status, _ = create_client_with_business(
        full_name="Frozen Full", id_number="FROZEN-200", status=ClientStatus.FROZEN
    )
    wrong_capacity, _ = create_client_with_business(
        full_name="Active Open", id_number="OPEN-300", status=ClientStatus.ACTIVE
    )
    _make_binder(
        test_db, matching.id, "MATCH-FULL", test_user.id, capacity_status=BinderCapacityStatus.FULL
    )
    _make_binder(
        test_db,
        wrong_status.id,
        "FROZEN-FULL",
        test_user.id,
        capacity_status=BinderCapacityStatus.FULL,
    )
    _make_binder(test_db, wrong_capacity.id, "ACTIVE-OPEN", test_user.id)

    response = client.get(
        "/api/v1/search?client_status=active&binder_capacity_status=full", headers=advisor_headers
    )

    clients = response.json()["clients"]
    assert clients["total"] == 1
    assert [row["id"] for row in clients["items"]] == [matching.id]


def test_bulk_client_resolution_avoids_per_row_legal_entity_loads(
    test_db, create_client_with_business
):
    from sqlalchemy import event

    from app.search.services.search_service import SearchService

    for i in range(20):
        create_client_with_business(full_name=f"Bulk Legal Entity {i:02d}", id_number=f"BLE{i:07d}")

    statements: list[str] = []

    def track_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    bind = test_db.get_bind()
    event.listen(bind, "before_cursor_execute", track_query)
    try:
        response = SearchService(test_db).search(
            client_status=ClientStatus.ACTIVE, page=1, page_size=20
        )
    finally:
        event.remove(bind, "before_cursor_execute", track_query)

    assert len(response.clients.items) == 20
    per_row_loads = [
        statement
        for statement in statements
        if "FROM legal_entities" in statement and "WHERE legal_entities.id =" in statement
    ]
    assert per_row_loads == []
    assert len(statements) <= 4
