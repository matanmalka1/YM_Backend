from types import SimpleNamespace

import pytest

from app.annual_reports.services import annual_report_pdf_builder as pdf_builder
from app.annual_reports.services import annual_report_pdf_service as pdf_mod
from app.core.exceptions import NotFoundError


def test_generate_raises_not_found_when_report_missing(test_db):
    service = pdf_mod.AnnualReportPdfService(test_db)

    with pytest.raises(NotFoundError):
        service.generate(999999)


def test_build_pdf_runs_when_reportlab_available_or_raises():
    report = SimpleNamespace(
        tax_year=2026,
        client_type="corporation",
        status=SimpleNamespace(value="not_started"),
        ita_reference="123",
        refund_due=0,
        tax_due=120,
    )
    summary = SimpleNamespace(
        income_lines=[SimpleNamespace(source_type="salary", amount=1000)],
        expense_lines=[SimpleNamespace(category="other", recognized_amount=100)],
        total_income=1000,
        recognized_expenses=100,
    )
    tax = SimpleNamespace(
        taxable_income=900,
        pension_deduction=0,
        tax_before_credits=100,
        credit_points_value=20,
        donation_credit=0,
        other_credits=0,
        tax_after_credits=80,
        effective_rate=8.9,
        total_liability=120,
        national_insurance=SimpleNamespace(base_amount=10, high_amount=5, total=15),
    )
    detail = SimpleNamespace(tax_refund_amount=0, tax_due_amount=120)

    try:
        pdf = pdf_builder.build_pdf(report, "Client", summary, tax, detail)
        assert isinstance(pdf, (bytes, bytearray))
        assert len(pdf) > 0
    except ImportError:
        pytest.skip("reportlab is not installed in this environment")
