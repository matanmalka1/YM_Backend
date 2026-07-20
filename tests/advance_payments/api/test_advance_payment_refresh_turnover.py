"""API tests for the /{payment_id}/refresh-turnover command."""

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


def _business(db, advance_rate=Decimal("10")) -> Business:
    idx = next(_seq)
    client = seed_client_identity(
        db,
        full_name=f"Refresh API Client {idx}",
        id_number=f"RFA{idx:06d}",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
        advance_rate=advance_rate,
    )
    business = Business(
        legal_entity_id=client.legal_entity_id,
        business_name=f"Refresh API Business {idx}",
        opened_at=date.today(),
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    business.client_record_id = client.id
    return business


def _payment(db, business, period):
    payment = AdvancePaymentService(db).create_payment_for_client(
        client_record_id=business.client_record_id,
        period=period,
        period_months_count=1,
    )
    db.commit()
    return payment


def _vat_item(db, client_id, period, net, user_id, status=VatWorkItemStatus.FILED):
    mat = TaxCalendarMaterializationService(db)
    entry = mat.ensure_periodic_entry("vat", period, 1)
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
    db.refresh(item)
    return item


def _url(business, payment) -> str:
    return (
        f"/api/v1/clients/{business.client_record_id}"
        f"/advance-payments/{payment.id}/refresh-turnover"
    )


def test_refresh_turnover_snapshots_filed_report(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-10")
    _vat_item(test_db, business.client_record_id, "2026-10", 70000, test_user.id)

    resp = client.post(_url(business, payment), json={}, headers=advisor_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["turnover_source"] == "vat_filed"
    assert data["turnover_snapshot_at"] is not None
    assert Decimal(data["turnover_amount"]) == Decimal("70000")
    assert Decimal(data["calculated_amount"]) == Decimal("7000.00")
    assert Decimal(data["expected_amount"]) == Decimal("7000.00")


def test_refresh_turnover_404_when_no_vat_report(client, test_db, advisor_headers):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-11")

    resp = client.post(_url(business, payment), json={}, headers=advisor_headers)

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ADVANCE_PAYMENT.VAT_TURNOVER_NOT_FOUND"


def test_refresh_turnover_409_when_vat_not_filed(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-09")
    _vat_item(
        test_db,
        business.client_record_id,
        "2026-09",
        50000,
        test_user.id,
        VatWorkItemStatus.READY_FOR_REVIEW,
    )

    resp = client.post(_url(business, payment), json={}, headers=advisor_headers)

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ADVANCE_PAYMENT.VAT_NOT_FILED"

    confirmed = client.post(
        _url(business, payment), json={"confirm_pending": True}, headers=advisor_headers
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["turnover_source"] == "vat_pending"


def _bulk_url(business) -> str:
    return f"/api/v1/clients/{business.client_record_id}/advance-payments/refresh-turnover"


def test_bulk_refresh_reports_each_skip_reason(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    filed = _payment(test_db, business, "2026-01")
    pending = _payment(test_db, business, "2026-02")
    absent = _payment(test_db, business, "2026-03")
    _vat_item(test_db, business.client_record_id, "2026-01", 60000, test_user.id)
    _vat_item(
        test_db,
        business.client_record_id,
        "2026-02",
        50000,
        test_user.id,
        VatWorkItemStatus.READY_FOR_REVIEW,
    )

    resp = client.post(
        _bulk_url(business),
        json={"payment_ids": [filed.id, pending.id, absent.id]},
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "refreshed": 1,
        "skipped_no_vat": 1,
        "skipped_not_filed": 1,
        "skipped_paid": 0,
    }


def test_bulk_refresh_rejects_empty_id_list(client, test_db, advisor_headers):
    business = _business(test_db)

    resp = client.post(_bulk_url(business), json={"payment_ids": []}, headers=advisor_headers)

    assert resp.status_code == 422


def test_bulk_refresh_404_for_another_clients_payment(client, test_db, advisor_headers):
    business = _business(test_db)
    other = _business(test_db)
    theirs = _payment(test_db, other, "2026-04")

    resp = client.post(
        _bulk_url(business), json={"payment_ids": [theirs.id]}, headers=advisor_headers
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ADVANCE_PAYMENT.NOT_FOUND"


def test_bulk_refresh_secretary_forbidden(client, test_db, secretary_headers):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-05")

    resp = client.post(
        _bulk_url(business), json={"payment_ids": [payment.id]}, headers=secretary_headers
    )

    assert resp.status_code == 403


def test_refresh_turnover_secretary_forbidden(client, test_db, secretary_headers):
    business = _business(test_db)
    payment = _payment(test_db, business, "2026-12")

    resp = client.post(_url(business, payment), json={}, headers=secretary_headers)

    assert resp.status_code == 403
