from fastapi import APIRouter, Depends, Query

from app.businesses.schemas.business_status_card import ClientStatusCardResponse
from app.businesses.services.status_card_service import StatusCardService
from app.core.openapi_responses import not_found_response
from app.core.path_params import PathId
from app.users.api.deps import DBSession, require_role
from app.users.models.user import UserRole

_YEAR_MIN = 2000
_YEAR_MAX = 2100

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{client_record_id}/status-card",
    response_model=ClientStatusCardResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_client_status_card(
    client_record_id: PathId,
    db: DBSession,
    year: int | None = Query(None, ge=_YEAR_MIN, le=_YEAR_MAX),
):
    """Comprehensive status card for a client — VAT, annual report, charges, advances, binders, documents."""
    return StatusCardService(db).get_status_card(client_record_id, year=year)
