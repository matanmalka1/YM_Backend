from __future__ import annotations

from .calendars.calendar_2025 import ANNUAL_TAX_AUTHORITY_DUE_DATES_2025
from .calendars.calendar_2026 import (
    ANNUAL_TAX_AUTHORITY_DUE_DATES_2026,
    BTL_MONTHLY_DUE_DAY,
    PERIODIC_TAX_AUTHORITY_DUE_DATES_2026,
)
from .exceptions import (
    ANNUAL_OVERRIDES_TAX_YEAR_2025,
    DEADLINE_OVERRIDES_2026,
    get_override,
)
from .financials.constants_2024 import (
    CONSTANTS_2024,
    CREDIT_POINT_2024,
    INCOME_TAX_BRACKETS_2024,
    NI_BRACKETS_2024,
)
from .financials.constants_2025 import (
    CONSTANTS_2025,
    CREDIT_POINT_2025,
    INCOME_TAX_BRACKETS_2025,
    NI_BRACKETS_2025,
)
from .financials.constants_2026 import (
    CONSTANTS_2026,
    CREDIT_POINT_2026,
    INCOME_TAX_BRACKETS_2026,
    NI_BRACKETS_2026,
)
from .policy import resolve_annual_report_rule, resolve_obligation_rules
from .types import (
    ClientTaxProfile,
    CreditPointConfig,
    DeadlineOverride,
    FinancialConstant,
    IncomeTaxBracket,
    ObligationRule,
    RateBracket,
)
from .validations import validate_profile
from .vat_deduction import VAT_DEDUCTION_RATE_BY_CATEGORY, VAT_DEDUCTION_RULES

# ── לוחות מועדים ─────────────────────────────────────────────────────────────

_PERIODIC_CALENDARS: dict[int, dict[str, dict[str, str]]] = {
    2026: PERIODIC_TAX_AUTHORITY_DUE_DATES_2026,
}

_ANNUAL_CALENDARS: dict[int, dict[str, dict[str, str]]] = {
    2025: ANNUAL_TAX_AUTHORITY_DUE_DATES_2025,
    2026: ANNUAL_TAX_AUTHORITY_DUE_DATES_2026,
}

# ── קבועים כספיים ─────────────────────────────────────────────────────────────

_FINANCIALS: dict[int, dict[str, FinancialConstant]] = {
    2024: CONSTANTS_2024,
    2025: CONSTANTS_2025,
    2026: CONSTANTS_2026,
}

_NI_BRACKETS: dict[int, tuple[RateBracket, ...]] = {
    2024: NI_BRACKETS_2024,
    2025: NI_BRACKETS_2025,
    2026: NI_BRACKETS_2026,
}

_INCOME_TAX_BRACKETS: dict[int, tuple[IncomeTaxBracket, ...]] = {
    2024: INCOME_TAX_BRACKETS_2024,
    2025: INCOME_TAX_BRACKETS_2025,
    2026: INCOME_TAX_BRACKETS_2026,
}

_CREDIT_POINTS: dict[int, CreditPointConfig] = {
    2024: CREDIT_POINT_2024,
    2025: CREDIT_POINT_2025,
    2026: CREDIT_POINT_2026,
}

# ── overrides ─────────────────────────────────────────────────────────────────

_PERIODIC_OVERRIDES: dict[int, tuple[DeadlineOverride, ...]] = {
    2026: DEADLINE_OVERRIDES_2026,
}

_ANNUAL_OVERRIDES: dict[int, tuple[DeadlineOverride, ...]] = {
    2025: ANNUAL_OVERRIDES_TAX_YEAR_2025,
}


# ── Public API ────────────────────────────────────────────────────────────────


def get_periodic_calendar(year: int) -> dict[str, dict[str, str]]:
    """לוח מועדים תקופתי (מע״מ, מקדמות, ניכויים) לשנה נתונה."""
    if year not in _PERIODIC_CALENDARS:
        raise KeyError(f"אין לוח מועדים תקופתי לשנת {year}. יש להוסיף calendars/calendar_{year}.py")
    return _PERIODIC_CALENDARS[year]


def get_annual_calendar(tax_year: int) -> dict[str, dict[str, str]]:
    """לוח מועדים שנתי (דוחות שנתיים) לשנת מס נתונה."""
    if tax_year not in _ANNUAL_CALENDARS:
        raise KeyError(f"אין לוח מועדים שנתי לשנת מס {tax_year}.")
    return _ANNUAL_CALENDARS[tax_year]


def get_effective_periodic_date(year: int, period: str, column: str) -> str | None:
    """
    מחזיר את המועד האפקטיבי לתקופה ועמודה — כולל בדיקת override.
    period: "YYYY-MM", column: שם עמודת הלוח.
    """
    overrides = _PERIODIC_OVERRIDES.get(year, ())
    override = get_override(period, column, overrides)
    if override:
        return override
    calendar = get_periodic_calendar(year)
    entry = calendar.get(period, {})
    return entry.get(column)


def get_financials(year: int) -> dict[str, FinancialConstant]:
    """קבועים כספיים שנתיים (מע״מ, תקרות, נקודת זיכוי)."""
    if year not in _FINANCIALS:
        raise KeyError(f"אין קבועים כספיים לשנת {year}.")
    return _FINANCIALS[year]


def get_financial(year: int, key: str) -> FinancialConstant:
    """קבוע כספי ספציפי לפי שנה ומפתח."""
    constants = get_financials(year)
    if key not in constants:
        raise KeyError(f"קבוע '{key}' לא נמצא לשנת {year}.")
    return constants[key]


def get_ni_brackets(year: int) -> tuple[RateBracket, ...]:
    """מדרגות ביטוח לאומי לעצמאי לשנה נתונה."""
    if year not in _NI_BRACKETS:
        raise KeyError(f"אין מדרגות ביטוח לאומי לשנת {year}.")
    return _NI_BRACKETS[year]


def get_obligations(profile: ClientTaxProfile) -> list[ObligationRule]:
    """חובות דיווח/תשלום לפי פרופיל לקוח."""
    return resolve_obligation_rules(profile)


def get_annual_report_rule(entity_type: str, tax_year: int) -> dict | None:
    """חוק דוח שנתי לפי סוג ישות ושנת מס."""
    return resolve_annual_report_rule(entity_type, tax_year)


def get_vat_deduction_rate(category: str) -> float:
    """שיעור ניכוי תשומות לפי קטגוריה (0.0–1.0). מחזיר 0.0 אם לא נמצא."""
    return VAT_DEDUCTION_RATE_BY_CATEGORY.get(category, 0.0)


def get_vat_deduction_rules():
    """Return canonical VAT input-deduction metadata for API/UI consumers."""
    return VAT_DEDUCTION_RULES


def validate(profile: ClientTaxProfile) -> list[str]:
    """מריץ את כל כללי הvalidation על פרופיל לקוח. רשימה ריקה = תקין."""
    return validate_profile(profile)


def get_income_tax_brackets(year: int) -> tuple[IncomeTaxBracket, ...]:
    """מדרגות מס הכנסה ליחיד (הכנסה מיגיעה אישית) לשנה נתונה."""
    if year not in _INCOME_TAX_BRACKETS:
        raise KeyError(f"אין מדרגות מס הכנסה לשנת {year}.")
    return _INCOME_TAX_BRACKETS[year]


def get_credit_point_config(year: int) -> CreditPointConfig:
    """שווי נקודת זיכוי ונקודות ברירת מחדל לפי שנה."""
    if year not in _CREDIT_POINTS:
        raise KeyError(f"אין נתוני נקודת זיכוי לשנת {year}.")
    return _CREDIT_POINTS[year]


def get_btl_due_day() -> int:
    """מועד תשלום ביטוח לאומי עצמאי — ה-15 בחודש (קבוע חוקי)."""
    return BTL_MONTHLY_DUE_DAY


def get_supported_years() -> tuple[int, ...]:
    """שנים שיש עבורן נתונים מלאים ב-registry (קבועים כספיים + מדרגות)."""
    return tuple(sorted(_FINANCIALS.keys()))


def get_vat_statutory_deadline_day(year: int) -> int:
    """המועד החוקי הבסיסי להגשת דוח מע״מ (ה-15) לשנה נתונה."""
    return int(get_financial(year, "vat_statutory_deadline_day").value)


def get_vat_online_extended_deadline_day(year: int) -> int:
    """הארכת הדיווח הדיגיטלי (ה-19) לשנה נתונה. זכות, לא בסיס חוקי."""
    return int(get_financial(year, "vat_online_extended_deadline_day").value)


def get_advance_payment_due_day(year: int) -> int:
    """מועד תשלום מקדמות מס הכנסה (ה-15) לשנה נתונה."""
    return int(get_financial(year, "advance_payment_due_day").value)
