"""API tests for the /prefill-turnover endpoint."""

from datetime import date
from decimal import Decimal
from itertools import count

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
        full_name=f"Prefill API Client {idx}",
        id_number=f"PFA{idx:06d}",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    business = Business(
        legal_entity_id=client.legal_entity_id,
        business_name=f"Prefill API Business {idx}",
        opened_at=date.today(),
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    business.client_record_id = client.id
    return business


def _filed_vat(db, client_id, period, net, user_id):
    mat = TaxCalendarMaterializationService(db)
    entry = mat.ensure_periodic_entry("vat", period, 1)
    amt = Decimal(str(net))
    item = VatWorkItem(
        client_record_id=client_id,
        created_by=user_id,
        period=period,
        period_type=VatType.MONTHLY,
        status=VatWorkItemStatus.FILED,
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


def test_prefill_turnover_returns_filed(client, test_db, advisor_headers, test_user):
    business = _business(test_db)
    item = _filed_vat(test_db, business.client_record_id, "2026-10", 70000, test_user.id)

    resp = client.get(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/prefill-turnover"
        "?period=2026-10&period_months_count=1",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "vat_filed"
    assert Decimal(data["turnover_amount"]) == Decimal("70000")
    assert data["vat_work_item_id"] == item.id


def test_prefill_turnover_returns_none_when_no_vat(client, test_db, advisor_headers):
    business = _business(test_db)

    resp = client.get(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/prefill-turnover"
        "?period=2026-11&period_months_count=1",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "none"
    assert data["turnover_amount"] is None
    assert data["vat_work_item_id"] is None


def test_prefill_turnover_secretary_forbidden(client, test_db, secretary_headers):
    business = _business(test_db)

    resp = client.get(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/prefill-turnover"
        "?period=2026-12&period_months_count=1",
        headers=secretary_headers,
    )

    assert resp.status_code == 403
