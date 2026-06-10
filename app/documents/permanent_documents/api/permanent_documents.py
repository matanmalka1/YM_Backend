from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.documents.permanent_documents.models.permanent_document import DocumentStatus, PermanentDocumentType
from app.documents.permanent_documents.schemas.permanent_document import (
    DocumentDownloadUrlResponse,
    OperationalSignalsResponse,
    PermanentDocumentListResponse,
    PermanentDocumentResponse,
)
from app.documents.permanent_documents.services.permanent_document_service import (
    PermanentDocumentService,
)
from app.documents.permanent_documents.services.response_builder import (
    PermanentDocumentResponseBuilder,
)
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/documents",
    tags=["permanent-documents"],
)


@router.post(
    "/upload",
    response_model=PermanentDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def upload_permanent_document(
    client_record_id: Annotated[int, Form(...)],
    document_type: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
    db: DBSession,
    user: CurrentUser,
    business_id: Annotated[int | None, Form()] = None,
    tax_year: Annotated[int | None, Form()] = None,
    annual_report_id: Annotated[int | None, Form()] = None,
):
    """Upload permanent document (ADVISOR and SECRETARY)."""
    service = PermanentDocumentService(db)
    document = service.upload_document(
        client_record_id=client_record_id,
        document_type=document_type,
        file_data=file.file,
        filename=file.filename or "document",
        uploaded_by=user.id,
        business_id=business_id,
        tax_year=tax_year,
        annual_report_id=annual_report_id,
        mime_type=file.content_type,
    )
    return PermanentDocumentResponseBuilder(db).build_one(document)


@router.get(
    "/client/{client_record_id}",
    response_model=PermanentDocumentListResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_client_documents(
    client_record_id: int,
    db: DBSession,
    user: CurrentUser,
    tax_year: int | None = Query(default=None),
    document_type: PermanentDocumentType | None = Query(default=None),
    status: DocumentStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """List permanent documents for a client."""
    service = PermanentDocumentService(db)
    documents, total = service.list_client_documents(
        client_record_id,
        page=page,
        page_size=page_size,
        tax_year=tax_year,
        document_type=document_type,
        status=status,
    )

    return PermanentDocumentListResponse(
        items=PermanentDocumentResponseBuilder(db).build_many(documents),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/client/{client_record_id}/signals",
    response_model=OperationalSignalsResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def get_operational_signals(
    client_record_id: int,
    db: DBSession,
    user: CurrentUser,
):
    """Get operational signals for a client (advisory indicators)."""
    signals = PermanentDocumentService(db).get_client_operational_signals(client_record_id)
    return OperationalSignalsResponse(**signals)


@router.get(
    "/client/{client_record_id}/{document_id}/download-url",
    response_model=DocumentDownloadUrlResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def get_download_url(client_record_id: int, document_id: int, db: DBSession, user: CurrentUser):
    """Get a presigned download URL for a document (expires in 1 hour)."""
    url = PermanentDocumentService(db).get_download_url(client_record_id, document_id)
    return {"url": url}


@router.delete(
    "/client/{client_record_id}/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def delete_document(client_record_id: int, document_id: int, db: DBSession, user: CurrentUser):
    """Soft-delete a permanent document (ADVISOR only)."""
    PermanentDocumentService(db).delete_document(client_record_id, document_id)


@router.put(
    "/client/{client_record_id}/{document_id}/replace",
    response_model=PermanentDocumentResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def replace_document(
    client_record_id: int,
    document_id: int,
    file: Annotated[UploadFile, File(...)],
    db: DBSession,
    user: CurrentUser,
):
    """Replace the file for an existing document (ADVISOR only)."""
    doc = PermanentDocumentService(db).replace_document(
        client_record_id=client_record_id,
        document_id=document_id,
        file_data=file.file,
        filename=file.filename or "document",
        uploaded_by=user.id,
        mime_type=file.content_type,
    )
    return PermanentDocumentResponseBuilder(db).build_one(doc)
