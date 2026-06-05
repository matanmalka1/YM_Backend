from datetime import date

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from tests.tax_calendar.api.grouped_helpers import (
    PATH,
    add_advance_payment,
    add_vat_item,
    advance_entry,
    headers,
    vat_entry,
)
from tests.tax_calendar.service.linking_helpers import advance_client


def test_vat_linked_item_uses_snapshot_effective_due_date(client, auth_token, test_db, test_user):
    entry = vat_entry(test_db)
    add_vat_item(test_db, entry, test_user.id)
    test_db.commit()

    response = client.get(PATH, headers=headers(auth_token))

    assert response.status_code == 200
    data = response.json()["items"][0]
    assert data["linked_count"] == 1
    assert data["effective_due_date_min"] == "2026-02-20"
    assert data["effective_due_date_max"] == "2026-02-20"


def test_advance_payment_linked_item_uses_snapshot_effective_due_date(client, auth_token, test_db):
    entry = advance_entry(test_db)
    add_advance_payment(test_db, entry)
    test_db.commit()

    response = client.get(PATH, headers=headers(auth_token))

    assert response.status_code == 200
    data = response.json()["items"][0]
    assert data["linked_count"] == 1
    assert data["effective_due_date_min"] == "2026-02-21"
    assert data["effective_due_date_max"] == "2026-02-21"


def test_multiple_linked_rows_return_effective_due_date_min_and_max(client, auth_token, test_db):
    entry = advance_entry(test_db)
    add_advance_payment(test_db, entry, due_date=date(2026, 2, 21))
    add_advance_payment(test_db, entry, due_date=date(2026, 2, 28))
    test_db.commit()

    response = client.get(PATH, headers=headers(auth_token))

    assert response.status_code == 200
    data = response.json()["items"][0]
    assert data["linked_count"] == 2
    assert data["effective_due_date_min"] == "2026-02-21"
    assert data["effective_due_date_max"] == "2026-02-28"


def test_overdue_count_excludes_done_rows(client, auth_token, test_db):
    entry = advance_entry(test_db, 2020)
    open_client = advance_client(test_db)
    done_client = advance_client(test_db)
    for client_record, status in (
        (open_client, AdvancePaymentStatus.PENDING),
        (done_client, AdvancePaymentStatus.PAID),
    ):
        test_db.add(
            AdvancePayment(
                client_record_id=client_record.id,
                period="2020-01",
                period_months_count=1,
                due_date=entry.due_date,
                due_date_effective=date(2020, 2, 15),
                status=status,
                tax_calendar_entry_id=entry.id,
            )
        )
    test_db.commit()

    response = client.get(PATH, headers=headers(auth_token))

    assert response.status_code == 200
    data = response.json()["items"][0]
    assert data["linked_count"] == 2
    assert data["done_count"] == 1
    assert data["open_count"] == 1
    assert data["overdue_count"] == 1
