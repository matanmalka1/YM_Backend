from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.clients.client_constants import EXCEL_MEDIA_TYPE
from app.core.media_types import PDF_MEDIA_TYPE
from app.core.openapi_responses import binary_response_doc
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.reports.advance_payment_report import AdvancePaymentReportService
from app.reports.annual_report_status_report import (
    AnnualReportStatusReportService,
)
from app.reports.report_schemas import (
    AdvancePaymentCollectionsReportResponse,
    AgingReportResponse,
    AnnualReportStatusReportResponse,
    VatComplianceReportResponse,
)
from app.reports.services.report_reports_export_service import ReportsExportService
from app.reports.services.report_service import AgingReportService
from app.reports.vat_compliance_report import VatComplianceReportService
from app.users.api.user_deps import DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)


@router.get("/vat-compliance", response_model=VatComplianceReportResponse)
def get_vat_compliance_report(
    db: DBSession,
    year: int = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    service = VatComplianceReportService(db)
    return service.get_vat_compliance_report(year, page=page, page_size=page_size)


@router.get("/advance-payments", response_model=AdvancePaymentCollectionsReportResponse)
def get_advance_payment_report(
    db: DBSession,
    year: int = Query(...),
    month: int | None = Query(None),
):
    service = AdvancePaymentReportService(db)
    return service.get_collections_report(year, month)


@router.get(
    "/advance-payments/export",
    response_class=FileResponse,
    responses=binary_response_doc(EXCEL_MEDIA_TYPE, PDF_MEDIA_TYPE),
)
def export_advance_payment_report(
    db: DBSession,
    format: str = Query(..., pattern="^(excel|pdf)$"),
    year: int = Query(...),
    month: int | None = Query(None, ge=1, le=12),
):
    result = ReportsExportService(db).export_advance_payment_report(
        export_format=format, year=year, month=month
    )
    return FileResponse(
        path=result.filepath,
        media_type=result.media_type,
        filename=result.filename,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/annual-reports", response_model=AnnualReportStatusReportResponse)
def get_annual_report_status_report(
    db: DBSession,
    tax_year: int = Query(...),
):
    service = AnnualReportStatusReportService(db)
    return service.get_report(tax_year)


@router.get("/aging", response_model=AgingReportResponse)
def get_aging_report(
    db: DBSession,
    as_of_date: date | None = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    service = AgingReportService(db)
    return service.generate_aging_report(as_of_date=as_of_date, page=page, page_size=page_size)


@router.get(
    "/aging/export",
    response_class=FileResponse,
    responses=binary_response_doc(EXCEL_MEDIA_TYPE, PDF_MEDIA_TYPE),
)
def export_aging_report(
    db: DBSession,
    format: str = Query(..., pattern="^(excel|pdf)$"),
    as_of_date: date | None = Query(None),
):
    result = ReportsExportService(db).export_aging_report(
        export_format=format,
        as_of_date=as_of_date,
    )
    return FileResponse(
        path=result.filepath,
        media_type=result.media_type,
        filename=result.filename,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
