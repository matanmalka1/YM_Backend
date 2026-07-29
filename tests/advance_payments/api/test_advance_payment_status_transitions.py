"""W3: the advisor transition route, the closing gate, and the full lock (D-13–D-16, D-20)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.audit.audit_constants import ENTITY_ADVANCE_PAYMENT, entity_action
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.common.enums import ObligationStatus
from tests.helpers.tax_calendar_links import create_linked_advance_payment

PAST_DUE = date(2020, 1, 15)
FUTURE_DUE = date(2035, 1, 15)


def _url(client_record_id: int, payment_id: int, suffix: str = "") -> str:
    return f"/api/v1/clients/{client_record_id}/advance-payments/{payment_id}{suffix}"


def _make_payment(test_db, business, **kwargs):
    kwargs.setdefault("period", "2026-03")
    kwargs.setdefault("due_date", FUTURE_DUE)
    return create_linked_advance_payment(
        test_db,
        client_record_id=business.client_record_id,
        **kwargs,
    )


def _closable_kwargs(user_id: int) -> dict:
    return {
        "assigned_to": user_id,
        "turnover_amount": Decimal("50000.00"),
        "advance_rate": Decimal("2.5"),
        "expected_amount": Decimal("1250.00"),
        "status": ObligationStatus.AWAITING_VERIFICATION,
    }


# ─── Transition steps ─────────────────────────────────────────────────────────


def test_forward_one_step(client, test_db, advisor_headers, create_client_with_business):
    _c, business = create_client_with_business(full_name="Adv Step", id_number="ADV-TR-001")
    payment = _make_payment(test_db, business)

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "input_received"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "input_received"


def test_transitions_still_carry_the_blanket_advisor_restriction_pending_d17(
    client, test_db, secretary_headers, create_client_with_business
):
    """Pins the *interim* state, not the target one.

    D-17/§4.1.9 names advance payments as the outlier whose blanket advisor-only
    write restriction retires: a secretary may move an obligation through the
    working stages, and only an advisor closes, sends back, cancels, amends or
    deletes. A forward step to `input_received` is exactly the clerical move
    D-17 hands to the secretary — so this 403 is wrong under the target model
    and is expected to flip.

    It cannot flip by relaxing `require_role` on the route: `POST /status`
    multiplexes forward, backward, cancel and close behind one endpoint, so
    authorisation has to become per-transition. VAT is the model — separate
    routes per act, `ready-for-review` open to both roles, `send-back` advisor
    only.

    **Scheduled for W7.** When D-17 lands, delete this test and assert the split.
    """
    _c, business = create_client_with_business(full_name="Adv Role", id_number="ADV-TR-002")
    payment = _make_payment(test_db, business)

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=secretary_headers,
        json={"status": "input_received"},
    )

    assert resp.status_code == 403


def test_skip_stage_rejected(client, test_db, advisor_headers, create_client_with_business):
    _c, business = create_client_with_business(full_name="Adv Skip", id_number="ADV-TR-003")
    payment = _make_payment(test_db, business)

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "in_progress"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.INVALID_TRANSITION"


def test_backward_requires_note(client, test_db, advisor_headers, create_client_with_business):
    _c, business = create_client_with_business(full_name="Adv Back", id_number="ADV-TR-004")
    payment = _make_payment(test_db, business, status=ObligationStatus.IN_PROGRESS)
    url = _url(business.client_record_id, payment.id, "/status")

    without_note = client.post(url, headers=advisor_headers, json={"status": "input_received"})
    with_note = client.post(
        url, headers=advisor_headers, json={"status": "input_received", "note": "חסר חומר"}
    )

    assert without_note.status_code == 400
    assert without_note.json()["error"]["code"] == "OBLIGATION.TRANSITION_REASON_REQUIRED"
    assert with_note.status_code == 200
    assert with_note.json()["status"] == "input_received"


def test_cancel_from_any_open_stage(client, test_db, advisor_headers, create_client_with_business):
    _c, business = create_client_with_business(full_name="Adv Cancel", id_number="ADV-TR-005")
    payment = _make_payment(test_db, business)

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "canceled"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "canceled"


# ─── The closing gate ─────────────────────────────────────────────────────────


def test_close_blocked_when_gates_missing(
    client, test_db, advisor_headers, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv Gate", id_number="ADV-TR-006")
    payment = _make_payment(test_db, business, status=ObligationStatus.AWAITING_VERIFICATION)

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "submitted"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ADVANCE_PAYMENT.NOT_READY"


def test_close_records_who_when_and_late(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv Close", id_number="ADV-TR-007")
    payment = _make_payment(test_db, business, due_date=PAST_DUE, **_closable_kwargs(test_user.id))

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "submitted"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["closed_by"] == test_user.id
    assert body["closed_at"] is not None
    assert body["closed_late"] is True

    audit = test_db.scalars(
        select(EntityAuditLog).where(
            EntityAuditLog.entity_type == ENTITY_ADVANCE_PAYMENT,
            EntityAuditLog.entity_id == payment.id,
            EntityAuditLog.action == entity_action(ENTITY_ADVANCE_PAYMENT, "status_changed"),
        )
    ).all()
    assert len(audit) == 1
    assert audit[0].metadata_json["closed_by"] == test_user.id
    assert audit[0].metadata_json["closed_late"] is True


def test_close_on_time_records_false_never_null(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    # due_date is NOT NULL on advances, so closed_late is always a real bool here;
    # NULL is reserved for records with no due date (D-32) — amendments, in W4.
    _c, business = create_client_with_business(full_name="Adv OnTime", id_number="ADV-TR-008")
    payment = _make_payment(
        test_db, business, due_date=FUTURE_DUE, **_closable_kwargs(test_user.id)
    )

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "submitted"},
    )

    assert resp.status_code == 200
    assert resp.json()["closed_late"] is False


def test_closed_late_prefers_effective_due_date(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    # INV-05: the original due date is past, but the effective one is in the
    # future — closing now is NOT late.
    _c, business = create_client_with_business(full_name="Adv Eff", id_number="ADV-TR-019")
    payment = _make_payment(test_db, business, due_date=PAST_DUE, **_closable_kwargs(test_user.id))
    payment.due_date_effective = FUTURE_DUE
    test_db.flush()

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "submitted"},
    )

    assert resp.status_code == 200
    assert resp.json()["closed_late"] is False


def test_part_paid_period_closes(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    # D-16: payment in full is not a gate — the advisor closes with an
    # outstanding difference.
    _c, business = create_client_with_business(full_name="Adv Partial", id_number="ADV-TR-009")
    payment = _make_payment(
        test_db,
        business,
        paid_amount=Decimal("400.00"),
        **_closable_kwargs(test_user.id),
    )

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "submitted"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted"
    assert Decimal(resp.json()["delta"]) > 0


# ─── Readiness endpoint ───────────────────────────────────────────────────────


def test_readiness_lists_every_missing_gate(
    client, test_db, advisor_headers, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv Ready", id_number="ADV-TR-010")
    payment = _make_payment(test_db, business)

    resp = client.get(
        _url(business.client_record_id, payment.id, "/readiness"), headers=advisor_headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["advance_payment_id"] == payment.id
    assert body["is_ready"] is False
    # assignee + turnover + no way to derive an expected amount
    assert len(body["issues"]) == 3


def test_readiness_ready_row(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv Ready2", id_number="ADV-TR-011")
    payment = _make_payment(test_db, business, **_closable_kwargs(test_user.id))

    resp = client.get(
        _url(business.client_record_id, payment.id, "/readiness"), headers=advisor_headers
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "advance_payment_id": payment.id,
        "is_ready": True,
        "issues": [],
    }


# ─── The full lock (D-13) ─────────────────────────────────────────────────────


def _closed_payment(test_db, business, user_id, **kwargs):
    kwargs.setdefault("paid_amount", Decimal("1250.00"))
    return _make_payment(
        test_db,
        business,
        assigned_to=user_id,
        turnover_amount=Decimal("50000.00"),
        advance_rate=Decimal("2.5"),
        expected_amount=Decimal("1250.00"),
        status=ObligationStatus.SUBMITTED,
        **kwargs,
    )


def test_patch_locked_after_close(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv Lock", id_number="ADV-TR-012")
    payment = _closed_payment(test_db, business, test_user.id)

    for body in ({"notes": "עדכון"}, {"paid_amount": "1.00"}, {"assigned_to": None}):
        resp = client.patch(
            _url(business.client_record_id, payment.id), headers=advisor_headers, json=body
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"


def test_delete_locked_after_close(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv LockDel", id_number="ADV-TR-013")
    payment = _closed_payment(test_db, business, test_user.id)

    resp = client.request(
        "DELETE",
        _url(business.client_record_id, payment.id),
        headers=advisor_headers,
        json={"reason": "ניסיון מחיקה"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"
    assert AdvancePaymentRepository(test_db).get_by_id(payment.id) is not None


def test_refresh_turnover_locked_after_close(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv LockRef", id_number="ADV-TR-014")
    payment = _closed_payment(test_db, business, test_user.id)

    resp = client.post(
        _url(business.client_record_id, payment.id, "/refresh-turnover"),
        headers=advisor_headers,
        json={"confirm_pending": False},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"


def test_no_transition_out_of_submitted(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv LockTr", id_number="ADV-TR-015")
    payment = _closed_payment(test_db, business, test_user.id)

    resp = client.post(
        _url(business.client_record_id, payment.id, "/status"),
        headers=advisor_headers,
        json={"status": "awaiting_verification", "note": "החזרה"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"


def test_bulk_refresh_skips_closed(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv BulkRef", id_number="ADV-TR-016")
    payment = _closed_payment(test_db, business, test_user.id)

    resp = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/refresh-turnover",
        headers=advisor_headers,
        json={"payment_ids": [payment.id]},
    )

    assert resp.status_code == 200
    assert resp.json()["skipped_closed"] == 1
    assert resp.json()["refreshed"] == 0


def test_bulk_mark_paid_skips_closed(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    # A closed-but-underpaid period must be skipped as closed, never topped up.
    _c, business = create_client_with_business(full_name="Adv BulkPay", id_number="ADV-TR-018")
    payment = _closed_payment(test_db, business, test_user.id, paid_amount=Decimal("100.00"))

    resp = client.post(
        "/api/v1/advance-payments/bulk-mark-paid",
        headers={**advisor_headers, "X-Idempotency-Key": "w3-lock-bulk-paid-1"},
        json={"payment_ids": [payment.id]},
    )

    assert resp.status_code == 200
    assert resp.json()["updated"] == []
    assert resp.json()["skipped"] == [{"id": payment.id, "reason": "closed"}]
    test_db.refresh(payment)
    assert payment.paid_amount == Decimal("100.00")


# ─── assigned_to round-trip ───────────────────────────────────────────────────


def test_assigned_to_patch_round_trip(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    _c, business = create_client_with_business(full_name="Adv Assign", id_number="ADV-TR-017")
    payment = _make_payment(test_db, business)
    url = _url(business.client_record_id, payment.id)

    resp = client.patch(url, headers=advisor_headers, json={"assigned_to": test_user.id})
    assert resp.status_code == 200
    assert resp.json()["assigned_to"] == test_user.id

    detail = client.get(url, headers=advisor_headers)
    assert detail.json()["assigned_to"] == test_user.id
