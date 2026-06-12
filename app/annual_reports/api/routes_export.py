"""Annual report export endpoints."""

import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.annual_reports.services.annual_report_pdf_service import AnnualReportPdfService
from app.core.openapi_responses import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{report_id}/export/pdf", responses=not_found_response(description="הדוח המבוקש לא נמצא")
)
def export_annual_report_pdf(report_id: int, db: DBSession, user: CurrentUser) -> StreamingResponse:
    """Download a working-draft PDF (טיוטה לעיון) for the annual report."""
    svc = AnnualReportPdfService(db)
    pdf_bytes, tax_year = svc.generate(report_id)
    filename = f"annual_report_{report_id}_{tax_year}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
