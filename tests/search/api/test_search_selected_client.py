"""The gate between the two search phases: which client, if any, the feed belongs to.

A `client_record_id` in the request is a *request* for a client, not a fact. It only selects
that client when client resolution — the term plus every advanced filter — returns it.
"""

from datetime import date

from app.binders.models.binder import Binder, BinderLocationStatus
from app.clients.client_enums import ClientStatus

EMPTY_GROUP = {"items": [], "total": 0}


def _make_binder(db, client_record_id: int, binder_number: str, user_id: int) -> Binder:
    binder = Binder(
        client_record_id=client_record_id,
        binder_number=binder_number,
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
    )
    db.add(binder)
    db.commit()
    db.refresh(binder)
    return binder


def _assert_no_feed(payload: dict) -> None:
    assert payload["items"] == {key: EMPTY_GROUP for key in payload["items"]}


def test_requested_client_inside_the_filtered_results_gets_its_feed(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Selected Feed Client")
    _make_binder(test_db, crm_client.id, "SEL-001", test_user.id)

    response = client.get(
        f"/api/v1/search?search=Selected%20Feed&client_record_id={crm_client.id}",
        headers=advisor_headers,
    )

    payload = response.json()
    assert payload["clients"]["total"] == 1
    assert [row["id"] for row in payload["clients"]["items"]] == [crm_client.id]
    assert payload["items"]["binders"]["total"] == 1


def test_requested_client_contradicted_by_the_term_gets_no_feed(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """The regression: a stale selection must not outrank the term typed beside it."""
    selected, _ = create_client_with_business(full_name="Stale Selection Client")
    create_client_with_business(full_name="Other Term Client")
    _make_binder(test_db, selected.id, "STALE-001", test_user.id)

    response = client.get(
        f"/api/v1/search?search=Other%20Term&client_record_id={selected.id}",
        headers=advisor_headers,
    )

    payload = response.json()
    assert payload["clients"]["total"] == 0
    assert payload["clients"]["items"] == []
    _assert_no_feed(payload)


def test_requested_client_contradicted_by_an_advanced_filter_gets_no_feed(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    selected, _ = create_client_with_business(
        full_name="Active Selection Client", status=ClientStatus.ACTIVE
    )
    _make_binder(test_db, selected.id, "FILTERED-001", test_user.id)

    response = client.get(
        f"/api/v1/search?client_record_id={selected.id}&client_status=frozen",
        headers=advisor_headers,
    )

    payload = response.json()
    assert payload["clients"]["total"] == 0
    _assert_no_feed(payload)


def test_unknown_requested_client_gets_no_feed(client, advisor_headers):
    response = client.get("/api/v1/search?client_record_id=999999", headers=advisor_headers)

    payload = response.json()
    assert payload["clients"]["total"] == 0
    _assert_no_feed(payload)


def test_a_term_resolving_to_one_client_selects_it_without_a_request(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Sole Match Client")
    _make_binder(test_db, crm_client.id, "SOLE-001", test_user.id)

    response = client.get("/api/v1/search?search=Sole%20Match", headers=advisor_headers)

    payload = response.json()
    assert payload["clients"]["total"] == 1
    assert payload["items"]["binders"]["total"] == 1


def test_a_term_resolving_to_several_clients_selects_none(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    first, _ = create_client_with_business(full_name="Ambiguous Match One")
    second, _ = create_client_with_business(full_name="Ambiguous Match Two")
    _make_binder(test_db, first.id, "AMB-001", test_user.id)
    _make_binder(test_db, second.id, "AMB-002", test_user.id)

    response = client.get("/api/v1/search?search=Ambiguous%20Match", headers=advisor_headers)

    payload = response.json()
    assert payload["clients"]["total"] == 2
    _assert_no_feed(payload)


def test_no_item_groups_are_queried_for_a_contradicted_selection(
    test_db, test_user, create_client_with_business
):
    """Not just empty in the response — the per-type reads must not run at all."""
    from sqlalchemy import event

    from app.search.services.search_service import SearchService

    selected, _ = create_client_with_business(full_name="Unqueried Feed Client")
    create_client_with_business(full_name="Different Term Client")
    _make_binder(test_db, selected.id, "UNQ-001", test_user.id)

    statements: list[str] = []

    def track_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    bind = test_db.get_bind()
    event.listen(bind, "before_cursor_execute", track_query)
    try:
        response = SearchService(test_db).search(
            search="Different Term", client_record_id=selected.id
        )
    finally:
        event.remove(bind, "before_cursor_execute", track_query)

    assert response.clients.total == 0
    item_reads = [
        statement
        for statement in statements
        if "FROM tasks" in statement or "FROM charges" in statement or "FROM documents" in statement
    ]
    assert item_reads == []
