from datetime import datetime

from app.annual_reports.models.annual_report_enums import FilingDeadlineType, SubmissionMethod
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.schemas.annual_report_responses import (
    AnnualReportResponse,
)
from app.annual_reports.services.annual_report_readiness_service import (
    AnnualReportReadinessService,
)
from app.audit.audit_constants import (
    ACTION_ANNUAL_REPORT_DEADLINE_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import ObligationStatus
from app.common.obligation_lifecycle import (
    assert_transition_allowed,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.utils.time_utils import utcnow

from ..annual_report_deadlines import extended_deadline, standard_deadline
from ..annual_report_messages import (
    ANNUAL_REPORT_NOT_FOUND,
    CUSTOM_DEADLINE_LABEL,
    DEADLINE_UPDATED_NOTE,
    INVALID_ANNUAL_REPORT_STATUS,
    INVALID_DEADLINE_TYPE_ERROR,
    REENTER_PENDING_CLIENT_CANCEL_SIGNATURE_REASON,
    REPORT_NOT_READY_FOR_SUBMISSION,
    STATUS_CHANGE_CANCEL_SIGNATURE_REASON,
)
from ..annual_report_status_signature_helper import AnnualReportSignatureHelper


def _deadline_note(deadline_type, filing_deadline, custom_deadline_note):
    note = DEADLINE_UPDATED_NOTE.format(
        deadline_type=deadline_type.value,
        filing_deadline=filing_deadline.strftime("%d/%m/%Y")
        if filing_deadline
        else CUSTOM_DEADLINE_LABEL,
    )
    return note + (f" — {custom_deadline_note}" if custom_deadline_note else "")


def _deadline_snapshot(report):
    return {
        "deadline_type": report.deadline_type.value
        if hasattr(report.deadline_type, "value")
        else report.deadline_type,
        "filing_deadline": report.filing_deadline,
        "custom_deadline_note": report.custom_deadline_note,
    }


class AnnualReportStatusService(AnnualReportSignatureHelper):
    def _get_or_raise_for_update(self, report_id: int) -> AnnualReport:
        """Fetch annual report with a row-level lock for status transitions."""
        report = self.repo.get_by_id_for_update(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )
        return report

    def _assert_filing_readiness(self, report_id: int) -> None:
        """Raise AppError listing all blocking issues before SUBMITTED transition."""
        svc = AnnualReportReadinessService(self.db)
        result = svc.get_readiness_check(report_id)
        if not result.is_ready:
            issues_str = "; ".join(result.issues)
            raise AppError(
                REPORT_NOT_READY_FOR_SUBMISSION.format(issues=issues_str),
                ErrorCode.ANNUAL_REPORT_INVALID_STATUS,
            )

    def transition_status(
        self,
        report_id: int,
        new_status: str,
        changed_by: int | None,
        changed_by_name: str,
        note: str | None = None,
        ita_reference: str | None = None,
        assessment_amount: float | None = None,
        refund_due: float | None = None,
        tax_due: float | None = None,
        submitted_at: datetime | None = None,
        submission_method: str | None = None,
        actor_type: str = "user",
    ) -> AnnualReportResponse:
        report = self._get_or_raise_for_update(report_id)
        valid_statuses = {e.value for e in ObligationStatus}
        if new_status not in valid_statuses:
            raise AppError(
                INVALID_ANNUAL_REPORT_STATUS.format(new_status=new_status),
                ErrorCode.ANNUAL_REPORT_INVALID_STATUS,
            )
        ns = ObligationStatus(new_status)

        # The shared graph owns this rule now, and raises OBLIGATION.* codes.
        assert_transition_allowed(report.status, ns, reason=note)

        if ns == ObligationStatus.SUBMITTED:
            self._assert_filing_readiness(report_id)

        client_record_for_signature = None
        if ns == ObligationStatus.AWAITING_VERIFICATION:
            client_record_for_signature = self._get_signature_client_context(report)

        update_fields: dict = {"status": ns}

        if ns == ObligationStatus.SUBMITTED:
            update_fields["submitted_at"] = submitted_at or utcnow()
            if ita_reference:
                update_fields["ita_reference"] = ita_reference
            if submission_method:
                sm = SubmissionMethod(submission_method)
                update_fields["submission_method"] = sm
                if report.deadline_type == FilingDeadlineType.STANDARD:
                    update_fields["filing_deadline"] = standard_deadline(
                        report.tax_year,
                        client_type=report.client_type,
                        submission_method=sm,
                    )
            # Assessment and tax outcome used to be recorded on a separate `closed`
            # status that followed `submitted`. The two were one act, so they merged.
            if assessment_amount is not None:
                update_fields["assessment_amount"] = assessment_amount
            if refund_due is not None:
                update_fields["refund_due"] = refund_due
            if tax_due is not None:
                update_fields["tax_due"] = tax_due

        old_status = report.status
        updated = self.repo.update(report_id, report=report, **update_fields)

        EntityAuditWriter(self.db).record_status_change(
            ENTITY_ANNUAL_REPORT,
            report_id,
            changed_by,
            old_status,
            ns,
            note=note,
            actor_type=actor_type,
            actor_display_name=changed_by_name,
            metadata_json={
                "client_record_id": report.client_record_id,
                "tax_year": report.tax_year,
            },
        )

        if (
            old_status == ObligationStatus.AWAITING_VERIFICATION
            and ns != ObligationStatus.AWAITING_VERIFICATION
        ):
            self._cancel_pending_signature_requests(
                report_id,
                changed_by,
                changed_by_name,
                STATUS_CHANGE_CANCEL_SIGNATURE_REASON,
                actor_type=actor_type,
            )

        if ns == ObligationStatus.AWAITING_VERIFICATION:
            if changed_by is None:
                raise AppError(
                    "יצירת בקשת חתימה לדוח שנתי דורשת משתמש מבצע",
                    ErrorCode.ANNUAL_REPORT_INVALID_STATUS,
                )
            self._cancel_pending_signature_requests(
                report_id,
                changed_by,
                changed_by_name,
                REENTER_PENDING_CLIENT_CANCEL_SIGNATURE_REASON,
            )
            assert client_record_for_signature is not None
            self._trigger_signature_request(
                updated, changed_by, changed_by_name, client_record_for_signature
            )

        return self._to_responses([updated])[0]

    def update_deadline(
        self,
        report_id: int,
        deadline_type: str | None,
        changed_by: int,
        changed_by_name: str,
        custom_deadline_note: str | None = None,
        custom_deadline_note_provided: bool = True,
    ) -> AnnualReportResponse:
        updated = self._update_deadline(
            report_id,
            deadline_type,
            changed_by,
            custom_deadline_note,
            custom_deadline_note_provided,
            changed_by_name=changed_by_name,
        )
        return self._to_responses([updated])[0]

    def _update_deadline(
        self,
        report_id: int,
        deadline_type: str | None,
        changed_by: int,
        custom_deadline_note=None,
        custom_deadline_note_provided: bool = True,
        changed_by_name: str | None = None,
    ):
        report = self._get_or_raise_for_update(report_id)
        old_value = _deadline_snapshot(report)
        # Partial update: when deadline_type is omitted, keep the existing type
        # (only custom_deadline_note is being changed).
        if deadline_type is None:
            dt = report.deadline_type
            if not isinstance(dt, FilingDeadlineType):
                dt = FilingDeadlineType(dt)
        else:
            valid_deadline_types = {e.value for e in FilingDeadlineType}
            if deadline_type not in valid_deadline_types:
                raise AppError(
                    INVALID_DEADLINE_TYPE_ERROR.format(deadline_type=deadline_type),
                    ErrorCode.ANNUAL_REPORT_INVALID_TYPE,
                )
            dt = FilingDeadlineType(deadline_type)
        # When the client did not send custom_deadline_note, preserve the
        # current value instead of clearing it.
        if not custom_deadline_note_provided:
            custom_deadline_note = report.custom_deadline_note
        if dt == FilingDeadlineType.STANDARD:
            filing_deadline = standard_deadline(
                report.tax_year,
                client_type=report.client_type,
                submission_method=report.submission_method,
            )
        elif dt == FilingDeadlineType.EXTENDED:
            filing_deadline = extended_deadline(report.tax_year)
        else:
            filing_deadline = None
        updated = self.repo.update(
            report_id,
            report=report,
            deadline_type=dt,
            filing_deadline=filing_deadline,
            custom_deadline_note=custom_deadline_note,
        )
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=changed_by,
            action=ACTION_ANNUAL_REPORT_DEADLINE_UPDATED,
            old_value=old_value,
            new_value=_deadline_snapshot(updated),
            actor_display_name=changed_by_name,
            metadata_json={
                "client_record_id": updated.client_record_id,
                "tax_year": updated.tax_year,
            },
        )
        return updated


