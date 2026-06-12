"""Routes: client-level VAT summary and export."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.openapi_responses import not_found_response
from app.users.api.deps import DBSession, require_role
from app.users.models.user import UserRole
from app.utils.time_utils import israel_today
from app.vat.schemas.vat_client_summary_schema import VatClientSummaryResponse
from app.vat.services.vat_client_summary_service import get_client_summary
from app.vat.services.vat_export_service import export

router = APIRouter(
    prefix="/vat",
    tags=["vat-reports"],
)

_DEFAULT_YEAR_WINDOW = 4


@router.get(
    "/clients/{client_record_id}/summary",
    response_model=VatClientSummaryResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_vat_client_summary(
    client_record_id: int,
    db: DBSession,
    period_year_after: int | None = Query(default=None, ge=2000, le=2100),
    period_year_before: int | None = Query(default=None, ge=2000, le=2100),
):
    current_year = israel_today().year
    resolved_to = period_year_before if period_year_before is not None else current_year
    resolved_from = (
        period_year_after if period_year_after is not None else current_year - _DEFAULT_YEAR_WINDOW
    )
    return get_client_summary(
        db,
        client_record_id=client_record_id,
        period_year_after=resolved_from,
        period_year_before=resolved_to,
    )


@router.get(
    "/clients/{client_record_id}/export",
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def export_vat_client(
    client_record_id: int,
    db: DBSession,
    format: str = Query(..., pattern="^(excel|pdf)$"),
    year: int = Query(..., ge=2000, le=2100),
):
    result, media_type = export(db, client_record_id, year, fmt=format)
    return FileResponse(
        path=result["filepath"],
        media_type=media_type,
        filename=result["filename"],
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )
