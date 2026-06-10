"""VAT amount derivation from tax rules."""

from decimal import ROUND_HALF_UP, Decimal

from app.vat.integrations.tax_rules_financials import get_vat_rate_percent
from app.vat.models.vat_enums import VatRateType


def calculate_vat_amount(
    net_amount: float | Decimal,
    rate_type: VatRateType | str | None,
    year: int,
) -> Decimal:
    """Derive VAT amount from the annual configured VAT rate."""
    parsed_rate_type = VatRateType(rate_type or VatRateType.STANDARD)
    if parsed_rate_type in (VatRateType.EXEMPT, VatRateType.ZERO_RATE):
        return Decimal("0.00")

    rate_percent = Decimal(str(get_vat_rate_percent(year)))
    amount = Decimal(str(net_amount)) * rate_percent / Decimal("100")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def split_gross_amount(
    gross_amount: float | Decimal,
    rate_type: VatRateType | str | None,
    year: int,
) -> tuple[Decimal, Decimal]:
    """Split a user-entered VAT-inclusive amount into net and VAT amounts."""
    gross = Decimal(str(gross_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    parsed_rate_type = VatRateType(rate_type or VatRateType.STANDARD)
    if parsed_rate_type in (VatRateType.EXEMPT, VatRateType.ZERO_RATE):
        return gross, Decimal("0.00")

    rate_percent = Decimal(str(get_vat_rate_percent(year)))
    divisor = Decimal("1") + (rate_percent / Decimal("100"))
    net = (gross / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    vat = gross - net
    return net, vat
