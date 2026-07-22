"""Tests for /groups?due_after= cutoff and order=due sorting.

These back the dashboard "upcoming deadlines" panel, which delegates its
"open + nearest-first" selection to the endpoint instead of filtering client-side.
"""

from datetime import date

from tests.tax_calendar.api.grouped_helpers import (
    PATH,
    add_advance_payment,
    advance_entry,
    headers,
)


def _setup_two_dated_advance_groups(test_db):
    """Two advance groups: an earlier one (2026) and a later one (2027)."""
    early = advance_entry(test_db, year=2026)
    late = advance_entry(test_db, year=2027)
    add_advance_payment(test_db, early, due_date=date(2026, 2, 15))
    add_advance_payment(test_db, late, due_date=date(2027, 2, 15))
    test_db.commit()
    return early, late


def test_due_after_excludes_groups_before_cutoff(client, auth_token, test_db):
    _setup_two_dated_advance_groups(test_db)

    resp = client.get(f"{PATH}?due_after=2027-01-01", headers=headers(auth_token))

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert resp.json()["total"] == 1
    assert items[0]["effective_due_date_min"] == "2027-02-15"


def test_order_due_sorts_by_effective_due_date_ascending(client, auth_token, test_db):
    _setup_two_dated_advance_groups(test_db)

    resp = client.get(f"{PATH}?order=due", headers=headers(auth_token))

    assert resp.status_code == 200
    dues = [item["effective_due_date_min"] for item in resp.json()["items"]]
    assert dues == sorted(dues)
    assert dues[0] == "2026-02-15"


def test_invalid_order_value_is_rejected(client, auth_token, test_db):
    resp = client.get(f"{PATH}?order=bogus", headers=headers(auth_token))

    assert resp.status_code == 422
