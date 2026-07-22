"""
tax_rules — מקור האמת הרשמי לחוקי מס ישראל.

נקודת כניסה ראשית: registry.py
  from app.tax_rules.registry import get_obligations, get_financials, get_periodic_calendar, ...
"""

from .registry import (
    get_annual_calendar,
    get_annual_report_rule,
    get_btl_due_day,
    get_credit_point_config,
    get_effective_periodic_date,
    get_financial,
    get_financials,
    get_income_tax_brackets,
    get_ni_brackets,
    get_obligations,
    get_periodic_calendar,
    get_vat_deduction_rate,
    get_vat_deduction_rules,
    validate,
)
from .sources import SOURCES
from .statutory import DONATION_CREDIT_RATE, DONATION_MINIMUM_ILS

TAX_RULES_VERSION = "2026.2"

__all__ = [
    "TAX_RULES_VERSION",
    "SOURCES",
    "DONATION_CREDIT_RATE",
    "DONATION_MINIMUM_ILS",
    "get_annual_calendar",
    "get_annual_report_rule",
    "get_btl_due_day",
    "get_credit_point_config",
    "get_effective_periodic_date",
    "get_income_tax_brackets",
    "get_financial",
    "get_financials",
    "get_ni_brackets",
    "get_obligations",
    "get_periodic_calendar",
    "get_vat_deduction_rate",
    "get_vat_deduction_rules",
    "validate",
]
