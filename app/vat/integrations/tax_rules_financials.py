"""Adapter for tax_rules financial access used by VAT reports."""


def get_financial_value(year: int, key: str):
    from tax_rules import get_financial

    return get_financial(year, key)


def get_vat_deduction_rate_for_category(year: int, category: str):
    from tax_rules import get_vat_deduction_rate

    return get_vat_deduction_rate(category)


def get_vat_rate_percent(year: int):
    return get_financial_value(year, "vat_rate_percent").value
