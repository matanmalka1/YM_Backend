from fastapi import APIRouter, Depends, Query

from app.core.openapi_responses import not_found_response
from app.core.path_params import PathId
from app.documents.permanent_documents.schemas.permanent_document import (
    DocumentVersionsResponse,
)
from app.documents.permanent_documents.permanent_document_constants import DOCUMENT_VERSIONS_DEFAULT_LIMIT
from app.documents.permanent_documents.services.permanent_document_action_service import (
    PermanentDocumentActionService,
)
from app.documents.permanent_documents.permanent_document_response_builder import (
    PermanentDocumentResponseBuilder,
)
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/documents",
    tags=["permanent-documents"],
)


@router.get(
    "/client/{client_record_id}/versions",
    response_model=DocumentVersionsResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_document_versions(
    client_record_id: PathId,
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
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def list_by_annual_report(
    report_id: PathId,
    db: DBSession,
    user: CurrentUser,
):
    docs = PermanentDocumentActionService(db).list_by_annual_report(report_id)
    return DocumentVersionsResponse(
        items=PermanentDocumentResponseBuilder(db).build_many(docs),
    )
