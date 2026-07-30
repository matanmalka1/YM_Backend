"""Pure advance-payment calculations.

No DB access — all inputs are passed as arguments.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError

DecimalInput = Decimal | int | float | str


def calculate_advance_payment_amounts(
    turnover_amount: DecimalInput | None,
    advance_rate: DecimalInput | None,
    override_amount: DecimalInput | None,
    *,
    withheld_amount: DecimalInput | None = None,
    fallback_expected: DecimalInput | None = None,
) -> tuple[Decimal, Decimal]:
    """Return the gross calculated amount and the resolved expected amount.

    ``calculated_amount`` is always ``turnover_amount × advance_rate / 100``.
    ``override_amount`` replaces the expected amount when present; otherwise
    withheld-at-source credit is deducted and the result is floored at zero.
    """
    calculated = Decimal("0.00")
    if turnover_amount is not None and advance_rate is not None:
        calculated = (Decimal(str(turnover_amount)) * Decimal(str(advance_rate)) / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    if override_amount is not None:
        expected = Decimal(str(override_amount))
    elif fallback_expected is not None and calculated == 0:
        expected = Decimal(str(fallback_expected))
    else:
        withheld = Decimal(str(withheld_amount or 0))
        expected = max(Decimal("0.00"), calculated - withheld)

    return calculated, expected


def derive_annual_income_from_vat(
    total_output_vat: Decimal,
    vat_rate: Decimal,
) -> Decimal:
    """Reverse-calculate annual taxable income from total output VAT."""
    if vat_rate == 0:
        raise AppError("שיעור המע״מ לא יכול להיות אפס", ErrorCode.ADVANCE_PAYMENT_RATE_INVALID)
    return total_output_vat / vat_rate


def calculate_expected_amount(
    annual_income: Decimal,
    advance_rate: Decimal,
    period_months_count: int = 1,
) -> Decimal:
    """
    Formula: annual_income × rate / 12 × period_months_count
    This matches the Israeli tax authority's advance payment calculation method.
    Rounded to the nearest whole shekel.
    period_months_count=1 → monthly, period_months_count=2 → bi-monthly.
    """
    monthly = (annual_income * advance_rate / Decimal("100")) / Decimal("12")
    return (monthly * period_months_count).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
