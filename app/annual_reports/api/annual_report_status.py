from fastapi import APIRouter, Depends, Query

from app.annual_reports.api.responses import (
    REPORT_TRANSITION_RESPONSES,
    REPORT_UPDATE_RESPONSES,
)
from app.annual_reports.schemas.annual_report_requests import (
    DeadlineUpdateRequest,
    StatusTransitionRequest,
    SubmitRequest,
)
from app.annual_reports.schemas.annual_report_responses import (
    AnnualReportAuditListResponse,
    AnnualReportDetailResponse,
    AnnualReportResponse,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.core.openapi_responses import not_found_response
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate_sequence
from app.core.path_params import PathId
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.post(
    "/{report_id}/status",
    response_model=AnnualReportResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_TRANSITION_RESPONSES,
)
def transition_status(
    report_id: PathId,
    body: StatusTransitionRequest,
    db: DBSession,
    user: CurrentUser,
):
    """
    Move the report to a new status.

    Only valid transitions are accepted (e.g. COLLECTING_DOCS → IN_PREPARATION).
    Attempting an invalid jump returns 400.
    """
    service = AnnualReportService(db)
    report = service.transition_status(
        report_id=report_id,
        new_status=body.status,
        changed_by=user.id,
        changed_by_name=user.full_name,
        note=body.note,
        ita_reference=body.ita_reference,
        assessment_amount=float(body.assessment_amount) if body.assessment_amount else None,
        refund_due=float(body.refund_due) if body.refund_due else None,
        tax_due=float(body.tax_due) if body.tax_due else None,
    )
    return report


@router.post(
    "/{report_id}/submit",
    response_model=AnnualReportDetailResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_TRANSITION_RESPONSES,
)
def submit_report(
    report_id: PathId,
    body: SubmitRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = AnnualReportService(db)
    service.transition_status(
        report_id=report_id,
        new_status="submitted",
        changed_by=user.id,
        changed_by_name=user.full_name,
        note=body.note,
        ita_reference=body.ita_reference,
        submitted_at=body.submitted_at,
        submission_method=body.submission_method.value if body.submission_method else None,
    )
    detail = service.get_detail_report(report_id)
    if detail is None:
        raise NotFoundError(f"דוח שנתי {report_id} לא נמצא", ErrorCode.ANNUAL_REPORT_NOT_FOUND)
    return detail


@router.post(
    "/{report_id}/deadline",
    response_model=AnnualReportResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_UPDATE_RESPONSES,
)
def update_deadline(
    report_id: PathId,
    body: DeadlineUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    """
    Update the deadline type for a report.

    Switching to 'extended' moves the deadline to January 31 of the year
    after next — used for authorised electronic representatives (מייצגים).
    """
    service = AnnualReportService(db)
    patch = body.model_dump(exclude_unset=True)
    report = service.update_deadline(
        report_id=report_id,
        changed_by=user.id,
        changed_by_name=user.full_name,
        # deadline_type omitted => keep existing; custom_deadline_note only
        # applied when the client sent it (partial PATCH semantics).
        deadline_type=patch.get("deadline_type"),
        custom_deadline_note=patch.get("custom_deadline_note"),
        custom_deadline_note_provided="custom_deadline_note" in patch,
    )
    return report


@router.get(
    "/{report_id}/audit",
    response_model=AnnualReportAuditListResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def get_report_audit(
    report_id: PathId,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    service = AnnualReportService(db)
    all_audit_entries = service.get_report_audit(report_id)
    total = len(all_audit_entries)
    items = paginate_sequence(all_audit_entries, page, page_size)
    return AnnualReportAuditListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )
