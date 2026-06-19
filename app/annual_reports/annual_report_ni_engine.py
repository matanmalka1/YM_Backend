"""National Insurance (ביטוח לאומי) calculation engine — multi-year, multi-bracket."""

from dataclasses import dataclass

from app.annual_reports.integrations.tax_rules_registry import (
    get_ni_brackets_for_year,
    get_supported_tax_years,
)
from app.annual_reports.models.annual_report_enums import ClientAnnualFilingType

_NI_EXEMPT_TYPES = {
    ClientAnnualFilingType.INDIVIDUAL,
    ClientAnnualFilingType.CORPORATION,
}

_MONTHS = 12


@dataclass
class NationalInsuranceResult:
    base_amount: float
    high_amount: float
    total: float


def calculate_national_insurance(
    income: float,
    tax_year: int = 2024,
    client_type: ClientAnnualFilingType | None = None,
) -> NationalInsuranceResult:
    """חישוב דמי ביטוח לאומי לעצמאי לפי שנת מס.

    מחזיר אפס עבור שכירים וחברות — אינם משלמים ביטוח לאומי עצמאי בדוח שנתי.
    """
    if client_type in _NI_EXEMPT_TYPES:
        return NationalInsuranceResult(base_amount=0.0, high_amount=0.0, total=0.0)

    try:
        brackets = get_ni_brackets_for_year(tax_year)
    except KeyError:
        brackets = get_ni_brackets_for_year(max(get_supported_tax_years()))

    income = max(float(income), 0.0)
    prev = 0.0
    base_amount = 0.0
    high_amount = 0.0

    for i, bracket in enumerate(brackets):
        annual_ceiling = bracket.up_to_ils * _MONTHS
        rate = bracket.rate_percent / 100.0
        taxable = min(income, annual_ceiling) - prev
        if taxable <= 0:
            break
        amount = round(taxable * rate, 2)
        if i == 0:
            base_amount = amount
        else:
            high_amount += amount
        prev = annual_ceiling

    total = round(base_amount + high_amount, 2)
    return NationalInsuranceResult(base_amount=base_amount, high_amount=high_amount, total=total)


__all__ = ["calculate_national_insurance", "NationalInsuranceResult"]
