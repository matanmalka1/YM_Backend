from datetime import date
from decimal import Decimal

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.businesses.models.business import Business
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def _business(db) -> Business:
    crm_client = seed_client_identity(db, full_name="AP KPI Client", id_number="APKPI-1")
    business = seed_business(
        db,
        legal_entity_id=crm_client.legal_entity_id,
        business_name="AP KPI Business",
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(business)
    business.client_record_id = crm_client.id
    return business


def _seed_payments(db, client_record_id: int):
    repo = AdvancePaymentRepository(db)
    jan = create_linked_advance_payment(
        db,
        repo=repo,
        client_record_id=client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("100"),
    )
    repo.update_payment(jan, paid_amount=Decimal("80"), status=AdvancePaymentStatus.PAID)

    mar = create_linked_advance_payment(
        db,
        repo=repo,
        client_record_id=client_record_id,
        period="2026-03",
        period_months_count=1,
        due_date=date(2020, 4, 15),  # past due date → timing_status=overdue
        expected_amount=Decimal("50"),
    )
    repo.update_payment(mar, paid_amount=Decimal("0"), status=AdvancePaymentStatus.PENDING)


def test_kpi_endpoint_returns_collection_rate(client, test_db, advisor_headers):
    business = _business(test_db)
    _seed_payments(test_db, business.client_record_id)

    resp = client.get(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/kpi?year=2026",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["client_record_id"] == business.client_record_id
    assert data["year"] == 2026
    assert Decimal(str(data["total_expected"])) == Decimal("150")
    assert Decimal(str(data["total_paid"])) == Decimal("80")
    assert data["collection_rate"] == "53.33"
    assert data["overdue_count"] >= 1
