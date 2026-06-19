import pytest

from app.annual_reports.annual_report_tax_engine import calculate_tax
from app.core.exceptions import AppError


def test_calculate_tax_applies_pension_and_donation_credits():
    result = calculate_tax(
        taxable_income=80_000,
        tax_year=2024,
        credit_points=2.25,
        pension_deduction=6_000,
        donation_amount=1_000,
        other_credits=500,
    )

    # Base income stays on original taxable_income
    assert result.taxable_income == 80_000
    # Pension capped and subtracted before brackets
    assert result.pension_deduction == 6_000
    assert result.tax_before_credits == 7_400.0
    # Credits applied afterward
    assert result.credit_points_value == 6_534.0
    assert result.donation_credit == 350.0
    assert result.other_credits == 500
    assert result.tax_after_credits == 16.0
    assert round(result.effective_rate, 6) == 0.0002


def test_calculate_tax_caps_pension_to_income_and_zero_income_is_zero_tax():
    result = calculate_tax(taxable_income=0, tax_year=2024, pension_deduction=5_000)
    assert result.taxable_income == 0
    assert result.pension_deduction == 0  # capped
    assert result.tax_before_credits == 0
    assert result.tax_after_credits == 0
    assert result.effective_rate == 0


def test_calculate_tax_handles_large_pension_deduction():
    result = calculate_tax(
        taxable_income=50_000, tax_year=2024, pension_deduction=60_000, credit_points=0
    )
    # Deduction capped to taxable income
    assert result.pension_deduction == 50_000
    # Adjusted income zero -> no tax
    assert result.tax_before_credits == 0
    assert result.tax_after_credits == 0
    assert result.effective_rate == 0


def test_calculate_tax_unsupported_year_raises():
    with pytest.raises(AppError):
        calculate_tax(taxable_income=10_000, tax_year=2035)


def test_calculate_tax_hits_top_bracket_and_normalizes_negative_credits():
    result = calculate_tax(
        taxable_income=1_000_000,
        tax_year=2026,
        credit_points=0,
        pension_deduction=0,
        donation_amount=-50,  # normalized to 0
        other_credits=-20,  # normalized to 0
    )
    assert result.tax_before_credits > 0
    assert result.donation_credit == 0
    assert result.other_credits == 0
    assert any(b.to_amount is None for b in result.brackets)
