from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    ClientAnnualFilingType,
    ExtensionReason,
    FilingDeadlineType,
    SubmissionMethod,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.audit.constants import ENTITY_ANNUAL_REPORT
from app.audit.services.entity_audit_writer import EntityAuditWriter
from app.clients.guards.client_record_guards import assert_client_record_is_active
from app.core.exceptions import AppError, ConflictError
from app.tax_calendar.services.materialization_service import (
    TaxCalendarMaterializationService,
)
from app.users.services.user_management_service import get_user_or_raise

from .base import AnnualReportBaseService
from .constants import FORM_MAP
from .deadlines import extended_deadline, standard_deadline
from .messages import (
    ANNUAL_REPORT_ALREADY_EXISTS,
    ANNUAL_REPORT_CLIENT_NOT_FOUND,
    ANNUAL_REPORT_CREATED_NOTE,
    DEADLINE_NOT_SET,
    INVALID_CLIENT_TYPE_ERROR,
    INVALID_DEADLINE_TYPE_ERROR,
)


class AnnualReportCreateService(AnnualReportBaseService):
    def create_report(
        self,
        client_record_id: int,
        tax_year: int,
        client_type: str,
        created_by: int,
        created_by_name: str,
        deadline_type: str = "standard",
        assigned_to: int | None = None,
        notes: str | None = None,
        submission_method: str | None = None,
        extension_reason: str | None = None,
        # Income flags for schedule auto-generation
        has_rental_income: bool = False,
        has_capital_gains: bool = False,
        has_foreign_income: bool = False,
        has_depreciation: bool = False,
        has_exempt_rental: bool = False,
    ) -> AnnualReport:
        """Create an annual report and initial schedules/status audit entry."""
        client_record = self.client_repo.get_by_id(client_record_id)
        if not client_record:
            from app.core.exceptions import NotFoundError

            raise NotFoundError(
                ANNUAL_REPORT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
                "ANNUAL_REPORT.CLIENT_NOT_FOUND",
            )
        assert_client_record_is_active(client_record)
        client_record_id = int(client_record.id)

        valid_client_types = {e.value for e in ClientAnnualFilingType}
        if client_type not in valid_client_types:
            raise AppError(
                INVALID_CLIENT_TYPE_ERROR.format(client_type=client_type),
                "ANNUAL_REPORT.INVALID_TYPE",
            )
        ct = ClientAnnualFilingType(client_type)

        valid_deadline_types = {e.value for e in FilingDeadlineType}
        if deadline_type not in valid_deadline_types:
            raise AppError(
                INVALID_DEADLINE_TYPE_ERROR.format(deadline_type=deadline_type),
                "ANNUAL_REPORT.INVALID_TYPE",
            )
        dt = FilingDeadlineType(deadline_type)

        if assigned_to is not None:
            get_user_or_raise(self.user_repo, assigned_to)

        existing = self.repo.get_by_client_record_year(client_record_id, tax_year)
        if existing:
            raise ConflictError(
                ANNUAL_REPORT_ALREADY_EXISTS.format(
                    client_record_id=client_record_id,
                    tax_year=tax_year,
                    existing_id=existing.id,
                    status=existing.status.value,
                ),
                "ANNUAL_REPORT.CONFLICT",
            )

        form_type = FORM_MAP[ct]
        if dt == FilingDeadlineType.STANDARD:
            filing_deadline = standard_deadline(
                tax_year,
                client_type=ct,
                submission_method=SubmissionMethod(submission_method)
                if submission_method
                else None,
            )
        elif dt == FilingDeadlineType.EXTENDED:
            filing_deadline = extended_deadline(tax_year)
        else:
            filing_deadline = None  # custom — caller can set note

        tax_calendar_entry = TaxCalendarMaterializationService(self.db).ensure_annual_entry(
            tax_year
        )
        report = self.repo.create(
            client_record_id=client_record_id,
            tax_year=tax_year,
            client_type=ct,
            form_type=form_type,
            created_by=created_by,
            assigned_to=assigned_to,
            status=AnnualReportStatus.NOT_STARTED,
            deadline_type=dt,
            filing_deadline=filing_deadline,
            tax_calendar_entry_id=tax_calendar_entry.id,
            notes=notes,
            submission_method=SubmissionMethod(submission_method) if submission_method else None,
            extension_reason=ExtensionReason(extension_reason) if extension_reason else None,
            has_rental_income=has_rental_income,
            has_capital_gains=has_capital_gains,
            has_foreign_income=has_foreign_income,
            has_depreciation=has_depreciation,
            has_exempt_rental=has_exempt_rental,
        )
        linked_report = TaxCalendarMaterializationService(self.db).link_annual_report(report)

        # Auto-generate required schedules
        self._generate_schedules(linked_report)

        self.repo.append_status_audit_entry(
            annual_report_id=linked_report.id,
            from_status=None,
            to_status=AnnualReportStatus.NOT_STARTED,
            changed_by=created_by,
            note=ANNUAL_REPORT_CREATED_NOTE.format(
                form_type=form_type.value,
                filing_deadline=filing_deadline.strftime("%d/%m/%Y")
                if filing_deadline
                else DEADLINE_NOT_SET,
            ),
        )

        EntityAuditWriter(self.db).record_create(
            ENTITY_ANNUAL_REPORT,
            linked_report.id,
            created_by,
            new_value={
                "tax_year": tax_year,
                "client_type": client_type,
                "client_record_id": client_record_id,
                "form_type": form_type,
            },
        )
        return linked_report
