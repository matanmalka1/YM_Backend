from datetime import date

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocument,
    PermanentDocumentType,
)


def _make_binder(db, client_record_id: int, binder_number: str, user_id: int) -> Binder:
    b = Binder(
        client_record_id=client_record_id,
        binder_number=binder_number,
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
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
    ids_page1 = {r["client_id"] for r in d1["results"]}
    ids_page2 = {r["client_id"] for r in d2["results"]}
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
    assert any(result["client_id"] == crm_client.id for result in data["results"])


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


def test_search_documents_scoped_by_client_id(
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
        f"/api/v1/search?search=audit_report&client_id={first_client.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    documents = response.json()["documents"]
    assert [doc["id"] for doc in documents] == [first_doc.id]
    assert all(doc["client_record_id"] == first_client.id for doc in documents)


def test_search_documents_with_different_client_id_does_not_leak(
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
        f"/api/v1/search?search=audit_report_private&client_id={other_client.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    assert response.json()["documents"] == []


def test_search_openapi_uses_search_and_client_id_params(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/search"]["get"]
    param_names = {param["name"] for param in operation["parameters"]}
    assert "search" in param_names
    assert "client_id" in param_names
    assert "query" not in param_names
    assert "client_name" not in param_names
    assert "client_search" not in param_names
