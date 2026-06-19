"""Annual report export endpoints."""

import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.annual_reports.services.annual_report_pdf_service import AnnualReportPdfService
from app.core.media_types import PDF_MEDIA_TYPE
from app.core.openapi_responses import binary_response_doc, error_responses, not_found_response
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{report_id}/export/pdf",
    response_class=StreamingResponse,
    responses=error_responses(
        binary_response_doc(PDF_MEDIA_TYPE),
        not_found_response(description="Annual report not found"),
    ),
)
def export_annual_report_pdf(
    report_id: PathId, db: DBSession, user: CurrentUser
) -> StreamingResponse:
    """Download a working-draft PDF (טיוטה לעיון) for the annual report."""
    svc = AnnualReportPdfService(db)
    pdf_bytes, tax_year = svc.generate(report_id)
    filename = f"annual_report_{report_id}_{tax_year}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type=PDF_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
