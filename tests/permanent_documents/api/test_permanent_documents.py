from io import BytesIO

from app.common.enums import IdNumberType
from app.documents.permanent_documents.models.permanent_document import PermanentDocumentType


def _business(create_client_with_business, suffix: int):
    _client, business = create_client_with_business(
        full_name=f"PermDoc Client {suffix}",
        id_number=f"7106000{suffix}",
        id_number_type=IdNumberType.CORPORATION,
    )
    return business


def test_upload_and_list_documents(client, test_db, advisor_headers, create_client_with_business):
    business = _business(create_client_with_business, 1)
    file_bytes = BytesIO(b"content")

    resp = client.post(
        "/api/v1/documents/upload",
        headers=advisor_headers,
        files={"file": ("tax.pdf", file_bytes, "application/pdf")},
        data={
            "client_record_id": business.client_id,
            "business_id": business.id,
            "document_type": "tax_form",
        },
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["client_record_id"] == business.client_id
    assert doc["business_id"] == business.id
    assert doc["document_type"] == "tax_form"
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


def test_get_download_url_and_replace_document(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    permanent_document_factory,
    actor_user,
):
    business = _business(create_client_with_business, 2)
    doc = permanent_document_factory(
        client_record_id=business.client_id,
        business_id=business.id,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/x/bank_approval/original.pdf",
        uploaded_by=actor_user.id,
    )

    url_resp = client.get(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}/download-url",
        headers=advisor_headers,
    )
    assert url_resp.status_code == 200
    assert "url" in url_resp.json()

    replace_resp = client.put(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}/replace",
        headers=advisor_headers,
        files={"file": ("new.pdf", BytesIO(b"new"), "application/pdf")},
    )
    assert replace_resp.status_code == 200
    replaced = replace_resp.json()
    assert replaced["id"] == doc.id
    assert replaced["is_present"] is True


def test_delete_document_marks_deleted(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    permanent_document_factory,
    actor_user,
):
    business = _business(create_client_with_business, 3)
    doc = permanent_document_factory(
        client_record_id=business.client_id,
        business_id=business.id,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/x/bank_approval/doc.pdf",
        uploaded_by=actor_user.id,
    )

    del_resp = client.delete(
        f"/api/v1/documents/client/{business.client_id}/{doc.id}", headers=advisor_headers
    )
    assert del_resp.status_code == 204

    list_resp = client.get(
        f"/api/v1/documents/client/{business.client_id}", headers=advisor_headers
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["items"] == []


def test_delete_document_wrong_client_returns_404(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    permanent_document_factory,
    actor_user,
):
    b1 = _business(create_client_with_business, 4)
    b2 = _business(create_client_with_business, 5)
    doc = permanent_document_factory(
        client_record_id=b1.client_id,
        business_id=b1.id,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/b1/bank_approval/doc.pdf",
        uploaded_by=actor_user.id,
    )

    resp = client.delete(
        f"/api/v1/documents/client/{b2.client_id}/{doc.id}", headers=advisor_headers
    )
    assert resp.status_code == 404


def test_replace_document_wrong_client_returns_404(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    permanent_document_factory,
    actor_user,
):
    b1 = _business(create_client_with_business, 6)
    b2 = _business(create_client_with_business, 7)
    doc = permanent_document_factory(
        client_record_id=b1.client_id,
        business_id=b1.id,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/b1/bank_approval/doc2.pdf",
        uploaded_by=actor_user.id,
    )

    resp = client.put(
        f"/api/v1/documents/client/{b2.client_id}/{doc.id}/replace",
        headers=advisor_headers,
        files={"file": ("bad.pdf", BytesIO(b"x"), "application/pdf")},
    )
    assert resp.status_code == 404


def test_get_download_url_cross_client_returns_404(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    permanent_document_factory,
    actor_user,
):
    b1 = _business(create_client_with_business, 8)
    b2 = _business(create_client_with_business, 9)
    doc = permanent_document_factory(
        client_record_id=b1.client_id,
        business_id=b1.id,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/b1/bank_approval/secret.pdf",
        uploaded_by=actor_user.id,
    )

    resp = client.get(
        f"/api/v1/documents/client/{b2.client_id}/{doc.id}/download-url",
        headers=advisor_headers,
    )
    assert resp.status_code == 404


def test_get_download_url_deleted_document_returns_404(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    permanent_document_factory,
    actor_user,
):
    b = _business(create_client_with_business, 10)
    doc = permanent_document_factory(
        client_record_id=b.client_id,
        business_id=b.id,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/b/bank_approval/deleted.pdf",
        uploaded_by=actor_user.id,
    )
    client.delete(f"/api/v1/documents/client/{b.client_id}/{doc.id}", headers=advisor_headers)

    resp = client.get(
        f"/api/v1/documents/client/{b.client_id}/{doc.id}/download-url",
        headers=advisor_headers,
    )
    assert resp.status_code == 404


def test_upload_client_scope_type_with_business_id_rejected(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business, 11)

    for doc_type in ("id_copy", "power_of_attorney", "engagement_agreement"):
        resp = client.post(
            "/api/v1/documents/upload",
            headers=advisor_headers,
            files={"file": ("doc.pdf", BytesIO(b"content"), "application/pdf")},
            data={
                "client_record_id": business.client_id,
                "business_id": business.id,
                "document_type": doc_type,
            },
        )
        assert resp.status_code == 422, f"expected 422 for {doc_type}, got {resp.status_code}"
        assert resp.json()["error"]["code"] == "PERMANENT_DOCUMENTS.CLIENT_SCOPE_VIOLATION"


def test_upload_without_business_id_creates_client_owned_document(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business, 12)

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
