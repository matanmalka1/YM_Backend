from app.businesses.models.business import Business
from app.common.enums import IdNumberType
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
)


def _doc(permanent_document_factory, business: Business, annual_report_id: int | None = None):
    return permanent_document_factory(
        client_record_id=business.client_id,
        business_id=business.id,
        scope=DocumentScope.CLIENT,
        document_type=PermanentDocumentType.ID_COPY,
        storage_key="businesses/x/id_copy/api.pdf",
        annual_report_id=annual_report_id,
    )


def test_actions_endpoints_versions_and_list(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    permanent_document_factory,
    annual_report_model_factory,
):
    _client, business = create_client_with_business(
        full_name="Perm Action API Client",
        id_number="71070001",
        id_number_type=IdNumberType.CORPORATION,
    )
    report = annual_report_model_factory(client_record_id=business.client_id)
    _doc(permanent_document_factory, business, annual_report_id=report.id)

    versions = client.get(
        f"/api/v1/documents/client/{business.client_id}/versions?document_type=id_copy",
        headers=advisor_headers,
    )
    assert versions.status_code == 200
    assert len(versions.json()["items"]) == 1

    by_report = client.get(
        f"/api/v1/documents/annual-report/{report.id}", headers=advisor_headers
    )
    assert by_report.status_code == 200
    assert len(by_report.json()["items"]) == 1
