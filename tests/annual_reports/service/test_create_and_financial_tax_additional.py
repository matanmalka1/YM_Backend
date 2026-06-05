from decimal import Decimal

import pytest

from app.annual_reports.models.annual_report_credit_point_reason import (
    AnnualReportCreditPoint,
    CreditPointReason,
)
from app.annual_reports.models.annual_report_enums import (
    AnnualReportSchedule,
    AnnualReportStatus,
)
from app.annual_reports.repositories.annual_report_repository import AnnualReportRepository
from app.annual_reports.repositories.detail_repository import AnnualReportDetailRepository
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.annual_reports.services.financial_line_service import AnnualReportFinancialLineService
from app.annual_reports.services.financial_summary_service import (
    AnnualReportFinancialSummaryService,
)
from app.annual_reports.services.readiness_service import AnnualReportReadinessService
from app.annual_reports.services.tax_service import AnnualReportTaxService
from app.core.exceptions import AppError, ConflictError, NotFoundError
from tests.helpers.identity import seed_client_identity


def _client(db, suffix="1"):
    return seed_client_identity(
        db, full_name=f"AR create extra {suffix}", id_number=f"ARCE{suffix}"
    )


def test_create_report_validation_errors(test_db):
    c = _client(test_db, "A")
    service = AnnualReportService(test_db)

    with pytest.raises(AppError):
        service.create_report(c.id, 2026, "bad", 1, "A")
    with pytest.raises(AppError):
        service.create_report(c.id, 2026, "corporation", 1, "A", deadline_type="bad")

    service.create_report(c.id, 2026, "corporation", 1, "A")
    with pytest.raises(ConflictError):
        service.create_report(c.id, 2026, "corporation", 1, "A")


def test_create_report_custom_deadline_and_assigned_to_validation(test_db):
    c = _client(test_db, "B")
    service = AnnualReportService(test_db)
    report = service.create_report(
        client_record_id=c.id,
        tax_year=2025,
        client_type="corporation",
        created_by=1,
        created_by_name="A",
        deadline_type="custom",
    )
    assert report.filing_deadline is None

    with pytest.raises(NotFoundError):
        service.create_report(
            client_record_id=c.id,
            tax_year=2024,
            client_type="corporation",
            created_by=1,
            created_by_name="A",
            assigned_to=999999,
        )


def test_readiness_incomplete_required_schedule_issue_present(test_db):
    c = _client(test_db, "C")
    service = AnnualReportService(test_db)
    readiness_service = AnnualReportReadinessService(test_db)
    report = service.create_report(c.id, 2026, "corporation", 1, "A", has_rental_income=True)

    # required schedule exists and incomplete -> explicit issue
    readiness = readiness_service.get_readiness_check(report.id)
    assert any("נספח נדרש לא הושלם" in issue for issue in readiness.issues)
    assert readiness.is_ready is False


def test_tax_calculation_uses_detail_credit_components(monkeypatch, test_db):
    c = _client(test_db, "D")
    service = AnnualReportService(test_db)
    line_service = AnnualReportFinancialLineService(test_db)
    tax_service = AnnualReportTaxService(test_db)
    report = service.create_report(c.id, 2026, "corporation", 1, "A")

    # ensure summary has taxable income
    line_service.add_income(report.id, "salary", 1000)
    AnnualReportDetailRepository(test_db).update_meta(
        report.id,
        pension_contribution=100.0,
        donation_amount=50.0,
        other_credits=20.0,
    )
    test_db.add_all(
        [
            AnnualReportCreditPoint(
                annual_report_id=report.id,
                reason=CreditPointReason.RESIDENT,
                points=2.0,
            ),
            AnnualReportCreditPoint(
                annual_report_id=report.id,
                reason=CreditPointReason.ACADEMIC_DEGREE,
                points=1.0,
            ),
        ]
    )
    test_db.flush()

    monkeypatch.setattr(
        tax_service.vat_repo,
        "sum_net_vat_by_client_record_year",
        lambda *args, **kwargs: 0.0,
    )
    monkeypatch.setattr(
        tax_service.advance_repo, "sum_paid_by_client_year", lambda *args, **kwargs: 0.0
    )
    out = tax_service.get_tax_calculation(report.id)
    assert out.total_credit_points == 3.0


def test_income_line_allows_zero_amount(test_db):
    c = _client(test_db, "E")
    service = AnnualReportService(test_db)
    line_service = AnnualReportFinancialLineService(test_db)
    summary_service = AnnualReportFinancialSummaryService(test_db)
    report = service.create_report(c.id, 2026, "corporation", 1, "A")

    line = line_service.add_income(report.id, "salary", 0)

    assert float(line.amount) == 0.0
    summary = summary_service.get_financial_summary(report.id)
    assert float(summary.total_income) == 0.0


def test_expense_line_uses_external_document_reference(test_db):
    c = _client(test_db, "F")
    service = AnnualReportService(test_db)
    line_service = AnnualReportFinancialLineService(test_db)
    report = service.create_report(c.id, 2026, "corporation", 1, "A")

    line = line_service.add_expense(
        report.id,
        "office_rent",
        250,
        external_document_reference="INV-2026-001",
    )

    assert line.external_document_reference == "INV-2026-001"
    assert line.supporting_document_id is None


def _prepare_financial_mutation(line_service, report_id: int, mutation: str):
    if mutation == "add_income":
        return lambda: line_service.add_income(report_id, "salary", Decimal("100.00"))
    if mutation == "update_income":
        line = line_service.add_income(report_id, "salary", Decimal("100.00"))
        return lambda: line_service.update_income(report_id, line.id, amount=Decimal("125.00"))
    if mutation == "delete_income":
        line = line_service.add_income(report_id, "salary", Decimal("100.00"))
        return lambda: line_service.delete_income(report_id, line.id)
    if mutation == "add_expense":
        return lambda: line_service.add_expense(report_id, "office_rent", Decimal("100.00"))
    if mutation == "update_expense":
        line = line_service.add_expense(report_id, "office_rent", Decimal("100.00"))
        return lambda: line_service.update_expense(report_id, line.id, amount=Decimal("125.00"))
    if mutation == "delete_expense":
        line = line_service.add_expense(report_id, "office_rent", Decimal("100.00"))
        return lambda: line_service.delete_expense(report_id, line.id)
    raise AssertionError(f"Unhandled mutation {mutation}")


@pytest.mark.parametrize(
    "mutation",
    [
        "add_income",
        "update_income",
        "delete_income",
        "add_expense",
        "update_expense",
        "delete_expense",
    ],
)
def test_financial_line_mutations_clear_saved_tax_for_pre_submission_report(test_db, mutation):
    c = _client(test_db, f"INV{mutation}")
    report = AnnualReportService(test_db).create_report(c.id, 2026, "corporation", 1, "A")
    line_service = AnnualReportFinancialLineService(test_db)
    tax_service = AnnualReportTaxService(test_db)
    mutate = _prepare_financial_mutation(line_service, report.id, mutation)

    tax_service.save_tax_calculation(report.id, Decimal("100.00"), None)
    test_db.refresh(report)
    assert report.tax_due == Decimal("100.00")

    mutate()

    test_db.refresh(report)
    assert report.tax_due is None
    assert report.refund_due is None


def test_financial_line_mutation_does_not_clear_saved_tax_for_submitted_report(test_db):
    c = _client(test_db, "SUBMITTED-TAX")
    report = AnnualReportService(test_db).create_report(c.id, 2026, "corporation", 1, "A")
    AnnualReportRepository(test_db).update(
        report.id,
        status=AnnualReportStatus.SUBMITTED,
        tax_due=Decimal("100.00"),
    )
    test_db.refresh(report)

    AnnualReportFinancialLineService(test_db).add_income(report.id, "salary", Decimal("100.00"))

    test_db.refresh(report)
    assert report.status == AnnualReportStatus.SUBMITTED
    assert report.tax_due == Decimal("100.00")
    assert report.refund_due is None


def test_annex_line_creates_schedule_owner_when_missing(test_db):
    c = _client(test_db, "G")
    service = AnnualReportService(test_db)
    report = service.create_report(c.id, 2026, "corporation", 1, "A")

    assert service.get_annex_lines(report.id, AnnualReportSchedule.SCHEDULE_B) == []

    line = service.add_annex_line(
        report.id,
        AnnualReportSchedule.SCHEDULE_B,
        {"rental_income": 12000},
        notes="auto owner",
    )

    assert line.schedule == AnnualReportSchedule.SCHEDULE_B
    assert line.annual_report_id == report.id
    schedules = service.get_schedules(report.id)
    assert any(
        entry.schedule == AnnualReportSchedule.SCHEDULE_B and entry.is_required is False
        for entry in schedules
    )
