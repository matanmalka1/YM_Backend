from datetime import date
from decimal import Decimal

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_list_advance_payments_paginates(
    client, test_db, advisor_headers, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Advance Payment Client", id_number="444444444"
    )
    repo = AdvancePaymentRepository(test_db)
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-01",
        period_months_count=1,
        due_date=date(2026, 2, 15),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-02",
        period_months_count=1,
        due_date=date(2026, 3, 15),
    )
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-03",
        period_months_count=1,
        due_date=date(2026, 4, 15),
    )
    # Extra year entry should be filtered out
    create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2025-12",
        period_months_count=1,
        due_date=date(2026, 1, 15),
    )

    response = client.get(
        f"/api/v1/clients/{business.client_record_id}/advance-payments?year=2026&page=1&page_size=2",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert [item["period"] for item in data["items"]] == ["2026-01", "2026-02"]

    second_page = client.get(
        f"/api/v1/clients/{business.client_record_id}/advance-payments?year=2026&page=2&page_size=2",
        headers=advisor_headers,
    )
    assert second_page.status_code == 200
    assert [item["period"] for item in second_page.json()["items"]] == ["2026-03"]


def test_update_advance_payment_success(
    client, test_db, advisor_headers, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Advance Payment Client", id_number="444444444"
    )
    repo = AdvancePaymentRepository(test_db)
    payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-05",
        period_months_count=1,
        due_date=date(2026, 6, 15),
        expected_amount=500.0,
    )

    response = client.patch(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/{payment.id}",
        headers=advisor_headers,
        json={"paid_amount": 500.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "awaiting_verification"
    assert Decimal(str(data["paid_amount"])) == Decimal("500.00")
    assert data["updated_at"] is not None


def test_update_advance_payment_rejects_server_owned_status(
    client, test_db, advisor_headers, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Advance Payment Client", id_number="444444444"
    )
    repo = AdvancePaymentRepository(test_db)
    payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-07",
        period_months_count=1,
        due_date=date(2026, 8, 15),
    )

    response = client.patch(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/{payment.id}",
        headers=advisor_headers,
        json={"status": "paid"},
    )

    assert response.status_code == 422


def test_update_advance_payment_not_found_returns_404(
    client, test_db, advisor_headers, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Advance Payment Client", id_number="444444444"
    )
    response = client.patch(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/999",
        headers=advisor_headers,
        json={"notes": "לא קיים"},
    )

    data = response.json()
    assert response.status_code == 404
    assert data["error"]["code"] == "ADVANCE_PAYMENT.NOT_FOUND"
    assert isinstance(data["error"]["message"], str)


def test_list_advance_payments_missing_client_returns_404(client, advisor_headers):
    response = client.get(
        "/api/v1/clients/999/advance-payments?year=2026",
        headers=advisor_headers,
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "ADVANCE_PAYMENT.CLIENT_RECORD_NOT_FOUND"
    assert data["error"]["message"] == "רשומת לקוח 999 לא נמצאה"
