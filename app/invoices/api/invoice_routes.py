from fastapi import APIRouter, Depends, status

from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.core.openapi_responses import (
    bad_request_response,
    conflict_response,
    error_responses,
    not_found_response,
)
from app.core.path_params import PathId
from app.invoices.repositories.invoice_repository import InvoiceRepository
from app.invoices.schemas.invoice_schemas import InvoiceAttachRequest, InvoiceResponse
from app.invoices.services.invoice_service import InvoiceService
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/invoices",
    tags=["invoices"],
)


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=error_responses(
        bad_request_response(description="נתוני החשבונית אינם תקינים"),
        not_found_response(description="החיוב המבוקש לא נמצא"),
        conflict_response(description="כבר קיימת חשבונית מצורפת לחיוב זה"),
    ),
)
def attach_invoice(request: InvoiceAttachRequest, db: DBSession, user: CurrentUser):
    invoice = InvoiceService(db).attach_invoice_to_charge(
        charge_id=request.charge_id,
        provider=request.provider,
        external_invoice_id=request.external_invoice_id,
        issued_at=request.issued_at,
        document_url=request.document_url,
        actor_id=user.id,
        actor_name=user.full_name,
    )
    return invoice


@router.get(
    "/charge/{charge_id}",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="החיוב המבוקש לא נמצא"),
)
def get_charge_invoice(charge_id: PathId, db: DBSession):
    invoice = InvoiceRepository(db).get_by_charge_id(charge_id)
    if not invoice:
        raise NotFoundError(f"לחיוב {charge_id} לא נמצאה חשבונית", ErrorCode.INVOICE_NOT_FOUND)
    return invoice
