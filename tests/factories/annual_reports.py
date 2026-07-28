from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.annual_reports.annual_report_constants import FORM_MAP
from app.annual_reports.models.annual_report_enums import (
    ClientAnnualFilingType,
    ExtensionReason,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_enums import (
    SubmissionMethod as AnnualReportSubmissionMethod,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.common.enums import (
    ObligationStatus,
    ObligationType,
)
from app.users.models.user import User
from tests.helpers.factory_utils import (
    TEST_TAX_YEAR,
    ClientRef,
    resolve_exclusive,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory
    from tests.factories.tax_calendar import TaxCalendarEntryFactory


class AnnualReportServiceFactory:
    def __init__(self, db: Session, client_factory: ClientFactory, actor_user: User) -> None:
        self.db = db
        self.client_factory = client_factory
        self.actor_user = actor_user

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        client_full_name: str | None = None,
        client_id_number: str | None = None,
        actor: User | None = None,
        created_by: int | None = None,
        created_by_name: str | None = None,
        tax_year: int = TEST_TAX_YEAR,
        client_type: str = "corporation",
        deadline_type: str = "standard",
        **report_fields: Any,
    ):
        if client is not None and client_record_id is not None:
            raise ValueError("Pass either client or client_record_id, not both")
        if client is None and client_record_id is None:
            client = self.client_factory(
                full_name=client_full_name,
                id_number=client_id_number,
            )
        if client_record_id is None and client is None:
            raise ValueError("A client or client_record_id is required")
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        if actor is not None:
            resolved_actor_id = actor.id
            resolved_actor_name = created_by_name or actor.full_name
        elif created_by is not None:
            resolved_actor_id = created_by
            resolved_actor_name = created_by_name or "Test Actor"
        else:
            actor = self.actor_user
            resolved_actor_id = actor.id
            resolved_actor_name = created_by_name or actor.full_name
        return AnnualReportService(self.db).create_report(
            client_record_id=resolved_client_id,
            tax_year=tax_year,
            client_type=client_type,
            created_by=resolved_actor_id,
            created_by_name=resolved_actor_name,
            deadline_type=deadline_type,
            **report_fields,
        )


class AnnualReportRowFactory:
    """Model-level AnnualReport factory: no AnnualReportService side effects (audit/timeline).

    Builds the row directly, so callers get full control over status, form_type,
    filing_deadline, refund_due, and tax_due instead of the service's computed defaults.
    """

    def __init__(
        self,
        db: Session,
        client_factory: ClientFactory,
        tax_calendar_entry_factory: TaxCalendarEntryFactory,
        actor_user: User,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.tax_calendar_entry_factory = tax_calendar_entry_factory
        self.actor_user = actor_user

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        created_by: int | None = None,
        assigned_to: int | None = None,
        tax_year: int = TEST_TAX_YEAR,
        client_type: ClientAnnualFilingType = ClientAnnualFilingType.CORPORATION,
        form_type: PrimaryAnnualReportForm | None = None,
        status: ObligationStatus = ObligationStatus.AWAITING_INPUT,
        deadline_type: FilingDeadlineType = FilingDeadlineType.STANDARD,
        filing_deadline: datetime | None = None,
        custom_deadline_note: str | None = None,
        submitted_at: datetime | None = None,
        ita_reference: str | None = None,
        assessment_amount: Decimal | int | str | None = None,
        refund_due: Decimal | int | str | None = None,
        tax_due: Decimal | int | str | None = None,
        has_rental_income: bool = False,
        has_capital_gains: bool = False,
        has_foreign_income: bool = False,
        has_depreciation: bool = False,
        has_exempt_rental: bool = False,
        submission_method: AnnualReportSubmissionMethod | None = None,
        extension_reason: ExtensionReason | None = None,
        tax_calendar_entry_id: int | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> AnnualReport:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        if client is None and client_record_id is None:
            client = self.client_factory()
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        if created_by is None:
            created_by = self.actor_user.id
        if tax_calendar_entry_id is None:
            entry = self.tax_calendar_entry_factory(
                obligation_type=ObligationType.ANNUAL_REPORT,
                tax_year=tax_year,
            )
            tax_calendar_entry_id = entry.id
        report_fields: dict[str, Any] = {
            "client_record_id": resolved_client_id,
            "created_by": created_by,
            "assigned_to": assigned_to,
            "tax_year": tax_year,
            "client_type": client_type,
            "form_type": form_type or FORM_MAP[client_type],
            "status": status,
            "deadline_type": deadline_type,
            "filing_deadline": filing_deadline,
            "custom_deadline_note": custom_deadline_note,
            "submitted_at": submitted_at,
            "ita_reference": ita_reference,
            "assessment_amount": (
                None if assessment_amount is None else Decimal(str(assessment_amount))
            ),
            "refund_due": None if refund_due is None else Decimal(str(refund_due)),
            "tax_due": None if tax_due is None else Decimal(str(tax_due)),
            "has_rental_income": has_rental_income,
            "has_capital_gains": has_capital_gains,
            "has_foreign_income": has_foreign_income,
            "has_depreciation": has_depreciation,
            "has_exempt_rental": has_exempt_rental,
            "submission_method": submission_method,
            "extension_reason": extension_reason,
            "tax_calendar_entry_id": tax_calendar_entry_id,
            "notes": notes,
            "updated_at": updated_at,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
        }
        if created_at is not None:
            report_fields["created_at"] = created_at
        report = AnnualReport(**report_fields)
        self.db.add(report)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(report)
        return report
