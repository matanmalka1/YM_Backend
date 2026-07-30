from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.common.enums import ObligationStatus
from app.utils.time_utils import utcnow
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


def _submitted_original(test_db, *, client_record_id: int, period: str, assigned_to: int):
    original = create_linked_advance_payment(
        test_db,
        client_record_id=client_record_id,
        period=period,
        due_date=date(2026, 12, 15),
        expected_amount=Decimal("1000.00"),
        paid_amount=Decimal("1000.00"),
        assigned_to=assigned_to,
        status=ObligationStatus.SUBMITTED,
    )
    test_db.commit()
    return original


def _amend(client, headers, client_record_id: int, payment_id: int) -> int:
    resp = client.post(
        f"/api/v1/clients/{client_record_id}/advance-payments/{payment_id}/amend",
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_withdrawing_an_amendment_restores_the_original_and_frees_the_chain(
    client, test_db, advisor_headers, create_client_with_business, test_user
):
    """The whole point of the act: the period comes back, and can be corrected again.

    The second amendment is what proves the ``amends_id`` slot was freed — its
    unique index excludes deleted rows only, so a withdrawal that moved the
    correction to ``CANCELED`` instead would fail here on a unique violation.
    """
    crm_client, _business = create_client_with_business(
        full_name="Advance Withdraw Client", id_number="ADV-WD-001"
    )
    original = _submitted_original(
        test_db, client_record_id=crm_client.id, period="2026-08", assigned_to=test_user.id
    )
    amendment_id = _amend(client, advisor_headers, crm_client.id, original.id)

    resp = client.post(
        f"/api/v1/clients/{crm_client.id}/advance-payments/{amendment_id}/withdraw",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == original.id
    assert body["status"] == ObligationStatus.SUBMITTED.value
    assert body["superseded_at"] is None
    assert body["amends_id"] is None
    assert _amend(client, advisor_headers, crm_client.id, original.id) != amendment_id


def test_a_withdrawn_amendment_stays_in_the_chain(
    client, test_db, advisor_headers, create_client_with_business, test_user
):
    """The one read that shows what happened, not what counts."""
    crm_client, _business = create_client_with_business(
        full_name="Advance Withdraw Client", id_number="ADV-WD-002"
    )
    original = _submitted_original(
        test_db, client_record_id=crm_client.id, period="2026-09", assigned_to=test_user.id
    )
    amendment_id = _amend(client, advisor_headers, crm_client.id, original.id)
    assert (
        client.post(
            f"/api/v1/clients/{crm_client.id}/advance-payments/{amendment_id}/withdraw",
            headers=advisor_headers,
        ).status_code
        == 200
    )

    chain = client.get(
        f"/api/v1/clients/{crm_client.id}/advance-payments/{original.id}/chain",
        headers=advisor_headers,
    )

    assert chain.status_code == 200
    records = {record["id"]: record for record in chain.json()}
    assert set(records) == {original.id, amendment_id}
    assert records[amendment_id]["is_withdrawn"] is True
    assert records[original.id]["is_withdrawn"] is False
    assert records[original.id]["superseded_at"] is None


def test_a_correction_that_lands_before_the_lock_stops_the_second_one(
    client, test_db, advisor_headers, create_client_with_business, test_user
):
    """The gate has to see the DB, not the row that was read before the lock.

    The service resolves the payment through its client scope, locks it, and only
    then checks ``assert_amendable`` — the check exists for the correction that
    lands while it waits for the lock. The setup recreates the only thing that
    makes it meaningful: the original is already in the session's identity map
    with ``superseded_at IS NULL`` when the request starts, and the DB says it is
    already corrected.

    A true two-transaction race cannot be staged here — the suite runs one
    connection inside one transaction — so this drives the same divergence
    directly. Without the locked re-read, the second request passes the gate and
    inserts, and the period ends up with two tips (or a 500 from the unique index
    on ``amends_id``) instead of a 409.
    """
    crm_client, _business = create_client_with_business(
        full_name="Advance Amend Race Client", id_number="ADV-AMEND-RACE-001"
    )
    original = _submitted_original(
        test_db, client_record_id=crm_client.id, period="2026-11", assigned_to=test_user.id
    )
    # Load it, then move it underneath the ORM: the loaded object keeps the state
    # it was read with, exactly as it would while another transaction opens a
    # correction.
    test_db.refresh(original)
    test_db.execute(
        text("UPDATE advance_payments SET superseded_at = :now WHERE id = :id"),
        {"now": utcnow(), "id": original.id},
    )
    assert original.superseded_at is None

    resp = client.post(
        f"/api/v1/clients/{crm_client.id}/advance-payments/{original.id}/amend",
        headers=advisor_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "OBLIGATION.ALREADY_AMENDED"
    assert (
        test_db.execute(
            text("SELECT count(*) FROM advance_payments WHERE amends_id = :id"),
            {"id": original.id},
        ).scalar()
        == 0
    )


def test_withdrawing_a_payment_that_is_not_an_amendment_is_rejected(
    client, test_db, advisor_headers, create_client_with_business, test_user
):
    """Withdrawing undoes a link; a standalone payment has none to undo."""
    crm_client, _business = create_client_with_business(
        full_name="Advance Withdraw Client", id_number="ADV-WD-003"
    )
    original = _submitted_original(
        test_db, client_record_id=crm_client.id, period="2026-10", assigned_to=test_user.id
    )

    resp = client.post(
        f"/api/v1/clients/{crm_client.id}/advance-payments/{original.id}/withdraw",
        headers=advisor_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.NOT_AN_AMENDMENT"
