from itertools import count

from app.binders.models.binder import Binder
from app.businesses.models.business import Business
from app.common.enums import IdNumberType
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
)
from app.documents.permanent_documents.repositories.permanent_document_repository import (
    PermanentDocumentRepository,
)
from tests.helpers.identity import seed_client_with_business

_client_seq = count(1)


def _business(db) -> Business:
    suffix = next(_client_seq)
    _, b = seed_client_with_business(
        db,
        full_name=f"PermDoc Meta Client {suffix}",
        id_number=f"7206000{suffix}",
        id_number_type=IdNumberType.CORPORATION,
    )
    db.commit()
    return b


def _make_document(db, business: Business, **overrides):
    repo = PermanentDocumentRepository(db)
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
    doc = repo.create(**kwargs)
    db.commit()
    return doc


# ── GET single document ──────────────────────────────────────────────────────


def test_get_document_returns_full_dto(client, test_db, advisor_headers):
    business = _business(test_db)
    doc = _make_document(test_db, business)

    resp = client.get(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}", headers=advisor_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == doc.id
    assert body["original_filename"] == "doc.pdf"
    assert body["tax_year"] == 2024
    assert body["binder_id"] is None


def test_get_document_not_found(client, test_db, advisor_headers):
    business = _business(test_db)

    resp = client.get(
        f"/api/v1/documents/client/{business.client_id}/999999", headers=advisor_headers
    )
    assert resp.status_code == 404


def test_get_document_wrong_client_returns_404(client, test_db, advisor_headers):
    b1 = _business(test_db)
    b2 = _business(test_db)
    doc = _make_document(test_db, b1)

    resp = client.get(f"/api/v1/documents/client/{b2.client_id}/{doc.id}", headers=advisor_headers)
    assert resp.status_code == 404


# ── PATCH document metadata ──────────────────────────────────────────────────


def test_patch_document_partial_update(client, test_db, advisor_headers):
    business = _business(test_db)
    doc = _make_document(test_db, business)

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


def test_patch_document_does_not_change_version_or_storage(client, test_db, advisor_headers):
    business = _business(test_db)
    doc = _make_document(test_db, business)

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


def test_patch_document_empty_body_returns_422(client, test_db, advisor_headers):
    business = _business(test_db)
    doc = _make_document(test_db, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={},
    )
    assert resp.status_code == 422


def test_patch_document_unknown_field_returns_422(client, test_db, advisor_headers):
    business = _business(test_db)
    doc = _make_document(test_db, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={"tags": ["x"]},
    )
    assert resp.status_code == 422


def test_patch_document_type_null_returns_422(client, test_db, advisor_headers):
    business = _business(test_db)
    doc = _make_document(test_db, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={"document_type": None},
    )
    assert resp.status_code == 422


def test_patch_document_tax_year_null_clears_it(client, test_db, advisor_headers):
    business = _business(test_db)
    doc = _make_document(test_db, business)

    resp = client.patch(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}",
        headers=advisor_headers,
        json={"tax_year": None},
    )
    assert resp.status_code == 200
    assert resp.json()["tax_year"] is None


# ── GET documents by binder ───────────────────────────────────────────────────


def _make_binder(db, client_record_id: int, binder_number: str = "B-1") -> Binder:
    binder = Binder(
        client_record_id=client_record_id,
        binder_number=binder_number,
        created_by=1,
    )
    db.add(binder)
    db.commit()
    return binder


def test_list_binder_documents(client, test_db, advisor_headers):
    business = _business(test_db)
    binder = _make_binder(test_db, business.client_id)
    doc = _make_document(test_db, business, binder_id=binder.id)
    _make_document(test_db, business, storage_key="businesses/x/other.pdf")  # no binder_id

    resp = client.get(f"/api/v1/documents/binder/{binder.id}", headers=advisor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert [item["id"] for item in body["items"]] == [doc.id]


def test_list_binder_documents_excludes_deleted_and_superseded(client, test_db, advisor_headers):
    business = _business(test_db)
    binder = _make_binder(test_db, business.client_id)
    deleted_doc = _make_document(
        test_db, business, binder_id=binder.id, storage_key="businesses/x/deleted.pdf"
    )
    superseded_doc = _make_document(
        test_db, business, binder_id=binder.id, storage_key="businesses/x/superseded.pdf"
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
