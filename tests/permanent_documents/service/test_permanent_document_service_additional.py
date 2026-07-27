from io import BytesIO

import pytest

from app.common.enums import IdNumberType
from app.core.exceptions import AppError, NotFoundError
from app.documents.permanent_documents.models.permanent_document import PermanentDocumentType
from app.documents.permanent_documents.services.permanent_document_service import (
    PermanentDocumentService,
)


class _Storage:
    def __init__(self):
        self.uploads = []

    def upload(self, key, file_data, content_type):
        self.uploads.append((key, content_type))
        return key

    def delete(self, key):
        return None

    def get_presigned_url(self, key, expires_in=3600):
        return f"/dl/{key}?exp={expires_in}"


def _business(create_client_with_business, *, suffix: str):
    _client, business = create_client_with_business(
        full_name=f"PermDoc Extra {suffix}",
        id_number=f"7102000{suffix}",
        id_number_type=IdNumberType.CORPORATION,
    )
    return business


def test_permanent_document_size_mime_and_download_not_found(
    test_db, test_user, create_client_with_business
):
    b = _business(create_client_with_business, suffix="1")
    service = PermanentDocumentService(test_db, storage=_Storage())

    with pytest.raises(AppError) as size_exc:
        service.upload_document(
            client_record_id=b.client_id,
            document_type=PermanentDocumentType.TAX_FORM,
            file_data=BytesIO(b"x" * (11 * 1024 * 1024)),
            filename="big.pdf",
            uploaded_by=test_user.id,
            mime_type="application/pdf",
            business_id=b.id,
        )
    assert size_exc.value.code == "DOCUMENT.FILE_TOO_LARGE"
    assert size_exc.value.status_code == 422

    with pytest.raises(AppError) as mime_exc:
        service.upload_document(
            client_record_id=b.client_id,
            document_type=PermanentDocumentType.TAX_FORM,
            file_data=BytesIO(b"ok"),
            filename="bad.bin",
            uploaded_by=test_user.id,
            mime_type="application/octet-stream",
            business_id=b.id,
        )
    assert mime_exc.value.code == "DOCUMENT.INVALID_FILE_TYPE"
    assert mime_exc.value.status_code == 422

    with pytest.raises(NotFoundError):
        service.get_download_url(b.client_id, 999999)


def test_permanent_document_replace_and_version_increment(
    test_db, test_user, create_client_with_business
):
    b = _business(create_client_with_business, suffix="2")
    storage = _Storage()
    service = PermanentDocumentService(test_db, storage=storage)
    doc = service.upload_document(
        client_record_id=b.client_id,
        document_type=PermanentDocumentType.TAX_FORM,
        file_data=BytesIO(b"first"),
        filename="tax_form.pdf",
        uploaded_by=test_user.id,
        mime_type="application/pdf",
        business_id=b.id,
    )
    replaced = service.replace_document(
        client_record_id=b.client_id,
        document_id=doc.id,
        file_data=BytesIO(b"second"),
        filename="id2.pdf",
        uploaded_by=test_user.id,
    )
    assert replaced.version == 2
    assert "v2_" in replaced.storage_key

    url = service.get_download_url(b.client_id, replaced.id, expires_in=120)
    assert "exp=120" in url
