"""HTTP-level tests for PeriodStr validation on AdvancePaymentCreateRequest.

Covers: valid YYYY-MM accepted, invalid month rejected (422),
malformed string rejected (422).
"""

from datetime import date

import pytest

from tests.helpers.identity import seed_business, seed_client_identity


def _business(test_db):
    from app.common.enums import AdvancePaymentFrequency

    client = seed_client_identity(
        test_db,
        full_name="Period Validation Client",
        id_number="880000001",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    business = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name="Period Validation Business",
        opened_at=date.today(),
    )
    test_db.commit()
    test_db.refresh(business)
    business.client_record_id = client.id
    return business


@pytest.mark.parametrize(
    "period",
    ["2026-13", "garbage", "01-2026", "2026-1", "2026-00", ""],
)
def test_invalid_period_returns_422(client, test_db, advisor_headers, period):
    business = _business(test_db)
    res = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments",
        headers=advisor_headers,
        json={"period": period, "period_months_count": 1},
    )
    assert res.status_code == 422


def test_valid_period_accepted(client, test_db, advisor_headers):
    business = _business(test_db)
    res = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments",
        headers=advisor_headers,
        json={"period": "2026-06", "period_months_count": 1},
    )
    assert res.status_code == 201
    assert res.json()["period"] == "2026-06"
