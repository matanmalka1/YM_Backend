"""A period's lateness survives being corrected (D-20, D-34).

``closed_late`` answers "was **this row's** closing act late". An amendment has
no due date (D-14), so its own answer is always NULL — and the period it
corrects may well have been filed late. ``chain_closed_late`` carries that
across the correction, written onto the amendment at birth.

Closing the amendment used to erase it: the close wrote both columns from the
same value, and for a row with no due date that value is NULL. The fact was
lost at exactly the moment the correction became the period's filed record, so
the period stopped counting as late the moment it was corrected.

All three domains, because two of them close through a dict handed to
``repo.update`` rather than through the shared helper — which is how they came
to hold their own copy of the rule in the first place.
"""

from datetime import date, datetime
from decimal import Decimal

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.annual_reports.services.annual_report_financial_line_service import (
    AnnualReportFinancialLineService,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.common.enums import ObligationStatus
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.helpers.tax_calendar_links import create_linked_advance_payment
from tests.vat.api.test_vat_reports_utils import setup_ready_item

#: A VAT period whose deadline is long past, so filing it now is late.
LATE_VAT_PERIOD = "2026-01"
PAST_DUE = date(2020, 1, 15)
PAST_DEADLINE = datetime(2020, 5, 31, 23, 59, 59)


def test_vat_amendment_keeps_the_periods_lateness_when_filed(
    client, test_db, advisor_headers, test_user, vat_client
):
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, LATE_VAT_PERIOD, assigned_to=test_user.id
    )
    assert (
        client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        ).status_code
        == 200
    )
    original = VatWorkItemRepository(test_db).get_by_id(item_id)
    assert (original.closed_late, original.chain_closed_late) == (True, True)

    amendment_id = client.post(
        f"/api/v1/vat/work-items/{item_id}/amend", headers=advisor_headers
    ).json()["id"]
    assert (
        client.post(
            f"/api/v1/vat/work-items/{amendment_id}/ready-for-review", headers=advisor_headers
        ).status_code
        == 200
    )
    filed = client.post(
        f"/api/v1/vat/work-items/{amendment_id}/file",
        headers=advisor_headers,
        json={"submission_method": "online"},
    )

    assert filed.status_code == 200, filed.json()
    body = filed.json()
    # Its own act was not late — it had no deadline to miss. The period's was.
    assert body["closed_late"] is None
    assert body["chain_closed_late"] is True


def test_annual_amendment_keeps_the_years_lateness_when_submitted(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
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
    svc.repo.update(
        report.id,
        status=ObligationStatus.AWAITING_VERIFICATION,
        assigned_to=test_user.id,
        tax_due=Decimal("1000"),
        filing_deadline=PAST_DEADLINE,
    )
    assert (
        client.post(
            f"/api/v1/annual-reports/{report.id}/submit", headers=advisor_headers, json={}
        ).status_code
        == 200
    )
    original = svc.repo.get_by_id(report.id)
    assert (original.closed_late, original.chain_closed_late) == (True, True)

    amendment_id = client.post(
        f"/api/v1/annual-reports/{report.id}/amend", headers=advisor_headers
    ).json()["id"]
    # The correction carries no deadline (D-14); the rest of the readiness gate
    # is satisfied the same way the original's was.
    svc.repo.update(
        amendment_id,
        status=ObligationStatus.AWAITING_VERIFICATION,
        assigned_to=test_user.id,
        tax_due=Decimal("1200"),
    )
    submitted = client.post(
        f"/api/v1/annual-reports/{amendment_id}/submit", headers=advisor_headers, json={}
    )

    assert submitted.status_code == 200, submitted.json()
    amendment = svc.repo.get_by_id(amendment_id)
    assert amendment.filing_deadline is None
    assert amendment.closed_late is None
    assert amendment.chain_closed_late is True


def test_advance_amendment_keeps_the_periods_lateness_when_closed(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _, business = create_client_with_business(
        full_name="Chain Lateness Advance", id_number="CHAIN-LATE-ADV"
    )
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=business.client_record_id,
        period="2026-03",
        due_date=PAST_DUE,
        assigned_to=test_user.id,
        turnover_amount=Decimal("50000.00"),
        advance_rate=Decimal("2.5"),
        expected_amount=Decimal("1250.00"),
        status=ObligationStatus.AWAITING_VERIFICATION,
    )
    base = f"/api/v1/clients/{business.client_record_id}/advance-payments"
    assert (
        client.post(
            f"{base}/{payment.id}/status", headers=advisor_headers, json={"status": "submitted"}
        ).json()["closed_late"]
        is True
    )

    amendment_id = client.post(f"{base}/{payment.id}/amend", headers=advisor_headers).json()["id"]
    # An amendment is born in progress, and the graph forbids skipping a stage.
    for status in ("awaiting_verification", "submitted"):
        resp = client.post(
            f"{base}/{amendment_id}/status", headers=advisor_headers, json={"status": status}
        )
        assert resp.status_code == 200, resp.json()

    amendment = AdvancePaymentRepository(test_db).get_by_id(amendment_id)
    assert amendment.due_date is None and amendment.due_date_effective is None
    assert amendment.closed_late is None
    assert amendment.chain_closed_late is True
