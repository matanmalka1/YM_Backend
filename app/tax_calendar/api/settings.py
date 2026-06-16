from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.openapi_responses import bad_request_response, conflict_response, error_responses
from app.tax_calendar.schemas.settings import (
    DeadlineRuleResponse,
    TaxCalendarBootstrapRequest,
    TaxCalendarBootstrapResponse,
    TaxCalendarEntryResponse,
    TaxCalendarSummaryResponse,
)
from app.tax_calendar.services import settings_calendar_service
from app.users.api.deps import DBSession, require_role
from app.users.models.user import UserRole
from app.utils.time_utils import israel_today

router = APIRouter(prefix="/settings/tax-calendar", tags=["settings-tax-calendar"])


def _check_year_range(tax_year_after: int | None, tax_year_before: int | None) -> None:
    if (
        tax_year_after is not None
        and tax_year_before is not None
        and tax_year_after > tax_year_before
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="שנת ההתחלה חייבת להיות קטנה או שווה לשנת הסיום.",
        )


@router.get(
    "/rules",
    response_model=list[DeadlineRuleResponse],
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def list_deadline_rules(db: DBSession) -> list[DeadlineRuleResponse]:
    """Unpaginated by design. Returns all deadline-rule config rows.

    No cap: bounded by the (small, admin-managed) number of configured rules.
    """
    return settings_calendar_service.list_rules(db)


@router.get(
    "/entries",
    response_model=list[TaxCalendarEntryResponse],
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def list_tax_calendar_entries(
    db: DBSession,
    tax_year_after: int | None = Query(None),
    tax_year_before: int | None = Query(None),
) -> list[TaxCalendarEntryResponse]:
    current_year = israel_today().year
    resolved_start = tax_year_after if tax_year_after is not None else current_year
    resolved_end = tax_year_before if tax_year_before is not None else current_year + 1
    _check_year_range(resolved_start, resolved_end)
    return settings_calendar_service.list_entries(
        db, tax_year_after=resolved_start, tax_year_before=resolved_end
    )


@router.get(
    "/summary",
    response_model=TaxCalendarSummaryResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def get_tax_calendar_summary(
    db: DBSession,
    tax_year_after: int | None = Query(None),
    tax_year_before: int | None = Query(None),
) -> TaxCalendarSummaryResponse:
    _check_year_range(tax_year_after, tax_year_before)
    return settings_calendar_service.get_summary(
        db, tax_year_after=tax_year_after, tax_year_before=tax_year_before
    )


@router.post(
    "/bootstrap",
    response_model=TaxCalendarBootstrapResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=error_responses(
        bad_request_response(description="טווח השנים אינו תקין"),
        conflict_response(description="רשומת יומן המס מתנגשת עם חובה קיימת"),
    ),
)
def bootstrap_tax_calendar_settings(
    request: TaxCalendarBootstrapRequest,
    db: DBSession,
) -> TaxCalendarBootstrapResponse:
    _check_year_range(request.tax_year_after, request.tax_year_before)
    return settings_calendar_service.bootstrap_calendar(
        db, tax_year_after=request.tax_year_after, tax_year_before=request.tax_year_before
    )
