"""API tests for the server-computed vat_turnover_mismatch flag (detail routes)."""

from datetime import date
from decimal import Decimal
from itertools import count

from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.businesses.models.business import Business
from app.common.enums import AdvancePaymentFrequency, VatType
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from tests.helpers.identity import seed_client_identity

_seq = count(1)


def _business(db, frequency=AdvancePaymentFrequency.MONTHLY) -> Business:
    idx = next(_seq)
    client = seed_client_identity(
        db,
        full_name=f"Mismatch Client {idx}",
        id_number=f"MSM{idx:06d}",
        advance_payment_frequency=frequency,
        advance_rate=Decimal("10"),
    )
    business = Business(
        legal_entity_id=client.legal_entity_id,
        business_name=f"Mismatch Business {idx}",
        opened_at=date.today(),
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    business.client_record_id = client.id
    return business


def _payment(db, business, period, turnover=None, period_months_count=1):
    payment = AdvancePaymentService(db).create_payment_for_client(
        client_record_id=business.client_record_id,
        period=period,
        period_months_count=period_months_count,
        turnover_amount=turnover,
    )
    db.commit()
    return payment


def _vat_item(db, client_id, period, net, user_id, status=VatWorkItemStatus.FILED):
    entry = TaxCalendarMaterializationService(db).ensure_periodic_entry("vat", period, 1)
    amt = Decimal(str(net))
    item = VatWorkItem(
        client_record_id=client_id,
        created_by=user_id,
        period=period,
        period_type=VatType.MONTHLY,
        status=status,
        total_output_vat=amt,
        total_output_net=amt,
        total_input_vat=Decimal("0"),
        net_vat=amt,
        tax_calendar_entry_id=entry.id,
        due_date_original=entry.due_date,
        due_date_effective=entry.due_date,
    )
    db.add(item)
    db.commit()
    return item


def _url(business, payment) -> str:
    return f"/api/v1/clients/{business.client_record_id}/advance-payments/{payment.id}"


def test_mismatch_flagged_when_stored_differs_from_vat(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-03", turnover=Decimal("50000"))
    _vat_item(test_db, business.client_record_id, "2026-03", 60000, test_user.id)

    resp = client.get(_url(business, payment), headers=advisor_headers)

    assert resp.status_code == 200
    mismatch = resp.json()["vat_turnover_mismatch"]
    assert mismatch is not None
    assert Decimal(mismatch["vat_amount"]) == Decimal("60000")
    assert Decimal(mismatch["difference"]) == Decimal("10000")
    assert mismatch["source"] == "vat_filed"


def test_no_mismatch_within_tolerance(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-04", turnover=Decimal("60000.50"))
    _vat_item(test_db, business.client_record_id, "2026-04", 60000, test_user.id)

    resp = client.get(_url(business, payment), headers=advisor_headers)

    assert resp.status_code == 200
    assert resp.json()["vat_turnover_mismatch"] is None


def test_no_mismatch_without_vat_report(client, test_db, advisor_headers):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-05", turnover=Decimal("50000"))

    resp = client.get(_url(business, payment), headers=advisor_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["vat_turnover_mismatch"] is None
    assert body["available_turnover"] is None


def test_unsnapshotted_period_offers_available_not_mismatch(
    client, test_db, advisor_headers, test_user
):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-06")
    _vat_item(test_db, business.client_record_id, "2026-06", 70000, test_user.id)

    resp = client.get(_url(business, payment), headers=advisor_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["vat_turnover_mismatch"] is None
    assert body["available_turnover"] is not None
    assert Decimal(body["available_turnover"]["amount"]) == Decimal("70000")


def test_overview_route_carries_mismatch(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    _payment(test_db, business, "2026-08", turnover=Decimal("10000"))
    _vat_item(test_db, business.client_record_id, "2026-08", 20000, test_user.id)

    resp = client.get(
        f"/api/v1/advance-payments/overview?year=2026&client_record_id={business.client_record_id}",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    items = resp.json()["items"]
    target = next(item for item in items if item["period"] == "2026-08")
    assert target["vat_turnover_mismatch"] is not None
    assert Decimal(target["vat_turnover_mismatch"]["difference"]) == Decimal("10000")


def test_list_route_carries_mismatch(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    _payment(test_db, business, "2026-07", turnover=Decimal("10000"))
    _vat_item(test_db, business.client_record_id, "2026-07", 99000, test_user.id)

    resp = client.get(
        f"/api/v1/clients/{business.client_record_id}/advance-payments?year=2026",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    items = resp.json()["items"]
    target = next(item for item in items if item["period"] == "2026-07")
    assert target["vat_turnover_mismatch"] is not None
    assert Decimal(target["vat_turnover_mismatch"]["difference"]) == Decimal("89000")


# ── The vat_mismatch overview filter ──────────────────────────────────────────
# The filter is SQL (vat_turnover_mismatch_expr); the flag on the row is Python
# (VatTurnoverMismatch.from_comparison). These assert the two agree, which is the
# only thing that keeps a filtered list from showing rows without the marker.


def _overview(client, headers, business, extra=""):
    resp = client.get(
        f"/api/v1/advance-payments/overview?year=2026"
        f"&client_record_id={business.client_record_id}&page_size=50{extra}",
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


def test_filter_keeps_only_rows_carrying_the_flag(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    _payment(test_db, business, "2026-02", turnover=Decimal("10000"))  # mismatch
    _vat_item(test_db, business.client_record_id, "2026-02", 25000, test_user.id)
    _payment(test_db, business, "2026-03", turnover=Decimal("30000.40"))  # within tolerance
    _vat_item(test_db, business.client_record_id, "2026-03", 30000, test_user.id)
    _payment(test_db, business, "2026-04", turnover=Decimal("40000"))  # no VAT return
    _payment(test_db, business, "2026-05")  # unsnapshotted

    body = _overview(client, advisor_headers, business, extra="&vat_mismatch=true")

    assert [item["period"] for item in body["items"]] == ["2026-02"]
    assert body["total"] == 1
    assert all(item["vat_turnover_mismatch"] is not None for item in body["items"])
    # KPIs are filtered with the rows, not over the unfiltered year.
    assert Decimal(body["total_expected"]) == Decimal("1000.00")


def test_filter_false_drops_the_mismatched_rows(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    _payment(test_db, business, "2026-02", turnover=Decimal("10000"))
    _vat_item(test_db, business.client_record_id, "2026-02", 25000, test_user.id)
    _payment(test_db, business, "2026-03", turnover=Decimal("30000"))
    _vat_item(test_db, business.client_record_id, "2026-03", 30000, test_user.id)

    body = _overview(client, advisor_headers, business, extra="&vat_mismatch=false")

    assert [item["period"] for item in body["items"]] == ["2026-03"]
    assert all(item["vat_turnover_mismatch"] is None for item in body["items"])


def test_unfiled_vat_return_still_counts_as_a_mismatch(client, test_db, advisor_headers, test_user):
    """A period in review resolves to vat_pending — weaker source, same disagreement."""
    business = _business(test_db)
    _payment(test_db, business, "2026-06", turnover=Decimal("10000"))
    _vat_item(
        test_db,
        business.client_record_id,
        "2026-06",
        90000,
        test_user.id,
        status=VatWorkItemStatus.READY_FOR_REVIEW,
    )

    body = _overview(client, advisor_headers, business, extra="&vat_mismatch=true")

    assert [item["period"] for item in body["items"]] == ["2026-06"]
    assert body["items"][0]["vat_turnover_mismatch"]["source"] == "vat_pending"


def test_half_covered_bimonthly_period_is_not_a_mismatch(
    client, test_db, advisor_headers, test_user
):
    """Same all-or-nothing coverage rule as the read path: one of two months is not a figure."""
    business = _business(test_db, frequency=AdvancePaymentFrequency.BIMONTHLY)
    _payment(test_db, business, "2026-01", turnover=Decimal("10000"), period_months_count=2)
    _vat_item(test_db, business.client_record_id, "2026-01", 90000, test_user.id)

    body = _overview(client, advisor_headers, business, extra="&vat_mismatch=true")

    assert body["items"] == []
    assert _overview(client, advisor_headers, business)["items"][0]["vat_turnover_mismatch"] is None


def test_fully_covered_bimonthly_period_sums_both_months(
    client, test_db, advisor_headers, test_user
):
    business = _business(test_db, frequency=AdvancePaymentFrequency.BIMONTHLY)
    _payment(test_db, business, "2026-03", turnover=Decimal("10000"), period_months_count=2)
    _vat_item(test_db, business.client_record_id, "2026-03", 20000, test_user.id)
    _vat_item(test_db, business.client_record_id, "2026-04", 5000, test_user.id)

    body = _overview(client, advisor_headers, business, extra="&vat_mismatch=true")

    assert [item["period"] for item in body["items"]] == ["2026-03"]
    assert Decimal(body["items"][0]["vat_turnover_mismatch"]["vat_amount"]) == Decimal("25000")


def test_batches_report_the_mismatch_count(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    _payment(test_db, business, "2026-09", turnover=Decimal("10000"))
    _vat_item(test_db, business.client_record_id, "2026-09", 80000, test_user.id)
    _payment(test_db, business, "2026-10", turnover=Decimal("10000"))
    _vat_item(test_db, business.client_record_id, "2026-10", 10000, test_user.id)

    resp = client.get(
        f"/api/v1/advance-payments/overview/batches?year=2026"
        f"&client_record_id={business.client_record_id}",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    by_month = {batch["month"]: batch for batch in resp.json()}
    assert by_month[9]["vat_mismatch_count"] == 1
    assert by_month[10]["vat_mismatch_count"] == 0
