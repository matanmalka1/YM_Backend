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


def _business(db) -> Business:
    idx = next(_seq)
    client = seed_client_identity(
        db,
        full_name=f"Mismatch Client {idx}",
        id_number=f"MSM{idx:06d}",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
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


def _payment(db, business, period, turnover=None):
    payment = AdvancePaymentService(db).create_payment_for_client(
        client_record_id=business.client_record_id,
        period=period,
        period_months_count=1,
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
