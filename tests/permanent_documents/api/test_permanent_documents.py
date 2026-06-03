from io import BytesIO
from itertools import count

from app.businesses.models.business import Business
from app.common.enums import IdNumberType
from app.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
)
from app.permanent_documents.repositories.permanent_document_repository import (
    PermanentDocumentRepository,
)
from tests.helpers.identity import seed_client_with_business

_client_seq = count(1)


def _business(db) -> Business:
    suffix = next(_client_seq)
    _client, b = seed_client_with_business(
        db,
        full_name=f"PermDoc Client {suffix}",
        id_number=f"7106000{suffix}",
        id_number_type=IdNumberType.CORPORATION,
    )
    db.commit()
    return b


def test_upload_and_list_documents(client, test_db, advisor_headers):
    business = _business(test_db)
    file_bytes = BytesIO(b"content")

    resp = client.post(
        "/api/v1/documents/upload",
        headers=advisor_headers,
        files={"file": ("id.pdf", file_bytes, "application/pdf")},
        data={
            "client_record_id": business.client_id,
            "business_id": business.id,
            "document_type": "id_copy",
        },
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["client_record_id"] == business.client_id
    assert doc["business_id"] == business.id
    assert doc["document_type"] == "id_copy"
    assert doc["scope"] == "business"
    assert doc["is_present"] is True
    doc_id = doc["id"]

    list_resp = client.get(
        f"/api/v1/documents/client/{business.client_id}", headers=advisor_headers
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == doc_id


def test_get_download_url_and_replace_document(client, test_db, advisor_headers):
    business = _business(test_db)
    repo = PermanentDocumentRepository(test_db)
    doc = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        scope=DocumentScope.CLIENT,
        document_type=PermanentDocumentType.ID_COPY,
        storage_key="businesses/x/id_copy/original.pdf",
        uploaded_by=1,
    )

    url_resp = client.get(f"/api/v1/documents/{doc.id}/download-url", headers=advisor_headers)
    assert url_resp.status_code == 200
    assert "url" in url_resp.json()

    replace_resp = client.put(
        f"/api/v1/documents/{doc.id}/replace",
        headers=advisor_headers,
        files={"file": ("new.pdf", BytesIO(b"new"), "application/pdf")},
    )
    assert replace_resp.status_code == 200
    replaced = replace_resp.json()
    assert replaced["id"] == doc.id
    assert replaced["is_present"] is True


def test_delete_document_marks_deleted(client, test_db, advisor_headers):
    business = _business(test_db)
    repo = PermanentDocumentRepository(test_db)
    doc = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        scope=DocumentScope.CLIENT,
        document_type=PermanentDocumentType.POWER_OF_ATTORNEY,
        storage_key="businesses/x/power_of_attorney/doc.pdf",
        uploaded_by=1,
    )

    del_resp = client.delete(f"/api/v1/documents/{doc.id}", headers=advisor_headers)
    assert del_resp.status_code == 204

    list_resp = client.get(
        f"/api/v1/documents/client/{business.client_id}", headers=advisor_headers
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["items"] == []


def test_upload_without_business_id_creates_client_owned_document(client, test_db, advisor_headers):
    business = _business(test_db)

    resp = client.post(
        "/api/v1/documents/upload",
        headers=advisor_headers,
        files={"file": ("id.pdf", BytesIO(b"content"), "application/pdf")},
        data={"client_record_id": business.client_id, "document_type": "id_copy"},
    )

    assert resp.status_code == 201
    doc = resp.json()
    assert doc["client_record_id"] == business.client_id
    assert doc["business_id"] is None
    assert doc["scope"] == "client"
