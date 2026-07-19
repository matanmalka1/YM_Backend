from datetime import date

from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_get_advance_payment_by_client_and_id(
    client, test_db, advisor_headers, create_client_with_business
):
    crm_client, _business = create_client_with_business(full_name="Advance Detail Client")
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=crm_client.id,
        period="2025-01",
        due_date=date(2025, 2, 15),
        notes="Deep link target",
    )
    test_db.commit()

    response = client.get(
        f"/api/v1/clients/{crm_client.id}/advance-payments/{payment.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == payment.id
    assert response.json()["notes"] == "Deep link target"


def test_get_advance_payment_hides_cross_client_record(
    client, test_db, advisor_headers, create_client_with_business
):
    owner, _ = create_client_with_business(full_name="Advance Owner")
    other, _ = create_client_with_business(full_name="Other Advance Client")
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=owner.id,
        period="2025-03",
        due_date=date(2025, 4, 15),
    )
    test_db.commit()

    response = client.get(
        f"/api/v1/clients/{other.id}/advance-payments/{payment.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 404
