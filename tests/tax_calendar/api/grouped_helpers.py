from datetime import date, datetime

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    ClientAnnualFilingType,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.common.enums import DeadlineRuleType, ObligationType, VatType
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from tests.tax_calendar.service.linking_helpers import (
    advance_client,
    annual_client,
    make_entry,
    vat_client,
)

PATH = "/api/v1/tax-calendar/groups"


def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def vat_entry(db, year: int = 2026):
    return make_entry(
        db,
        obligation_type=ObligationType.VAT,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        period=f"{year}-01",
        months=1,
        tax_year=year,
    )


def advance_entry(db, year: int = 2026):
    return make_entry(
        db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        period=f"{year}-01",
        months=1,
        tax_year=year,
    )


def annual_entry(db, year: int = 2026):
    return make_entry(
        db,
        obligation_type=ObligationType.ANNUAL_REPORT,
        rule_type=DeadlineRuleType.ANNUAL_REPORT,
        period=None,
        months=None,
        tax_year=year,
    )


def add_vat_item(db, entry, user_id: int, *, due_date=date(2026, 2, 20)):
    client_record = vat_client(db, VatType.MONTHLY)
    item = VatWorkItem(
        client_record_id=client_record.id,
        created_by=user_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        status=VatWorkItemStatus.MATERIAL_RECEIVED,
        tax_calendar_entry_id=entry.id,
        due_date_original=entry.due_date,
        due_date_effective=due_date,
        due_date_override_reason="דחיית מועד",
    )
    db.add(item)
    db.flush()
    return item


def add_advance_payment(
    db,
    entry,
    *,
    due_date=date(2026, 2, 21),
    status=AdvancePaymentStatus.PENDING,
):
    client_record = advance_client(db)
    payment = AdvancePayment(
        client_record_id=client_record.id,
        period="2026-01",
        period_months_count=1,
        due_date=entry.due_date,
        due_date_original=entry.due_date,
        due_date_effective=due_date,
        due_date_override_reason="דחיית מועד",
        status=status,
        tax_calendar_entry_id=entry.id,
    )
    db.add(payment)
    db.flush()
    return payment


def add_annual_report(db, entry):
    client_record = annual_client(db)
    report = AnnualReport(
        client_record_id=client_record.id,
        tax_year=2026,
        client_type=ClientAnnualFilingType.SELF_EMPLOYED,
        form_type=PrimaryAnnualReportForm.FORM_1301,
        status=AnnualReportStatus.NOT_STARTED,
        deadline_type=FilingDeadlineType.STANDARD,
        filing_deadline=datetime(2027, 7, 31, 10, 0),
        tax_calendar_entry_id=entry.id,
    )
    db.add(report)
    db.flush()
    return report
