from datetime import date, datetime
from decimal import Decimal
from typing import Any

_MONTH_HE = {
    1: "ינואר",
    2: "פברואר",
    3: "מרץ",
    4: "אפריל",
    5: "מאי",
    6: "יוני",
    7: "יולי",
    8: "אוגוסט",
    9: "ספטמבר",
    10: "אוקטובר",
    11: "נובמבר",
    12: "דצמבר",
}


def _date_value(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _money(value: Any) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _period_label(period: str, months_count: int) -> str:
    try:
        year_text, month_text = period.split("-")
        year = int(year_text)
        start_month = int(month_text)
    except (ValueError, TypeError):
        return period

    if start_month not in _MONTH_HE:
        return period

    if months_count == 1:
        return f"{_MONTH_HE[start_month]} {year}"

    end_month = start_month + months_count - 1
    if end_month not in _MONTH_HE:
        return period
    return f"{_MONTH_HE[start_month]}–{_MONTH_HE[end_month]} {year}"


def vat_work_item_metadata(item, due_date: date) -> dict[str, Any]:
    months_count = 2 if _enum_value(getattr(item, "period_type", None)) == "bimonthly" else 1
    return {
        "period": item.period,
        "period_label": _period_label(item.period, months_count),
        "period_months_count": months_count,
        "due_date": _date_value(due_date),
        "status": _enum_value(item.status),
    }


def annual_report_metadata(report) -> dict[str, Any]:
    return {
        "tax_year": report.tax_year,
        "filing_deadline": _date_value(report.filing_deadline),
        "status": _enum_value(report.status),
    }


def advance_payment_metadata(payment) -> dict[str, Any]:
    expected = payment.expected_amount
    paid = payment.paid_amount
    remaining = None
    if expected is not None:
        remaining = max(Decimal(str(expected)) - Decimal(str(paid or 0)), Decimal("0"))
    months_count = int(payment.period_months_count or 1)
    return {
        "period": payment.period,
        "period_label": _period_label(payment.period, months_count),
        "period_months_count": months_count,
        "frequency": "bimonthly" if months_count == 2 else "monthly",
        "due_date": _date_value(payment.due_date_effective or payment.due_date),
        "status": _enum_value(payment.status),
        "expected_amount": _money(expected),
        "paid_amount": _money(paid),
        "remaining_amount": _money(remaining),
        "payment_method": _enum_value(payment.payment_method),
        "paid_at": _date_value(payment.paid_at),
        "annual_report_id": payment.annual_report_id,
    }


def charge_metadata(charge, due_date: date) -> dict[str, Any]:
    return {
        "business_id": charge.business_id,
        "charge_type": _enum_value(charge.charge_type),
        "status": _enum_value(charge.status),
        "amount": _money(charge.amount),
        "issued_at": _date_value(charge.issued_at),
        "due_date": _date_value(due_date),
        "period": charge.period,
    }
