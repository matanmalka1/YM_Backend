"""Scoping: what matching must never return, on both endpoints."""

from datetime import UTC, datetime

from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocument,
    PermanentDocumentType,
)
from app.tasks.models.task import Task


def _make_task(db, client_record_id, user_id, title):
    task = Task(title=title, client_record_id=client_record_id, created_by_user_id=user_id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _make_document(db, *, client_record_id, business_id, filename, user_id):
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


def test_a_soft_deleted_record_is_excluded(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="לקוח מחיקה")
    task = _make_task(test_db, crm_client.id, test_user.id, "משימה שנמחקה")
    task.deleted_at = datetime.now(UTC)
    test_db.commit()

    matches = client.get("/api/v1/search?search=משימה שנמחקה", headers=advisor_headers).json()[
        "matches"
    ]

    assert matches["tasks"] == {"items": [], "total": 0}


def test_records_of_a_soft_deleted_client_are_excluded_on_both_endpoints(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """Closes the gap MAT-91 flagged: the client join must gate every path."""
    from app.clients.models.client_record import ClientRecord

    crm_client, _ = create_client_with_business(full_name="לקוח שנמחק רכות")
    _make_task(test_db, crm_client.id, test_user.id, "משימת רפאים")
    test_db.query(ClientRecord).filter(ClientRecord.id == crm_client.id).update(
        {"deleted_at": datetime.now(UTC)}
    )
    test_db.commit()

    search_matches = client.get(
        "/api/v1/search?search=משימת רפאים", headers=advisor_headers
    ).json()["matches"]
    expansion = client.get(
        "/api/v1/search/items?search=משימת רפאים&result_type=task", headers=advisor_headers
    ).json()

    assert search_matches["tasks"] == {"items": [], "total": 0}
    assert expansion == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_deleted_and_superseded_documents_are_excluded(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, business = create_client_with_business(full_name="לקוח מסמכים")
    deleted = _make_document(
        test_db,
        client_record_id=crm_client.id,
        business_id=business.id,
        filename="deleted.pdf",
        user_id=test_user.id,
    )
    deleted.is_deleted = True
    superseded = _make_document(
        test_db,
        client_record_id=crm_client.id,
        business_id=business.id,
        filename="superseded.pdf",
        user_id=test_user.id,
    )
    replacement = _make_document(
        test_db,
        client_record_id=crm_client.id,
        business_id=business.id,
        filename="replacement.pdf",
        user_id=test_user.id,
    )
    superseded.superseded_by = replacement.id
    test_db.commit()

    for filename in ("deleted.pdf", "superseded.pdf"):
        matches = client.get(f"/api/v1/search?search={filename}", headers=advisor_headers).json()[
            "matches"
        ]
        assert matches["documents"] == {"items": [], "total": 0}, filename

    alive = client.get("/api/v1/search?search=replacement.pdf", headers=advisor_headers).json()[
        "matches"
    ]["documents"]
    assert [row["id"] for row in alive["items"]] == [replacement.id]


def test_a_secretary_can_search_matches_too(
    client, test_db, secretary_headers, test_user, create_client_with_business
):
    """Both roles the router admits see matches; unauthenticated is a 401 (test_search)."""
    crm_client, _ = create_client_with_business(full_name="לקוח הרשאות")
    _make_task(test_db, crm_client.id, test_user.id, "משימת הרשאות")

    allowed = client.get("/api/v1/search?search=משימת הרשאות", headers=secretary_headers)

    assert allowed.status_code == 200
    assert [row["title"] for row in allowed.json()["matches"]["tasks"]["items"]]
