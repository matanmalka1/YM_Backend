from app.common.enums import IdNumberType
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
)


def _business(create_client_with_business, suffix: int):
    _, business = create_client_with_business(
        full_name=f"PermDoc Meta Client {suffix}",
        id_number=f"7206000{suffix}",
        id_number_type=IdNumberType.CORPORATION,
    )
    return business


def _make_document(permanent_document_factory, business, **overrides):
    kwargs = dict(
        client_record_id=business.client_id,
        business_id=business.id,
        scope=DocumentScope.BUSINESS,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/x/bank_approval/doc.pdf",
        uploaded_by=1,
        original_filename="doc.pdf",
        tax_year=2024,
    )
    kwargs.update(overrides)
    return permanent_document_factory(**kwargs)


# ── GET single document ──────────────────────────────────────────────────────


def test_get_document_returns_full_dto(
    client, test_db, advisor_headers, create_client_with_business, permanent_document_factory
):
    business = _business(create_client_with_business, 1)
    doc = _make_document(permanent_document_factory, business)

    resp = client.get(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}", headers=advisor_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == doc.id
    assert body["original_filename"] == "doc.pdf"
    assert body["tax_year"] == 2024
    assert body["binder_id"] is None


def test_get_document_not_found(client, test_db, advisor_headers, create_client_with_business):
    business = _business(create_client_with_business, 2)

    resp = client.get(
        f"/api/v1/documents/client/{business.client_id}/999999", headers=advisor_headers
    )
    assert resp.status_code == 404


def test_get_document_wrong_client_returns_404(
    client, test_db, advisor_headers, create_client_with_business, permanent_document_factory
):
    b1 = _business(create_client_with_business, 3)
    b2 = _business(create_client_with_business, 4)
    doc = _make_document(permanent_document_factory, b1)

    resp = client.get(f"/api/v1/documents/client/{b2.client_id}/{doc.id}", headers=advisor_headers)
    assert resp.status_code == 404


# ── PATCH document metadata ──────────────────────────────────────────────────


def test_patch_document_partial_update(
    client, test_db, advisor_headers, create_client_with_business, permanent_document_factory
):
    business = _business(create_client_with_business, 5)
    doc = _make_document(permanent_document_factory, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={"tax_year": 2025},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tax_year"] == 2025
    assert body["original_filename"] == "doc.pdf"
    assert body["document_type"] == "bank_approval"


def test_patch_document_does_not_change_version_or_storage(
    client, test_db, advisor_headers, create_client_with_business, permanent_document_factory
):
    business = _business(create_client_with_business, 6)
    doc = _make_document(permanent_document_factory, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={"original_filename": "renamed.pdf"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["original_filename"] == "renamed.pdf"
    assert body["version"] == doc.version
    assert body["storage_key"] == doc.storage_key
    assert body["file_size_bytes"] == doc.file_size_bytes
    assert body["mime_type"] == doc.mime_type


def test_patch_document_empty_body_returns_422(
    client, test_db, advisor_headers, create_client_with_business, permanent_document_factory
):
    business = _business(create_client_with_business, 7)
    doc = _make_document(permanent_document_factory, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={},
    )
    assert resp.status_code == 422


def test_patch_document_unknown_field_returns_422(
    client, test_db, advisor_headers, create_client_with_business, permanent_document_factory
):
    business = _business(create_client_with_business, 8)
    doc = _make_document(permanent_document_factory, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={"tags": ["x"]},
    )
    assert resp.status_code == 422


def test_patch_document_type_null_returns_422(
    client, test_db, advisor_headers, create_client_with_business, permanent_document_factory
):
    business = _business(create_client_with_business, 9)
    doc = _make_document(permanent_document_factory, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={"document_type": None},
    )
    assert resp.status_code == 422


def test_patch_document_tax_year_null_clears_it(
    client, test_db, advisor_headers, create_client_with_business, permanent_document_factory
):
    business = _business(create_client_with_business, 10)
    doc = _make_document(permanent_document_factory, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={"tax_year": None},
    )
    assert resp.status_code == 200
    assert resp.json()["tax_year"] is None


# ── GET documents by binder ───────────────────────────────────────────────────


def _make_binder(binder_factory, client_record_id: int, binder_number: str = "B-1"):
    return binder_factory(
        client_record_id=client_record_id,
        binder_number=binder_number,
        created_by=1,
    )


def test_list_binder_documents(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    binder_factory,
    permanent_document_factory,
):
    business = _business(create_client_with_business, 11)
    binder = _make_binder(binder_factory, business.client_id)
    doc = _make_document(permanent_document_factory, business, binder_id=binder.id)
    _make_document(
        permanent_document_factory, business, storage_key="businesses/x/other.pdf"
    )  # no binder_id

    resp = client.get(f"/api/v1/documents/binder/{binder.id}", headers=advisor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert [item["id"] for item in body["items"]] == [doc.id]


def test_list_binder_documents_excludes_deleted_and_superseded(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    binder_factory,
    permanent_document_factory,
):
    business = _business(create_client_with_business, 12)
    binder = _make_binder(binder_factory, business.client_id)
    deleted_doc = _make_document(
        permanent_document_factory,
        business,
        binder_id=binder.id,
        storage_key="businesses/x/deleted.pdf",
    )
    superseded_doc = _make_document(
        permanent_document_factory,
        business,
        binder_id=binder.id,
        storage_key="businesses/x/superseded.pdf",
    )
    deleted_doc.is_deleted = True
    superseded_doc.superseded_by = deleted_doc.id
    test_db.commit()

    resp = client.get(f"/api/v1/documents/binder/{binder.id}", headers=advisor_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_list_binder_documents_404_for_missing_binder(client, advisor_headers):
    resp = client.get("/api/v1/documents/binder/999999", headers=advisor_headers)
    assert resp.status_code == 404
