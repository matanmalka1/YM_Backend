from datetime import date

from sqlalchemy import event

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.clients.client_enums import ClientStatus
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocument,
    PermanentDocumentType,
)
from app.search.services.search_service import SearchService
from app.tasks.models.task import Task


def _make_binder(
    db,
    client_record_id: int,
    binder_number: str,
    user_id: int,
    *,
    capacity_status: BinderCapacityStatus = BinderCapacityStatus.OPEN,
) -> Binder:
    b = Binder(
        client_record_id=client_record_id,
        binder_number=binder_number,
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=capacity_status,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def test_search_clients_db_pagination(
    client, test_db, advisor_headers, create_client_with_business
):
    """Page 2 should return correct offset results."""
    for i in range(5):
        create_client_with_business(
            full_name=f"Paginate Client {i:02d}",
            id_number=f"PAG{i:07d}",
        )

    r1 = client.get(
        "/api/v1/search?search=Paginate&page=1&page_size=3",
        headers=advisor_headers,
    )
    r2 = client.get(
        "/api/v1/search?search=Paginate&page=2&page_size=3",
        headers=advisor_headers,
    )

    assert r1.status_code == 200
    assert r2.status_code == 200
    d1 = r1.json()
    d2 = r2.json()

    assert d1["total"] == 5
    assert len(d1["results"]) == 3
    assert len(d2["results"]) == 2

    # Pages must not overlap
    ids_page1 = {r["client_record_id"] for r in d1["results"]}
    ids_page2 = {r["client_record_id"] for r in d2["results"]}
    assert ids_page1.isdisjoint(ids_page2)


def test_global_search_by_client_name_returns_client_results(
    client, advisor_headers, create_client_with_business
):
    crm_client, _business = create_client_with_business(
        full_name="רפאל בדיקות",
        id_number="RAF0000001",
    )

    response = client.get("/api/v1/search?search=רפאל", headers=advisor_headers)

    assert response.status_code == 200
    data = response.json()
    assert any(result["client_record_id"] == crm_client.id for result in data["results"])


def test_search_endpoint_returns_operational_task_group(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _business = create_client_with_business(full_name="Operational Search Client")
    task = Task(
        title="Unique operational follow-up",
        client_record_id=crm_client.id,
        created_by_user_id=test_user.id,
    )
    test_db.add(task)
    test_db.commit()

    response = client.get(
        f"/api/v1/search?search=operational&client_record_id={crm_client.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    group = response.json()["operational"]["tasks"]
    assert group["total"] == 1
    assert group["items"][0]["id"] == task.id
    assert group["items"][0]["href"].endswith(f"task_id={task.id}")


def test_client_search_bulk_loads_legal_entities(test_db, create_client_with_business):
    for i in range(20):
        create_client_with_business(
            full_name=f"Bulk Legal Entity {i:02d}",
            id_number=f"BLE{i:07d}",
        )

    statements: list[str] = []

    def track_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    bind = test_db.get_bind()
    event.listen(bind, "before_cursor_execute", track_query)
    try:
        results, _total, _documents = SearchService(test_db).search(
            client_status=ClientStatus.ACTIVE,
            page=1,
            page_size=20,
        )
    finally:
        event.remove(bind, "before_cursor_execute", track_query)

    assert len(results) == 20
    single_legal_entity_loads = [
        statement
        for statement in statements
        if "FROM legal_entities" in statement and "WHERE legal_entities.id =" in statement
    ]
    assert single_legal_entity_loads == []
    assert len(statements) <= 6


def test_search_binder_number_filter(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """DB-level binder_number filter returns only matching binders."""
    c, _business = create_client_with_business(
        full_name="Binder Filter Client",
        id_number="BFC0000001",
    )
    _make_binder(test_db, c.id, "ALPHA-001", test_user.id)
    _make_binder(test_db, c.id, "BETA-002", test_user.id)

    response = client.get(
        "/api/v1/search?binder_number=ALPHA",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    binder_results = [r for r in data["results"] if r["result_type"] == "binder"]
    assert len(binder_results) >= 1
    assert all("ALPHA" in r["binder_number"].upper() for r in binder_results)


def test_combined_client_and_binder_filters_are_intersected(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    matching, _ = create_client_with_business(
        full_name="Matching Active Full",
        id_number="MATCH-100",
        status=ClientStatus.ACTIVE,
    )
    wrong_status, _ = create_client_with_business(
        full_name="Frozen Full",
        id_number="FROZEN-200",
        status=ClientStatus.FROZEN,
    )
    wrong_capacity, _ = create_client_with_business(
        full_name="Active Open",
        id_number="OPEN-300",
        status=ClientStatus.ACTIVE,
    )
    _make_binder(
        test_db,
        matching.id,
        "MATCH-FULL",
        test_user.id,
        capacity_status=BinderCapacityStatus.FULL,
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
        "/api/v1/search?client_status=active&binder_capacity_status=full",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert [row["client_record_id"] for row in data["results"]] == [matching.id]


def test_free_text_matches_client_without_becoming_a_binder_number_filter(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Unique Client Name")
    _make_binder(test_db, crm_client.id, "UNRELATED-777", test_user.id)

    response = client.get(
        "/api/v1/search?search=Unique%20Client",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    rows = response.json()["results"]
    assert len(rows) == 1
    assert rows[0]["client_record_id"] == crm_client.id
    assert rows[0]["binder_number"] == "UNRELATED-777"


def test_binder_number_free_text_returns_owning_client_operational_items(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Binder Operational Owner")
    _make_binder(test_db, crm_client.id, "OPS-BINDER-991", test_user.id)
    task = Task(
        title="Task with unrelated title",
        client_record_id=crm_client.id,
        created_by_user_id=test_user.id,
    )
    test_db.add(task)
    test_db.commit()

    response = client.get(
        "/api/v1/search?search=OPS-BINDER-991",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    group = response.json()["operational"]["tasks"]
    assert group["total"] == 1
    assert [item["id"] for item in group["items"]] == [task.id]


def _make_document(
    db,
    *,
    client_record_id: int,
    business_id: int,
    filename: str,
    user_id: int,
) -> PermanentDocument:
    document = PermanentDocument(
        client_record_id=client_record_id,
        business_id=business_id,
        scope=DocumentScope.BUSINESS,
        document_type=PermanentDocumentType.OTHER,
        storage_key=f"tests/{client_record_id}/{filename}",
        original_filename=filename,
        uploaded_by=user_id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def test_search_documents_scoped_by_client_record_id(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    first_client, first_business = create_client_with_business(
        full_name="Scoped Document Client",
        id_number="SDC0000001",
    )
    second_client, second_business = create_client_with_business(
        full_name="Other Document Client",
        id_number="ODC0000001",
    )
    first_doc = _make_document(
        test_db,
        client_record_id=first_client.id,
        business_id=first_business.id,
        filename="audit_report_2026.pdf",
        user_id=test_user.id,
    )
    _make_document(
        test_db,
        client_record_id=second_client.id,
        business_id=second_business.id,
        filename="audit_report_2026.pdf",
        user_id=test_user.id,
    )

    response = client.get(
        f"/api/v1/search?search=audit_report&client_record_id={first_client.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    documents = response.json()["documents"]
    assert [doc["id"] for doc in documents] == [first_doc.id]
    assert all(doc["client_record_id"] == first_client.id for doc in documents)


def test_search_documents_with_different_client_record_id_does_not_leak(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    owner_client, owner_business = create_client_with_business(
        full_name="Owner Document Client",
        id_number="OWN0000001",
    )
    other_client, _other_business = create_client_with_business(
        full_name="Different Document Client",
        id_number="DIF0000001",
    )
    _make_document(
        test_db,
        client_record_id=owner_client.id,
        business_id=owner_business.id,
        filename="audit_report_private.pdf",
        user_id=test_user.id,
    )

    response = client.get(
        f"/api/v1/search?search=audit_report_private&client_record_id={other_client.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    assert response.json()["documents"] == []


def test_document_results_respect_advanced_client_filters(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    active_client, active_business = create_client_with_business(
        full_name="Active Document Owner",
        status=ClientStatus.ACTIVE,
    )
    frozen_client, frozen_business = create_client_with_business(
        full_name="Frozen Document Owner",
        status=ClientStatus.FROZEN,
    )
    active_document = _make_document(
        test_db,
        client_record_id=active_client.id,
        business_id=active_business.id,
        filename="shared_filtered_document.pdf",
        user_id=test_user.id,
    )
    _make_document(
        test_db,
        client_record_id=frozen_client.id,
        business_id=frozen_business.id,
        filename="shared_filtered_document.pdf",
        user_id=test_user.id,
    )

    response = client.get(
        "/api/v1/search?filename=shared_filtered&client_status=active",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    assert [document["id"] for document in response.json()["documents"]] == [active_document.id]


def test_operational_results_respect_advanced_client_filters(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    active_client, _ = create_client_with_business(
        full_name="Active Task Owner",
        status=ClientStatus.ACTIVE,
    )
    frozen_client, _ = create_client_with_business(
        full_name="Frozen Task Owner",
        status=ClientStatus.FROZEN,
    )
    active_task = Task(
        title="Shared filtered task",
        client_record_id=active_client.id,
        created_by_user_id=test_user.id,
    )
    test_db.add_all(
        [
            active_task,
            Task(
                title="Shared filtered task",
                client_record_id=frozen_client.id,
                created_by_user_id=test_user.id,
            ),
        ]
    )
    test_db.commit()

    response = client.get(
        "/api/v1/search?search=shared%20filtered&client_status=active",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    group = response.json()["operational"]["tasks"]
    assert group["total"] == 1
    assert [item["id"] for item in group["items"]] == [active_task.id]


def test_search_openapi_uses_search_and_client_record_id_params(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/search"]["get"]
    param_names = {param["name"] for param in operation["parameters"]}
    assert "search" in param_names
    assert "client_record_id" in param_names
    assert "client_id" not in param_names
    assert "query" not in param_names
    assert "client_name" not in param_names
    assert "client_search" not in param_names
