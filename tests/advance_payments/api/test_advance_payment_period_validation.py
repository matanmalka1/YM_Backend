"""HTTP-level tests for PeriodStr validation on AdvancePaymentCreateRequest.

Covers: valid YYYY-MM accepted, invalid month rejected (422),
malformed string rejected (422).
"""

import pytest

from app.common.enums import AdvancePaymentFrequency


@pytest.mark.parametrize(
    "period",
    ["2026-13", "garbage", "01-2026", "2026-1", "2026-00", ""],
)
def test_invalid_period_returns_422(
    client, test_db, advisor_headers, period, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Period Validation Client",
        id_number="880000001",
        business_name="Period Validation Business",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    res = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments",
        headers=advisor_headers,
        json={"period": period, "period_months_count": 1},
    )
    assert res.status_code == 422


def test_valid_period_accepted(client, test_db, advisor_headers, create_client_with_business):
    _client, business = create_client_with_business(
        full_name="Period Validation Client",
        id_number="880000001",
        business_name="Period Validation Business",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    res = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments",
        headers=advisor_headers,
        json={"period": "2026-06", "period_months_count": 1},
    )
    assert res.status_code == 201
    assert res.json()["period"] == "2026-06"
