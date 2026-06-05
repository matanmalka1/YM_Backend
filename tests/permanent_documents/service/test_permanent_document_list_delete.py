import pytest

from app.businesses.models.business import Business
from app.common.enums import IdNumberType
from app.core.exceptions import NotFoundError
from app.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
)
from app.permanent_documents.repositories.permanent_document_repository import (
    PermanentDocumentRepository,
)
from app.permanent_documents.services.permanent_document_service import (
    PermanentDocumentService,
)
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from tests.helpers.identity import seed_client_with_business


def _user(test_db) -> User:
    user = User(
        full_name="Permanent Service User",
        email="permanent.service@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _business(test_db) -> Business:
    _client, business = seed_client_with_business(
        test_db,
        full_name="Permanent Service Client",
        id_number="71030001",
        id_number_type=IdNumberType.CORPORATION,
    )
    test_db.commit()
    return business


def test_list_business_documents_and_delete_document(test_db):
    user = _user(test_db)
    business = _business(test_db)
    repo = PermanentDocumentRepository(test_db)
    service = PermanentDocumentService(test_db)

    doc_2025 = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        scope=DocumentScope.BUSINESS,
        document_type=PermanentDocumentType.TAX_FORM,
        storage_key="businesses/1/tax_form/2025.pdf",
        uploaded_by=user.id,
        tax_year=2025,
    )
    doc_2024 = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        scope=DocumentScope.BUSINESS,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/1/bank_approval/2024.pdf",
        uploaded_by=user.id,
        tax_year=2024,
    )

    all_docs = service.list_business_documents(business.id)
    assert {d.id for d in all_docs} == {doc_2025.id, doc_2024.id}

    docs_2025 = service.list_business_documents(business.id, tax_year=2025)
    assert [d.id for d in docs_2025] == [doc_2025.id]

    service.delete_document(business.client_id, doc_2024.id)
    remaining = service.list_business_documents(business.id)
    assert [d.id for d in remaining] == [doc_2025.id]

    with pytest.raises(NotFoundError) as exc_info:
        service.delete_document(business.client_id, doc_2024.id)
    assert exc_info.value.code == "PERMANENT_DOCUMENTS.NOT_FOUND"
