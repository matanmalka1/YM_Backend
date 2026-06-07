from fastapi import APIRouter, Depends, Query

from app.permanent_documents.schemas.permanent_document import (
    DocumentVersionsResponse,
)
from app.permanent_documents.services.constants import DOCUMENT_VERSIONS_DEFAULT_LIMIT
from app.permanent_documents.services.permanent_document_action_service import (
    PermanentDocumentActionService,
)
from app.permanent_documents.services.response_builder import (
    PermanentDocumentResponseBuilder,
)
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/documents",
    tags=["permanent-documents"],
)


@router.get(
    "/client/{client_record_id}/versions",
    response_model=DocumentVersionsResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def get_document_versions(
    client_record_id: int,
    db: DBSession,
    user: CurrentUser,
    document_type: str = Query(...),
    tax_year: int | None = Query(default=None),
):
    docs, has_more = PermanentDocumentActionService(db).get_document_versions(
        client_record_id, document_type, tax_year
    )
    return DocumentVersionsResponse(
        items=PermanentDocumentResponseBuilder(db).build_many(docs),
        limit=DOCUMENT_VERSIONS_DEFAULT_LIMIT,
        has_more=has_more,
    )


@router.get(
    "/annual-report/{report_id}",
    response_model=DocumentVersionsResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_by_annual_report(
    report_id: int,
    db: DBSession,
    user: CurrentUser,
):
    docs = PermanentDocumentActionService(db).list_by_annual_report(report_id)
    return DocumentVersionsResponse(
        items=PermanentDocumentResponseBuilder(db).build_many(docs),
    )
