from app.businesses.models.business import Business
from app.common.enums import IdNumberType
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
)
from app.documents.permanent_documents.repositories.permanent_document_repository import (
    PermanentDocumentRepository,
)


def _doc(db, business: Business, annual_report_id: int | None = None):
    return PermanentDocumentRepository(db).create(
        client_record_id=business.client_id,
        business_id=business.id,
        scope=DocumentScope.CLIENT,
        document_type=PermanentDocumentType.ID_COPY,
        storage_key="businesses/x/id_copy/api.pdf",
        uploaded_by=1,
        annual_report_id=annual_report_id,
    )


def test_actions_endpoints_versions_and_list(
    client, test_db, advisor_headers, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Perm Action API Client",
        id_number="71070001",
        id_number_type=IdNumberType.CORPORATION,
    )
    _doc(test_db, business, annual_report_id=55)

    versions = client.get(
        f"/api/v1/documents/client/{business.client_id}/versions?document_type=id_copy",
        headers=advisor_headers,
    )
    assert versions.status_code == 200
    assert len(versions.json()["items"]) == 1

    by_report = client.get("/api/v1/documents/annual-report/55", headers=advisor_headers)
    assert by_report.status_code == 200
    assert len(by_report.json()["items"]) == 1
