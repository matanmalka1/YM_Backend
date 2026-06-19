from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.clients.client_constants import EXCEL_MEDIA_TYPE, MAX_CLIENT_IMPORT_UPLOAD_SIZE
from app.clients.schemas.client import ClientImportResponse
from app.clients.services.client_create_service import CreateClientService
from app.clients.services.client_excel_service import (
    ClientExcelImportError,
    ClientExcelService,
)
from app.clients.services.client_query_service import ClientQueryService
from app.core.openapi_responses import binary_response_doc
from app.infrastructure.idempotency import IdempotencyGuard, require_idempotency_key
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

MAX_UPLOAD_SIZE = MAX_CLIENT_IMPORT_UPLOAD_SIZE

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/export",
    response_class=FileResponse,
    responses=binary_response_doc(EXCEL_MEDIA_TYPE),
)
def export_clients(db: DBSession):
    """Return all clients as an Excel workbook."""
    excel_service = ClientExcelService(db)
    try:
        result = excel_service.export_clients(ClientQueryService(db).list_all_clients())
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return FileResponse(
        path=result["filepath"],
        media_type=EXCEL_MEDIA_TYPE,
        filename=result["filename"],
    )


@router.get(
    "/template",
    response_class=FileResponse,
    responses=binary_response_doc(EXCEL_MEDIA_TYPE),
)
def download_client_template(db: DBSession):
    """Download a starter Excel template for client imports."""
    excel_service = ClientExcelService(db)
    try:
        result = excel_service.generate_template()
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return FileResponse(
        path=result["filepath"],
        media_type=EXCEL_MEDIA_TYPE,
        filename=result["filename"],
    )


@router.post(
    "/import",
    response_model=ClientImportResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
async def import_clients_from_excel(
    file: UploadFile,
    request: Request,
    db: DBSession,
    user: CurrentUser,
    idem: IdempotencyGuard = Depends(require_idempotency_key),
):
    """Create clients in bulk from an Excel file (advisor-only)."""
    content_length = request.headers.get("Content-Length")
    parsed_content_length = int(content_length) if content_length is not None else None
    contents = await file.read(MAX_UPLOAD_SIZE + 1)
    create_client_service = CreateClientService(db)
    excel_service = ClientExcelService(db)

    def _run():
        try:
            return excel_service.import_clients_from_upload(
                contents,
                create_client_service,
                actor_id=user.id,
                content_length=parsed_content_length,
                max_upload_size=MAX_UPLOAD_SIZE,
            )
        except ClientExcelImportError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=str(exc),
            ) from exc

    return idem.execute(payload=contents, fn=_run)
