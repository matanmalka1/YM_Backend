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
from app.annual_reports.repositories.annual_report_detail_repository import (
    AnnualReportDetailRepository,
)
from app.annual_reports.repositories.annual_report_repository import AnnualReportRepository
from app.annual_reports.services.annual_report_financial_line_service import (
    AnnualReportFinancialLineService,
)
from app.annual_reports.services.annual_report_financial_summary_service import (
    AnnualReportFinancialSummaryService,
)
from app.annual_reports.services.annual_report_readiness_service import AnnualReportReadinessService
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.annual_reports.services.annual_report_tax_service import AnnualReportTaxService
from app.core.exceptions import AppError, ConflictError, NotFoundError


def test_create_report_validation_errors(test_db, actor_user, client_factory):
    c = client_factory(full_name="AR create extra A", id_number="ARCEA")
    service = AnnualReportService(test_db)

    with pytest.raises(AppError):
        service.create_report(c.id, 2026, "bad", actor_user.id, actor_user.full_name)
    with pytest.raises(AppError):
        service.create_report(
            c.id,
            2026,
            "corporation",
            actor_user.id,
            actor_user.full_name,
            deadline_type="bad",
        )

    service.create_report(c.id, 2026, "corporation", actor_user.id, actor_user.full_name)
    with pytest.raises(ConflictError):
        service.create_report(c.id, 2026, "corporation", actor_user.id, actor_user.full_name)


def test_create_report_custom_deadline_and_assigned_to_validation(
    test_db, actor_user, client_factory
):
    c = client_factory(full_name="AR create extra B", id_number="ARCEB")
    service = AnnualReportService(test_db)
    report = service.create_report(
        client_record_id=c.id,
        tax_year=2025,
        client_type="corporation",
        created_by=actor_user.id,
        created_by_name=actor_user.full_name,
        deadline_type="custom",
    )
    assert report.filing_deadline is None

    with pytest.raises(NotFoundError):
        service.create_report(
            client_record_id=c.id,
            tax_year=2024,
            client_type="corporation",
            created_by=actor_user.id,
            created_by_name=actor_user.full_name,
            assigned_to=999999,  # deliberately absent: the assignee lookup must raise
        )


def test_readiness_incomplete_required_schedule_issue_present(test_db, actor_user, client_factory):
    c = client_factory(full_name="AR create extra C", id_number="ARCEC")
    service = AnnualReportService(test_db)
    readiness_service = AnnualReportReadinessService(test_db)
    report = service.create_report(
        c.id,
        2026,
        "corporation",
        actor_user.id,
        actor_user.full_name,
        has_rental_income=True,
    )

    # required schedule exists and incomplete -> explicit issue
    readiness = readiness_service.get_readiness_check(report.id)
    assert any("נספח נדרש לא הושלם" in issue for issue in readiness.issues)
    assert readiness.is_ready is False


def test_tax_calculation_uses_detail_credit_components(
    monkeypatch, test_db, actor_user, client_factory
):
    c = client_factory(full_name="AR create extra D", id_number="ARCED")
    service = AnnualReportService(test_db)
    line_service = AnnualReportFinancialLineService(test_db)
    tax_service = AnnualReportTaxService(test_db)
    report = service.create_report(c.id, 2026, "corporation", actor_user.id, actor_user.full_name)

    # ensure summary has taxable income
    line_service.add_income(report.id, "salary", 1000, actor_id=actor_user.id)
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
    assert out.total_credit_points == Decimal("3.0")


def test_income_line_allows_zero_amount(test_db, actor_user, client_factory):
    c = client_factory(full_name="AR create extra E", id_number="ARCEE")
    service = AnnualReportService(test_db)
    line_service = AnnualReportFinancialLineService(test_db)
    summary_service = AnnualReportFinancialSummaryService(test_db)
    report = service.create_report(c.id, 2026, "corporation", actor_user.id, actor_user.full_name)

    line = line_service.add_income(report.id, "salary", 0, actor_id=actor_user.id)

    assert float(line.amount) == 0.0
    summary = summary_service.get_financial_summary(report.id)
    assert float(summary.total_income) == 0.0


def test_expense_line_uses_external_document_reference(test_db, actor_user, client_factory):
    c = client_factory(full_name="AR create extra F", id_number="ARCEF")
    service = AnnualReportService(test_db)
    line_service = AnnualReportFinancialLineService(test_db)
    report = service.create_report(c.id, 2026, "corporation", actor_user.id, actor_user.full_name)

    line = line_service.add_expense(
        report.id,
        "office_rent",
        250,
        external_document_reference="INV-2026-001",
        actor_id=actor_user.id,
    )

    assert line.external_document_reference == "INV-2026-001"
    assert line.supporting_document_id is None


def _prepare_financial_mutation(line_service, report_id: int, mutation: str, actor_id: int):
    if mutation == "add_income":
        return lambda: line_service.add_income(
            report_id, "salary", Decimal("100.00"), actor_id=actor_id
        )
    if mutation == "update_income":
        line = line_service.add_income(report_id, "salary", Decimal("100.00"), actor_id=actor_id)
        return lambda: line_service.update_income(
            report_id, line.id, amount=Decimal("125.00"), actor_id=actor_id
        )
    if mutation == "delete_income":
        line = line_service.add_income(report_id, "salary", Decimal("100.00"), actor_id=actor_id)
        return lambda: line_service.delete_income(report_id, line.id, actor_id=actor_id)
    if mutation == "add_expense":
        return lambda: line_service.add_expense(
            report_id, "office_rent", Decimal("100.00"), actor_id=actor_id
        )
    if mutation == "update_expense":
        line = line_service.add_expense(
            report_id, "office_rent", Decimal("100.00"), actor_id=actor_id
        )
        return lambda: line_service.update_expense(
            report_id, line.id, amount=Decimal("125.00"), actor_id=actor_id
        )
    if mutation == "delete_expense":
        line = line_service.add_expense(
            report_id, "office_rent", Decimal("100.00"), actor_id=actor_id
        )
        return lambda: line_service.delete_expense(report_id, line.id, actor_id=actor_id)
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
def test_financial_line_mutations_clear_saved_tax_for_pre_submission_report(
    test_db, actor_user, mutation, client_factory
):
    c = client_factory(full_name=f"AR create extra INV{mutation}", id_number=f"ARCEINV{mutation}")
    report = AnnualReportService(test_db).create_report(
        c.id, 2026, "corporation", actor_user.id, actor_user.full_name
    )
    line_service = AnnualReportFinancialLineService(test_db)
    tax_service = AnnualReportTaxService(test_db)
    mutate = _prepare_financial_mutation(line_service, report.id, mutation, actor_user.id)

    tax_service.save_tax_calculation(report.id, Decimal("100.00"), None)
    test_db.refresh(report)
    assert report.tax_due == Decimal("100.00")

    mutate()

    test_db.refresh(report)
    assert report.tax_due is None
    assert report.refund_due is None


def test_financial_line_mutation_does_not_clear_saved_tax_for_submitted_report(
    test_db, actor_user, client_factory
):
    c = client_factory(full_name="AR create extra SUBMITTED-TAX", id_number="ARCESUBMITTED-TAX")
    report = AnnualReportService(test_db).create_report(
        c.id, 2026, "corporation", actor_user.id, actor_user.full_name
    )
    AnnualReportRepository(test_db).update(
        report.id,
        status=AnnualReportStatus.SUBMITTED,
        tax_due=Decimal("100.00"),
    )
    test_db.refresh(report)

    AnnualReportFinancialLineService(test_db).add_income(
        report.id, "salary", Decimal("100.00"), actor_id=actor_user.id
    )

    test_db.refresh(report)
    assert report.status == AnnualReportStatus.SUBMITTED
    assert report.tax_due == Decimal("100.00")
    assert report.refund_due is None


def test_annex_line_creates_schedule_owner_when_missing(test_db, actor_user, client_factory):
    c = client_factory(full_name="AR create extra G", id_number="ARCEG")
    service = AnnualReportService(test_db)
    report = service.create_report(c.id, 2026, "corporation", actor_user.id, actor_user.full_name)

    assert service.get_annex_lines(report.id, AnnualReportSchedule.SCHEDULE_B) == []

    line = service.add_annex_line(
        report.id,
        AnnualReportSchedule.SCHEDULE_B,
        {"rental_income": 12000},
        notes="auto owner",
        actor_id=actor_user.id,
    )

    assert line.schedule == AnnualReportSchedule.SCHEDULE_B
    assert line.annual_report_id == report.id
    schedules = service.get_schedules(report.id)
    assert any(
        entry.schedule == AnnualReportSchedule.SCHEDULE_B and entry.is_required is False
        for entry in schedules
    )
