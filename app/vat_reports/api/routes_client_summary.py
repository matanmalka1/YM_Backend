"""Routes: client-level VAT summary and export."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.users.api.deps import DBSession, require_role
from app.users.models.user import UserRole
from app.vat_reports.schemas.vat_client_summary_schema import VatClientSummaryResponse
from app.vat_reports.services.vat_client_summary_service import get_client_summary
from app.vat_reports.services.vat_export_service import export

router = APIRouter(
    prefix="/vat",
    tags=["vat-reports"],
)


@router.get(
    "/clients/{client_record_id}/summary",
    response_model=VatClientSummaryResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def get_vat_client_summary(
    client_record_id: int,
    db: DBSession,
    from_year: int | None = Query(default=None, ge=2000, le=2100),
    to_year: int | None = Query(default=None, ge=2000, le=2100),
):
    return get_client_summary(
        db, client_record_id=client_record_id, from_year=from_year, to_year=to_year
    )


@router.get(
    "/clients/{client_record_id}/export",
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
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
