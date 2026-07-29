"""W3 — the closing act records its facts, and a submitted report is fully locked.

Closing facts (D-13, D-20, D-32): closed_by names the author, closed_late is
written once at the close — true/false against the filing deadline, NULL when
there is no deadline, never False-by-default.

Full lock (D-13): nothing on a submitted report changes — figures, lines,
schedules, annexes, detail, deadline — and a submitted report is never deleted.
"""

from datetime import datetime
from decimal import Decimal

from app.annual_reports.services.annual_report_detail_service import (
    AnnualReportDetailService,
)
from app.annual_reports.services.annual_report_financial_line_service import (
    AnnualReportFinancialLineService,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.common.enums import ObligationStatus
from app.utils.time_utils import utcnow

API = "/api/v1/annual-reports"

_PAST_DEADLINE = datetime(2020, 5, 31, 23, 59, 59)
_FUTURE_DEADLINE = datetime(2099, 5, 31, 23, 59, 59)


def _ready_for_submit(
    test_db,
    annual_report_service_factory,
    client_factory,
    test_user,
    *,
    filing_deadline,
):
    """A report at AWAITING_VERIFICATION that passes every readiness gate."""
    report = annual_report_service_factory(actor=test_user, client=client_factory())
    svc = AnnualReportService(test_db)
    AnnualReportFinancialLineService(test_db).add_income(
        report.id,
        "business",
        Decimal("50000"),
        None,
        actor_id=test_user.id,
        actor_name=test_user.full_name,
    )
    AnnualReportDetailService(test_db).update_detail(
        report.id,
        actor_id=test_user.id,
        actor_name=test_user.full_name,
        client_approved_at=utcnow(),
    )
    # Last: income mutations clear saved tax_due while pre-submission, so the
    # readiness-satisfying fields are written after every line mutation.
    svc.repo.update(
        report.id,
        status=ObligationStatus.AWAITING_VERIFICATION,
        assigned_to=test_user.id,
        tax_due=Decimal("1000"),
        filing_deadline=filing_deadline,
    )
    return report.id


def _submit(client, advisor_headers, report_id: int):
    return client.post(f"{API}/{report_id}/submit", headers=advisor_headers, json={})


# ── Closing facts ─────────────────────────────────────────────────────────────


def test_submit_records_author_and_late_close(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    report_id = _ready_for_submit(
        test_db,
        annual_report_service_factory,
        client_factory,
        test_user,
        filing_deadline=_PAST_DEADLINE,
    )
    resp = _submit(client, advisor_headers, report_id)
    assert resp.status_code == 200, resp.json()

    row = AnnualReportService(test_db).repo.get_by_id(report_id)
    assert row.status == ObligationStatus.SUBMITTED
    assert row.closed_by == test_user.id
    assert row.closed_at is not None
    assert row.closed_late is True


def test_submit_on_time_records_closed_late_false(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    report_id = _ready_for_submit(
        test_db,
        annual_report_service_factory,
        client_factory,
        test_user,
        filing_deadline=_FUTURE_DEADLINE,
    )
    resp = _submit(client, advisor_headers, report_id)
    assert resp.status_code == 200

    row = AnnualReportService(test_db).repo.get_by_id(report_id)
    assert row.closed_late is False


def test_submit_without_deadline_leaves_closed_late_null(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """D-32: no due date means NULL — never False, or the record reads 'on time'."""
    report_id = _ready_for_submit(
        test_db,
        annual_report_service_factory,
        client_factory,
        test_user,
        filing_deadline=None,
    )
    resp = _submit(client, advisor_headers, report_id)
    assert resp.status_code == 200

    row = AnnualReportService(test_db).repo.get_by_id(report_id)
    assert row.closed_at is not None
    assert row.closed_late is None


def test_submit_blocked_without_assignee(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """D-15: the shared gate — a closed obligation is a record with an author."""
    report_id = _ready_for_submit(
        test_db,
        annual_report_service_factory,
        client_factory,
        test_user,
        filing_deadline=_FUTURE_DEADLINE,
    )
    AnnualReportService(test_db).repo.update(report_id, assigned_to=None)

    resp = _submit(client, advisor_headers, report_id)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ANNUAL_REPORT.INVALID_STATUS"


# ── Full lock ─────────────────────────────────────────────────────────────────


def _submitted_report_with_lines(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """A submitted report that still owns an income line, an expense line and a schedule."""
    report_id = _ready_for_submit(
        test_db,
        annual_report_service_factory,
        client_factory,
        test_user,
        filing_deadline=_FUTURE_DEADLINE,
    )
    line_svc = AnnualReportFinancialLineService(test_db)
    income = line_svc.add_income(
        report_id, "salary", Decimal("100"), None, actor_id=test_user.id, actor_name="t"
    )
    expense = line_svc.add_expense(
        report_id, "office_rent", Decimal("50"), actor_id=test_user.id, actor_name="t"
    )
    schedule_resp = client.post(
        f"{API}/{report_id}/schedules",
        headers=advisor_headers,
        json={"schedule": "schedule_b", "notes": None},
    )
    assert schedule_resp.status_code == 201
    # complete it so readiness still passes with the schedule present
    complete_resp = client.post(
        f"{API}/{report_id}/schedules/complete",
        headers=advisor_headers,
        json={"schedule": "schedule_b"},
    )
    assert complete_resp.status_code == 200

    # The line mutations above cleared the saved tax result; restore it so the
    # readiness gate passes.
    AnnualReportService(test_db).repo.update(report_id, tax_due=Decimal("1000"))

    resp = _submit(client, advisor_headers, report_id)
    assert resp.status_code == 200, resp.json()
    return report_id, income.id, expense.id


def _assert_locked(resp):
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"


def test_submitted_report_rejects_every_mutation(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    report_id, income_id, expense_id = _submitted_report_with_lines(
        client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
    )

    # Financial lines — add / update / delete, both kinds
    _assert_locked(
        client.post(
            f"{API}/{report_id}/income",
            headers=advisor_headers,
            json={"source_type": "salary", "amount": 1},
        )
    )
    _assert_locked(
        client.patch(
            f"{API}/{report_id}/income/{income_id}",
            headers=advisor_headers,
            json={"amount": 2},
        )
    )
    _assert_locked(client.delete(f"{API}/{report_id}/income/{income_id}", headers=advisor_headers))
    _assert_locked(
        client.post(
            f"{API}/{report_id}/expenses",
            headers=advisor_headers,
            json={"category": "office_rent", "amount": 1},
        )
    )
    _assert_locked(
        client.patch(
            f"{API}/{report_id}/expenses/{expense_id}",
            headers=advisor_headers,
            json={"amount": 2},
        )
    )
    _assert_locked(
        client.delete(f"{API}/{report_id}/expenses/{expense_id}", headers=advisor_headers)
    )

    # Detail, schedules, deadline, tax calculation
    _assert_locked(
        client.patch(
            f"{API}/{report_id}/details",
            headers=advisor_headers,
            json={"internal_notes": "after the fact"},
        )
    )
    _assert_locked(
        client.post(
            f"{API}/{report_id}/schedules",
            headers=advisor_headers,
            json={"schedule": "schedule_a", "notes": None},
        )
    )
    _assert_locked(
        client.post(
            f"{API}/{report_id}/schedules/complete",
            headers=advisor_headers,
            json={"schedule": "schedule_b"},
        )
    )
    _assert_locked(
        client.post(
            f"{API}/{report_id}/deadline",
            headers=advisor_headers,
            json={"deadline_type": "extended"},
        )
    )
    _assert_locked(
        client.post(
            f"{API}/{report_id}/tax-calculation/save",
            headers=advisor_headers,
            json={"tax_due": 123},
        )
    )

    # A submitted report is never removed (D-13, D-22)
    _assert_locked(client.delete(f"{API}/{report_id}", headers=advisor_headers))

    # And the figures did not move
    row = AnnualReportService(test_db).repo.get_by_id(report_id)
    assert row.status == ObligationStatus.SUBMITTED
    assert row.deleted_at is None
