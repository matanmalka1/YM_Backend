"""The annual calendar entry's own due date is not a deadline for anybody.

``AnnualReport.filing_deadline`` is derived per entity type from
``tax_rules_config`` (company 31/07, individual 31/05, small business 30/04, plus
year-specific deferrals). The shared ``TaxCalendarEntry`` for an annual obligation
cannot carry that — annual uniqueness is ``(obligation_type, tax_year)``, one row
for every client — so its own ``due_date`` comes from a seeded rule and matches no
particular client.

These tests pin that the grouped calendar never presents that date as a deadline.
"""

from datetime import datetime

from app.annual_reports.models.annual_report_enums import FilingDeadlineType
from tests.helpers.tax_calendar_links import (
    PATH,
    add_annual_report,
    annual_entry,
    headers,
    vat_entry,
)


def _annual_group(client, auth_token):
    response = client.get(f"{PATH}?include_empty=true", headers=headers(auth_token))
    assert response.status_code == 200
    groups = [g for g in response.json()["items"] if g["obligation_type"] == "annual_report"]
    assert len(groups) == 1
    return groups[0]


def test_annual_group_does_not_publish_a_regulatory_due_date(client, auth_token, test_db):
    """No single statutory annual date exists, so none is published."""
    entry = annual_entry(test_db)
    add_annual_report(test_db, entry)
    test_db.commit()

    assert _annual_group(client, auth_token)["regulatory_due_date"] is None


def test_periodic_group_still_publishes_its_regulatory_due_date(client, auth_token, test_db):
    """VAT and advance periods genuinely do share one statutory date — unchanged."""
    vat_entry(test_db)
    test_db.commit()

    response = client.get(f"{PATH}?include_empty=true", headers=headers(auth_token))
    vat_groups = [g for g in response.json()["items"] if g["obligation_type"] == "vat"]

    assert vat_groups[0]["regulatory_due_date"] is not None


def test_annual_effective_dates_come_from_the_report(client, auth_token, test_db):
    entry = annual_entry(test_db)
    add_annual_report(test_db, entry)
    test_db.commit()

    group = _annual_group(client, auth_token)

    assert group["effective_due_date_min"] == "2027-07-31"
    assert group["effective_due_date_max"] == "2027-07-31"


def test_custom_deadline_report_does_not_inherit_the_entry_date(client, auth_token, test_db):
    """A custom-deadline report has no computed deadline — and must not borrow one.

    ``filing_deadline`` is NULL for FilingDeadlineType.CUSTOM. Falling back to the
    entry's seeded date made the dashboard show that date as the report's deadline
    and counted the report overdue against it.
    """
    entry = annual_entry(test_db)
    report = add_annual_report(test_db, entry)
    report.deadline_type = FilingDeadlineType.CUSTOM
    report.filing_deadline = None
    test_db.commit()

    group = _annual_group(client, auth_token)

    assert group["effective_due_date_min"] is None
    assert group["effective_due_date_max"] is None
    assert group["overdue_count"] == 0


def test_custom_deadline_report_is_not_counted_overdue(client, auth_token, test_db):
    """An unknown deadline cannot be in the past — overdue needs a date to compare."""
    entry = annual_entry(test_db)
    with_deadline = add_annual_report(test_db, entry)
    with_deadline.filing_deadline = datetime(2020, 7, 31, 10, 0)  # long past
    custom = add_annual_report(test_db, entry)
    custom.deadline_type = FilingDeadlineType.CUSTOM
    custom.filing_deadline = None
    test_db.commit()

    group = _annual_group(client, auth_token)

    assert group["linked_count"] == 2
    # Only the dated, past-due report counts; the undated one is not overdue.
    assert group["overdue_count"] == 1
    assert group["effective_due_date_min"] == "2020-07-31"
