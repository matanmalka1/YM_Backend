from datetime import date
from decimal import Decimal

from app.common.enums import ObligationStatus
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_create_amendment_returns_null_due_date(
    client,
    test_db,
    advisor_headers,
    create_client_with_business,
    test_user,
):
    crm_client, _business = create_client_with_business(
        full_name="Advance Amendment Client",
        id_number="ADV-AMEND-001",
    )
    original = create_linked_advance_payment(
        test_db,
        client_record_id=crm_client.id,
        period="2026-01",
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("1000.00"),
        paid_amount=Decimal("1000.00"),
        turnover_amount=Decimal("50000.00"),
        advance_rate=Decimal("2.00"),
        calculated_amount=Decimal("1000.00"),
        assigned_to=test_user.id,
        status=ObligationStatus.SUBMITTED,
    )
    test_db.commit()

    response = client.post(
        f"/api/v1/clients/{crm_client.id}/advance-payments/{original.id}/amend",
        headers=advisor_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["amends_id"] == original.id
    assert body["status"] == ObligationStatus.IN_PROGRESS.value
    assert body["due_date"] is None
    assert body["due_date_effective"] is None
    assert body["timing_status"] == "not_applicable"

    overview = client.get(
        "/api/v1/advance-payments/overview?year=2026&page=1&page_size=50",
        headers=advisor_headers,
    )

    assert overview.status_code == 200
    overview_amendment = next(item for item in overview.json()["items"] if item["id"] == body["id"])
    assert overview_amendment["due_date"] is None
    assert overview_amendment["timing_status"] == "not_applicable"

    for timing_status in ("on_time", "overdue"):
        filtered = client.get(
            (
                "/api/v1/advance-payments/overview"
                f"?year=2026&timing_status={timing_status}&page=1&page_size=50"
            ),
            headers=advisor_headers,
        )

        assert filtered.status_code == 200
        assert body["id"] not in {item["id"] for item in filtered.json()["items"]}
