"""Routes: invoice data entry (add / update / delete / list)."""

from fastapi import APIRouter, Depends, Query, status

from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole
from app.vat.models.vat_enums import InvoiceType
from app.vat.schemas.vat_invoice_schema import (
    VatInvoiceCreateRequest,
    VatInvoiceListResponse,
    VatInvoiceResponse,
)
from app.vat.schemas.vat_invoice_update import VatInvoiceUpdateRequest
from app.vat.services.vat_report_service import VatReportService

router = APIRouter(prefix="/vat", tags=["vat-reports"])


@router.post(
    "/work-items/{item_id}/invoices",
    response_model=VatInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description='פריט עבודה למע"מ לא נמצא'),
)
def add_invoice(
    item_id: int,
    request: VatInvoiceCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Add an income or expense invoice to a work item."""
    service = VatReportService(db)
    invoice, ceiling_warning = service.add_invoice(
        item_id=item_id,
        created_by=current_user.id,
        invoice_type=request.invoice_type,
        invoice_number=request.invoice_number,
        invoice_date=request.invoice_date,
        counterparty_name=request.counterparty_name,
        gross_amount=float(request.gross_amount),
        counterparty_id=request.counterparty_id,
        counterparty_id_type=request.counterparty_id_type,
        expense_category=request.expense_category,
        rate_type=request.rate_type,
        document_type=request.document_type,
        business_activity_id=request.business_activity_id,
    )
    response = VatInvoiceResponse.model_validate(invoice)
    response.ceiling_warning = ceiling_warning
    return response


@router.get(
    "/work-items/{item_id}/invoices",
    response_model=VatInvoiceListResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description='פריט עבודה למע"מ לא נמצא'),
)
def list_invoices(
    item_id: int,
    db: DBSession,
    current_user: CurrentUser,
    invoice_type: InvoiceType | None = Query(default=None),
):
    """List invoices for a work item, optionally filtered by type."""
    service = VatReportService(db)
    items = service.list_invoices(item_id=item_id, invoice_type=invoice_type)
    return VatInvoiceListResponse(items=items)


@router.patch(
    "/work-items/{item_id}/invoices/{invoice_id}",
    response_model=VatInvoiceResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="החשבונית המבוקשת לא נמצאה"),
)
def update_invoice(
    item_id: int,
    invoice_id: int,
    request: VatInvoiceUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Update an existing invoice. Not allowed after filing."""
    service = VatReportService(db)
    # Partial PATCH: only fields the client actually sent are forwarded, so
    # omitted fields stay unchanged and explicit null can clear nullable fields.
    patch = request.model_dump(exclude_unset=True)
    if "gross_amount" in patch and patch["gross_amount"] is not None:
        patch["gross_amount"] = float(patch["gross_amount"])
    return service.update_invoice(
        item_id=item_id,
        invoice_id=invoice_id,
        performed_by=current_user.id,
        patch=patch,
    )


@router.delete(
    "/work-items/{item_id}/invoices/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="החשבונית המבוקשת לא נמצאה"),
)
def delete_invoice(
    item_id: int,
    invoice_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Delete an invoice from a work item. Not allowed after filing."""
    service = VatReportService(db)
    service.delete_invoice(
        item_id=item_id,
        invoice_id=invoice_id,
        performed_by=current_user.id,
    )
