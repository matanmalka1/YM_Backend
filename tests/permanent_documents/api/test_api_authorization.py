from io import BytesIO

from app.businesses.models.business import Business
from app.common.enums import IdNumberType
from tests.helpers.identity import seed_client_with_business


def _create_business(test_db) -> Business:
    _client, business = seed_client_with_business(
        test_db,
        full_name="API Test Client",
        id_number="71080001",
        id_number_type=IdNumberType.CORPORATION,
    )
    test_db.commit()
    return business


def test_secretary_can_upload_documents(client, secretary_headers, test_db):
    """Test that secretary can upload permanent documents."""
    b = _create_business(test_db)

    response = client.post(
        "/api/v1/documents/upload",
        headers=secretary_headers,
        data={
            "client_record_id": b.client_id,
            "business_id": b.id,
            "document_type": "tax_form",
        },
        files={"file": ("test.pdf", BytesIO(b"fake content"), "application/pdf")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["client_record_id"] == b.client_id
    assert data["business_id"] == b.id
    assert data["document_type"] == "tax_form"
    assert data["is_present"] is True


def test_advisor_can_upload_documents(client, advisor_headers, test_db):
    """Test that advisor can upload permanent documents."""
    b = _create_business(test_db)

    response = client.post(
        "/api/v1/documents/upload",
        headers=advisor_headers,
        data={
            "client_record_id": b.client_id,
            "business_id": b.id,
            "document_type": "bank_approval",
        },
        files={"file": ("bank.pdf", BytesIO(b"fake content"), "application/pdf")},
    )

    assert response.status_code == 201


def test_unauthenticated_cannot_upload_documents(client, test_db):
    """Test that unauthenticated users cannot upload documents."""
    b = _create_business(test_db)

    response = client.post(
        "/api/v1/documents/upload",
        data={
            "client_record_id": b.client_id,
            "business_id": b.id,
            "document_type": "id_copy",
        },
        files={"file": ("test.pdf", BytesIO(b"fake content"), "application/pdf")},
    )

    assert response.status_code == 401


def test_invalid_token_cannot_upload_documents(client, test_db):
    """Test that invalid token cannot upload documents."""
    b = _create_business(test_db)

    response = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": "Bearer invalid-token"},
        data={
            "client_record_id": b.client_id,
            "business_id": b.id,
            "document_type": "id_copy",
        },
        files={"file": ("test.pdf", BytesIO(b"fake content"), "application/pdf")},
    )

    assert response.status_code == 401


def test_secretary_can_view_operational_signals(client, secretary_headers, test_db):
    """Test that secretary can view operational signals."""
    b = _create_business(test_db)

    response = client.get(
        f"/api/v1/documents/client/{b.client_id}/signals",
        headers=secretary_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["client_record_id"] == b.client_id
    assert "missing_documents" in data


def test_advisor_can_view_operational_signals(client, advisor_headers, test_db):
    """Test that advisor can view operational signals."""
    b = _create_business(test_db)

    response = client.get(
        f"/api/v1/documents/client/{b.client_id}/signals",
        headers=advisor_headers,
    )

    assert response.status_code == 200
