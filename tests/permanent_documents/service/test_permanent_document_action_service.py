from app.businesses.models.business import Business
from app.common.enums import IdNumberType
from app.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
    PermanentDocument,
)
from app.permanent_documents.repositories.permanent_document_repository import (
    PermanentDocumentRepository,
)
from app.permanent_documents.services.permanent_document_action_service import (
    PermanentDocumentActionService,
)
from tests.helpers.identity import seed_client_with_business


def _business(db) -> Business:
    _client, business = seed_client_with_business(
        db,
        full_name="Perm Action Client",
        id_number="71040001",
        id_number_type=IdNumberType.CORPORATION,
    )
    db.commit()
    return business


def _doc(db, business: Business, annual_report_id: int | None = None) -> PermanentDocument:
    return PermanentDocumentRepository(db).create(
        client_record_id=business.client_id,
        business_id=business.id,
        scope=DocumentScope.CLIENT,
        document_type=PermanentDocumentType.ID_COPY,
        storage_key="businesses/x/id_copy/a.pdf",
        uploaded_by=1,
        annual_report_id=annual_report_id,
    )


def test_list_versions_and_annual_report_documents(test_db):
    business = _business(test_db)
    _doc(test_db, business, annual_report_id=10)
    service = PermanentDocumentActionService(test_db)

    versions = service.get_document_versions(business.client_id, PermanentDocumentType.ID_COPY)
    assert len(versions) == 1
    by_report = service.list_by_annual_report(10)
    assert len(by_report) == 1


def test_list_versions_returns_empty_for_missing_document_type(test_db):
    business = _business(test_db)
    service = PermanentDocumentActionService(test_db)

    versions = service.get_document_versions(
        business.client_id, PermanentDocumentType.POWER_OF_ATTORNEY
    )
    assert versions == []
