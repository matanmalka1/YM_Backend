from io import BytesIO

import pytest

from app.common.enums import IdNumberType
from app.core.exceptions import NotFoundError
from app.documents.permanent_documents.models.permanent_document import PermanentDocumentType
from app.documents.permanent_documents.services.permanent_document_service import (
    PermanentDocumentService,
)


def _business(create_client_with_business, *, suffix: str):
    _client, business = create_client_with_business(
        full_name=f"Doc Test Client {suffix}",
        id_number=f"7101000{suffix}",
        id_number_type=IdNumberType.CORPORATION,
    )
    return business


def test_upload_permanent_document(test_db, test_user, create_client_with_business):
    """Test uploading a permanent document."""
    business = _business(create_client_with_business, suffix="1")

    service = PermanentDocumentService(test_db)
    file_data = BytesIO(b"fake document content")

    document = service.upload_document(
        client_record_id=business.client_id,
        document_type=PermanentDocumentType.TAX_FORM,
        file_data=file_data,
        filename="tax_form.pdf",
        uploaded_by=test_user.id,
        business_id=business.id,
    )

    assert document is not None
    assert document.client_record_id == business.client_id
    assert document.business_id == business.id
    assert document.document_type == PermanentDocumentType.TAX_FORM
    assert document.is_present is True
    assert document.uploaded_by == test_user.id


def test_missing_document_types(test_db, test_user, create_client_with_business):
    """Test getting missing document types for a business."""
    business = _business(create_client_with_business, suffix="2")
    service = PermanentDocumentService(test_db)

    # Initially, all default required types are missing
    missing = service.get_missing_document_types(business.id)
    assert len(missing) == 3
    assert PermanentDocumentType.ID_COPY.value in missing
    assert PermanentDocumentType.POWER_OF_ATTORNEY.value in missing
    assert PermanentDocumentType.ENGAGEMENT_AGREEMENT.value in missing

    # Upload one required document (client-scoped — id_copy must not have business_id)
    file_data = BytesIO(b"fake content")
    service.upload_document(
        client_record_id=business.client_id,
        document_type=PermanentDocumentType.ID_COPY,
        file_data=file_data,
        filename="id.pdf",
        uploaded_by=test_user.id,
    )

    # Now only 2 should be missing
    missing_after = service.get_missing_document_types(business.id)
    assert len(missing_after) == 2
    assert PermanentDocumentType.ID_COPY.value not in missing_after


def test_upload_document_business_not_found(test_db, client_factory, actor_user):
    """Test that uploading document for non-existent business raises error."""
    service = PermanentDocumentService(test_db)
    file_data = BytesIO(b"fake content")
    client = client_factory(
        full_name="Doc Test Client Missing Business",
        id_number="710100099",
        id_number_type=IdNumberType.CORPORATION,
    )

    with pytest.raises(NotFoundError) as exc_info:
        service.upload_document(
            client_record_id=client.id,
            document_type=PermanentDocumentType.ID_COPY,
            file_data=file_data,
            filename="test.pdf",
            uploaded_by=actor_user.id,
            business_id=99999,
        )
    assert exc_info.value.code == "PERMANENT_DOCUMENTS.BUSINESS_NOT_FOUND"


def test_upload_document_without_business_uses_client_as_primary_owner(
    test_db, test_user, client_factory
):
    client = client_factory(
        full_name="Doc Test Client No Business",
        id_number="710100098",
        id_number_type=IdNumberType.CORPORATION,
    )

    service = PermanentDocumentService(test_db)
    document = service.upload_document(
        client_record_id=client.id,
        document_type=PermanentDocumentType.ID_COPY,
        file_data=BytesIO(b"fake document content"),
        filename="id_copy.pdf",
        uploaded_by=test_user.id,
    )

    assert document.client_record_id == client.id
    assert document.business_id is None
