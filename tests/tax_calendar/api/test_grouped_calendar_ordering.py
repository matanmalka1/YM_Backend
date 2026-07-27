from app.common.enums import DeadlineRuleType, ObligationType
from tests.helpers.tax_calendar_links import PATH, headers, make_entry


def _make_vat(db, period: str, months: int, tax_year: int):
    rule_type = DeadlineRuleType.VAT_MONTHLY if months == 1 else DeadlineRuleType.VAT_BIMONTHLY
    return make_entry(
        db,
        obligation_type=ObligationType.VAT,
        rule_type=rule_type,
        period=period,
        months=months,
        tax_year=tax_year,
    )


def _make_advance(db, period: str, months: int, tax_year: int):
    rule_type = (
        DeadlineRuleType.ADVANCE_MONTHLY if months == 1 else DeadlineRuleType.ADVANCE_BIMONTHLY
    )
    return make_entry(
        db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=rule_type,
        period=period,
        months=months,
        tax_year=tax_year,
    )


def _make_annual(db, tax_year: int):
    return make_entry(
        db,
        obligation_type=ObligationType.ANNUAL_REPORT,
        rule_type=DeadlineRuleType.ANNUAL_REPORT,
        period=None,
        months=None,
        tax_year=tax_year,
    )


def test_ordering_full_period(client, auth_token, test_db):
    """vat/1, vat/2, advance/1, advance/2, annual in that order."""
    _make_advance(test_db, "2026-01", 2, 2026)
    _make_annual(test_db, 2026)
    _make_advance(test_db, "2026-01", 1, 2026)
    _make_vat(test_db, "2026-01", 2, 2026)
    _make_vat(test_db, "2026-01", 1, 2026)
    test_db.commit()

    response = client.get(f"{PATH}?include_empty=true", headers=headers(auth_token))

    assert response.status_code == 200
    rows = response.json()["items"]
    assert len(rows) == 5
    assert [(r["obligation_type"], r["period_months_count"]) for r in rows] == [
        ("vat", 1),
        ("vat", 2),
        ("advance_payment", 1),
        ("advance_payment", 2),
        ("annual_report", None),
    ]


def test_ordering_monthly_only(client, auth_token, test_db):
    """When only monthly rows exist: vat/1, advance/1."""
    _make_advance(test_db, "2026-02", 1, 2026)
    _make_vat(test_db, "2026-02", 1, 2026)
    test_db.commit()

    response = client.get(f"{PATH}?include_empty=true", headers=headers(auth_token))

    assert response.status_code == 200
    rows = response.json()["items"]
    assert len(rows) == 2
    assert [(r["obligation_type"], r["period_months_count"]) for r in rows] == [
        ("vat", 1),
        ("advance_payment", 1),
    ]
