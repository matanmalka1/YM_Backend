from sqlalchemy import String, cast
from sqlalchemy.dialects import postgresql

from app.businesses.models.business import Business
from app.common.enums import IdNumberType
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
    PermanentDocument,
)
from app.documents.permanent_documents.repositories.permanent_document_repository import (
    PermanentDocumentRepository,
)
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from tests.helpers.identity import seed_client_with_business


def _user(test_db) -> User:
    user = User(
        full_name="Permanent Doc Admin",
        email="permdoc.admin@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _business(test_db, *, suffix: str) -> Business:
    _client, business = seed_client_with_business(
        test_db,
        full_name=f"Permanent Client {suffix}",
        id_number=f"7105000{suffix}",
        id_number_type=IdNumberType.CORPORATION,
    )
    test_db.commit()
    return business


def test_count_by_business_ignores_soft_deleted_documents(test_db):
    user = _user(test_db)
    repo = PermanentDocumentRepository(test_db)
    business_a = _business(test_db, suffix="1")
    business_b = _business(test_db, suffix="2")

    active = repo.create(
        client_record_id=business_a.client_id,
        business_id=business_a.id,
        scope=DocumentScope.BUSINESS,
        document_type=PermanentDocumentType.TAX_FORM,
        storage_key="businesses/1/tax_form/a.pdf",
        uploaded_by=user.id,
    )
    deleted = repo.create(
        client_record_id=business_a.client_id,
        business_id=business_a.id,
        scope=DocumentScope.BUSINESS,
        document_type=PermanentDocumentType.BANK_APPROVAL,
        storage_key="businesses/1/bank_approval/b.pdf",
        uploaded_by=user.id,
    )
    repo.create(
        client_record_id=business_b.client_id,
        business_id=business_b.id,
        scope=DocumentScope.BUSINESS,
        document_type=PermanentDocumentType.RECEIPT,
        storage_key="businesses/2/receipt/c.pdf",
        uploaded_by=user.id,
    )

    deleted.is_deleted = True
    test_db.commit()

    assert active.is_deleted is False
    assert repo.count_by_business(business_a.id) == 1
    assert repo.count_by_business(business_b.id) == 1


def test_document_type_search_uses_cast_for_postgres_ilike():
    expr = cast(PermanentDocument.document_type, String).ilike("%id%")
    compiled = str(expr.compile(dialect=postgresql.dialect()))
    assert "CAST(permanent_documents.document_type AS VARCHAR)" in compiled
    assert "ILIKE" in compiled
