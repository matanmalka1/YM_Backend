"""Client resolution: the typed term resolves to the clients it identifies."""

from datetime import UTC, date, datetime

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus


def _make_binder(
    db,
    client_record_id: int,
    binder_number: str,
    user_id: int,
) -> Binder:
    binder = Binder(
        client_record_id=client_record_id,
        binder_number=binder_number,
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
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


def test_term_resolves_a_handed_over_binder_to_its_owner(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """Where a binder is now does not change whose it is — the term identifies, it does not filter."""
    owner, _ = create_client_with_business(full_name="Handed Over Owner")
    binder = _make_binder(test_db, owner.id, "HANDED-4242", test_user.id)
    binder.location_status = BinderLocationStatus.HANDED_OVER
    test_db.commit()

    response = client.get("/api/v1/search?search=HANDED-4242", headers=advisor_headers)

    match = response.json()["clients"]["items"][0]
    assert match["id"] == owner.id
    assert match["matched_binder_numbers"] == ["HANDED-4242"]


def test_a_deleted_binder_never_resolves_its_owner(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    owner, _ = create_client_with_business(full_name="Deleted Binder Owner")
    binder = _make_binder(test_db, owner.id, "DELETED-9001", test_user.id)
    binder.deleted_at = datetime.now(UTC)
    test_db.commit()

    response = client.get("/api/v1/search?search=DELETED-9001", headers=advisor_headers)

    assert response.json()["clients"]["total"] == 0


def test_a_resolved_search_runs_at_most_four_queries(test_db, create_client_with_business):
    """Client rows + client count + binder explanations + one match query — never more.

    Replaces the 19-query dossier path this contract deleted (MAT-89); also guards
    against per-row legal-entity loads and any N+1 in building match client identity.
    """
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
        response = SearchService(test_db).search("Bulk Legal Entity", page=1, page_size=20)
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


def test_an_expansion_runs_at_most_two_queries(test_db, test_user, create_client_with_business):
    from sqlalchemy import event

    from app.search.schemas.search import SearchMatchType
    from app.search.services.search_service import SearchService
    from app.tasks.models.task import Task

    crm_client, _ = create_client_with_business(full_name="Expansion Budget")
    for _ in range(3):
        test_db.add(
            Task(
                title="expansion budget task",
                client_record_id=crm_client.id,
                created_by_user_id=test_user.id,
            )
        )
    test_db.commit()

    statements: list[str] = []

    def track_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    bind = test_db.get_bind()
    event.listen(bind, "before_cursor_execute", track_query)
    try:
        response = SearchService(test_db).list_matches(
            "expansion budget task", SearchMatchType.TASK, page=1, page_size=5
        )
    finally:
        event.remove(bind, "before_cursor_execute", track_query)

    assert response.total == 3
    assert len(statements) <= 2
