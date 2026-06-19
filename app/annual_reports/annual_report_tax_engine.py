"""Pure Israeli income tax calculation engine — multi-year brackets."""

from dataclasses import dataclass

from tax_rules.statutory import (
    DONATION_CREDIT_RATE as _DONATION_CREDIT_RATE,
)
from tax_rules.statutory import (
    DONATION_MINIMUM_ILS as _DONATION_MINIMUM_ILS,
)

from app.annual_reports.annual_report_messages import UNSUPPORTED_TAX_YEAR_ERROR
from app.annual_reports.integrations.tax_rules_registry import (
    get_credit_point_annual_value,
    get_default_resident_credit_points,
    get_income_tax_brackets_for_year,
    get_supported_tax_years,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.utils.time_utils import israel_today

try:
    _BASE_RESIDENT_CREDIT_POINTS: float = float(
        get_default_resident_credit_points(israel_today().year)
    )
except Exception:
    _BASE_RESIDENT_CREDIT_POINTS = 2.25


@dataclass
class BracketBreakdownItem:
    rate: float
    from_amount: float
    to_amount: float | None
    taxable_in_bracket: float
    tax_in_bracket: float


@dataclass
class TaxCalculationResult:
    taxable_income: float
    pension_deduction: float
    tax_before_credits: float
    credit_points_value: float
    donation_credit: float
    other_credits: float
    tax_after_credits: float
    effective_rate: float
    brackets: list[BracketBreakdownItem]
    total_credit_points: float


def calculate_tax(
    taxable_income: float,
    tax_year: int,
    credit_points: float = _BASE_RESIDENT_CREDIT_POINTS,
    pension_deduction: float = 0.0,
    donation_amount: float = 0.0,
    other_credits: float = 0.0,
) -> TaxCalculationResult:
    """Calculate Israeli income tax for the given tax year."""
    taxable_income = float(taxable_income)
    credit_points = float(credit_points)
    pension_deduction = float(pension_deduction)
    donation_amount = float(donation_amount)
    other_credits = float(other_credits)

    try:
        year_brackets = get_income_tax_brackets_for_year(tax_year)
        credit_point_value = get_credit_point_annual_value(tax_year)
    except KeyError as exc:
        raise AppError(
            UNSUPPORTED_TAX_YEAR_ERROR.format(
                tax_year=tax_year, supported_years=get_supported_tax_years()
            ),
            ErrorCode.TAX_ENGINE_INVALID_INPUT,
            status_code=400,
        ) from exc

    deduction = min(max(pension_deduction, 0.0), max(taxable_income, 0.0))
    adjusted_income = taxable_income - deduction

    credit_points_value = round(credit_points * credit_point_value, 2)
    _donation_amt = max(donation_amount, 0.0)
    donation_credit = (
        round(_donation_amt * _DONATION_CREDIT_RATE, 2)
        if _donation_amt >= _DONATION_MINIMUM_ILS
        else 0.0
    )
    other_credits_val = round(max(other_credits, 0.0), 2)
    total_credits = credit_points_value + donation_credit + other_credits_val

    if adjusted_income <= 0:
        return TaxCalculationResult(
            taxable_income=round(taxable_income, 2),
            pension_deduction=round(deduction, 2),
            tax_before_credits=0.0,
            credit_points_value=credit_points_value,
            donation_credit=donation_credit,
            other_credits=other_credits_val,
            tax_after_credits=0.0,
            effective_rate=0.0,
            brackets=[],
            total_credit_points=round(credit_points, 4),
        )

    tax = 0.0
    prev = 0.0
    breakdown: list[BracketBreakdownItem] = []
    for bracket in year_brackets:
        upper = bracket.up_to_ils
        rate = bracket.rate
        if upper is None:
            taxable_in_bracket = adjusted_income - prev
            tax_in_bracket = taxable_in_bracket * rate
            tax += tax_in_bracket
            if taxable_in_bracket > 0:
                breakdown.append(
                    BracketBreakdownItem(
                        rate,
                        prev,
                        None,
                        round(taxable_in_bracket, 2),
                        round(tax_in_bracket, 2),
                    )
                )
            break
        if adjusted_income <= upper:
            taxable_in_bracket = adjusted_income - prev
            tax_in_bracket = taxable_in_bracket * rate
            tax += tax_in_bracket
            if taxable_in_bracket > 0:
                breakdown.append(
                    BracketBreakdownItem(
                        rate,
                        prev,
                        upper,
                        round(taxable_in_bracket, 2),
                        round(tax_in_bracket, 2),
                    )
                )
            break
        taxable_in_bracket = upper - prev
        tax_in_bracket = taxable_in_bracket * rate
        tax += tax_in_bracket
        if taxable_in_bracket > 0:
            breakdown.append(
                BracketBreakdownItem(
                    rate,
                    prev,
                    upper,
                    round(taxable_in_bracket, 2),
                    round(tax_in_bracket, 2),
                )
            )
        prev = upper

    tax_after_credits = max(0.0, tax - total_credits)
    effective_rate = tax_after_credits / taxable_income if taxable_income else 0.0

    return TaxCalculationResult(
        taxable_income=round(taxable_income, 2),
        pension_deduction=round(deduction, 2),
        tax_before_credits=round(tax, 2),
        credit_points_value=credit_points_value,
        donation_credit=donation_credit,
        other_credits=other_credits_val,
        tax_after_credits=round(tax_after_credits, 2),
        effective_rate=round(effective_rate, 6),
        brackets=breakdown,
        total_credit_points=round(credit_points, 4),
    )


__all__ = ["calculate_tax", "TaxCalculationResult", "BracketBreakdownItem"]
