import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_enums import ClientAnnualFilingType
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.clients.constants import (
    CLIENT_OBLIGATION_NEXT_YEAR_START_MONTH,
    CLIENT_OBLIGATION_TRIGGER_FIELDS,
    ENTITY_TYPE_TO_REPORT_CLIENT_TYPE,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import EntityType
from app.core.exceptions import ConflictError, NotFoundError

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class ObligationResult:
    reports_created: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_created(self) -> int:
        return self.reports_created


def _years_to_generate(reference_date: date | None = None) -> list[int]:
    if not 2 <= CLIENT_OBLIGATION_NEXT_YEAR_START_MONTH <= 12:
        raise ValueError("CLIENT_OBLIGATION_NEXT_YEAR_START_MONTH must be between 2 and 12")
    today = reference_date or date.today()
    years = [today.year]
    if today.month >= CLIENT_OBLIGATION_NEXT_YEAR_START_MONTH:
        years.append(today.year + 1)
    return years


def _derive_client_type(entity_type: EntityType | None) -> ClientAnnualFilingType:
    if entity_type is None or entity_type not in ENTITY_TYPE_TO_REPORT_CLIENT_TYPE:
        raise ValueError("סוג ישות לא נתמך ליצירת דוח שנתי")
    return ENTITY_TYPE_TO_REPORT_CLIENT_TYPE[entity_type]


def generate_client_obligations(
    db: Session,
    client_record_id: int,
    actor_id: int | None = None,
    actor_name: str | None = None,
    entity_type: EntityType | None = None,
    reference_date: date | None = None,
    best_effort: bool = False,
) -> int:
    return generate_client_obligations_result(
        db=db,
        client_record_id=client_record_id,
        actor_id=actor_id,
        actor_name=actor_name,
        entity_type=entity_type,
        reference_date=reference_date,
        best_effort=best_effort,
    ).total_created


def generate_client_obligations_result(
    db: Session,
    client_record_id: int,
    actor_id: int | None = None,
    actor_name: str | None = None,
    entity_type: EntityType | None = None,
    reference_date: date | None = None,
    best_effort: bool = False,
) -> ObligationResult:
    """
    Creating tax periods and annual reports for the client for the current year (and for the next year in the fourth quarter).
    Idempotent action — existing periods and reports are skipped.
    Returns creation details by periods/reports and a list of errors.

    best_effort=False (default — for use in creation flows):
    Errors are raised immediately after a rollback of the savepoint.
    The failure propagates upwards, get_db() performs a rollback for the main transaction — no data is saved.

    best_effort=True — for use in update flows:
    Errors are recorded in the log, the savepoint is rolled back, and the function returns.
    The main transaction is preserved — the updating entity is already flushed and a commit will be performed at the end of the request.

    Important: In best_effort=True this is an intentional partial-success design.
    Tax periods and annual reports are created in two separate stages, and each year is saved in an independent savepoint.
    Therefore, a situation may occur where some periods were created without a matching annual report, or vice versa, if another stage failed.
    """
    years = _years_to_generate(reference_date)
    result = ObligationResult()
    if not ClientRecordRepository(db).get_by_id(client_record_id):
        if best_effort:
            return result
        raise NotFoundError(
            f"רשומת לקוח עבור מזהה {client_record_id} לא נמצאה",
            "CLIENT_RECORD.NOT_FOUND",
        )

    client_type = _derive_client_type(entity_type).value
    report_service = AnnualReportService(db)
    _actor_name = actor_name or ""
    # Intentional partial-success boundary: annual reports are isolated from deadline savepoints.
    for year in years:
        sp = db.begin_nested()  # SAVEPOINT
        try:
            report_service.create_report(
                client_record_id=client_record_id,
                tax_year=year,
                client_type=client_type,
                created_by=actor_id,
                created_by_name=_actor_name,
            )
            result.reports_created += 1
            sp.commit()  # RELEASE SAVEPOINT
        except ConflictError:
            sp.rollback()  # דוח קיים — מדלגים; חייבים לסיים את ה-savepoint
        except Exception:
            sp.rollback()  # ROLLBACK TO SAVEPOINT בלבד
            _log.exception("שגיאה ביצירת דוח שנתי ללקוח %s שנה %s", client_record_id, year)
            if not best_effort:
                raise
            result.errors.append(f"annual_report_creation_failed:{year}")

    return result


def obligation_fields_changed(fields: dict) -> bool:
    """Return True if any key in fields affects obligation generation."""
    return bool(CLIENT_OBLIGATION_TRIGGER_FIELDS.intersection(fields))
