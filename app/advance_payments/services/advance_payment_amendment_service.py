"""Correcting a closed advance payment, by creating a second row for it (D-10, D-21).

Advance payments had neither half of this. They had no lock to correct *around*
until W3 gave them one, and no amendment mechanism at all — the status was
derived from money, so a figure that moved simply moved the status with it. Now
that closing is an act a person performs and the record is frozen after it, a
wrong figure needs somewhere to go.

The copy is shallow, and that is not an omission: an advance's figures are its
own columns. There are no invoices or lines to carry — only the turnover, the
rate, and what was expected against what was paid.
"""

from app.advance_payments.models.advance_payment import AdvancePayment
from app.audit.audit_constants import (
    ACTION_ADVANCE_PAYMENT_AMENDED,
    ACTION_ADVANCE_PAYMENT_AMENDMENT_WITHDRAWN,
    ENTITY_ADVANCE_PAYMENT,
)
from app.common.enums import ObligationStatus
from app.common.obligation_chain import (
    assert_amendable,
    assert_withdrawable,
    copy_for_amendment,
    select_chain,
    withdraw_amendment,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


def create_amendment(
    service,
    *,
    client_record_id: int,
    payment_id: int,
    actor_id: int,
    actor_name: str | None = None,
) -> AdvancePayment:
    """Open a correction of a closed advance period.

    Client scope is resolved first, through the domain's own scoped read — the
    lock is taken by primary key and would not check ownership. The original is
    then re-read **under the lock**, and the gate is checked against that row:
    two advisors pressing "amend" on the same period would otherwise both pass
    it and both insert, and only the unique index on ``amends_id`` would stop the
    second — as a 500, rather than the conflict ``assert_amendable`` already
    knows how to raise. The re-read repopulates the row the scoped read just put
    in the identity map, so the gate sees the database and not what was read
    before the wait.
    """
    requested = service.get_payment_for_client(client_record_id, payment_id)

    original = service.repo.get_by_id_for_update(requested.id)
    if original is None:
        raise NotFoundError(
            f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
            ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
        )
    assert_amendable(original)

    amendment = service.repo.create_amendment(
        original,
        fields={
            # No per-domain exclusions. The payment facts — amount, date, method,
            # reference — describe money that actually reached the authority for
            # this period, so they are the advance's material, in the same sense
            # that invoices are a VAT period's. Only the closing act itself is
            # withheld, and that is already in the shared exclusion set.
            **copy_for_amendment(original),
            # D-21: the material already exists, so nothing is being waited for.
            "status": ObligationStatus.IN_PROGRESS,
        },
    )

    service._audit.record_action(
        ENTITY_ADVANCE_PAYMENT,
        amendment.id,
        actor_id,
        ACTION_ADVANCE_PAYMENT_AMENDED,
        new_value={"amends_id": original.id, "period": amendment.period},
        actor_display_name=actor_name,
        metadata_json=service._audit_metadata(amendment),
    )

    return amendment


def withdraw(
    service,
    *,
    client_record_id: int,
    payment_id: int,
    actor_id: int,
    actor_name: str | None = None,
) -> AdvancePayment:
    """Take back an open correction and return the period to its closed payment.

    Client scope is resolved first, through the domain's own scoped read — the
    lock is taken by primary key and would not check ownership. Both rows are then
    locked, **the original first**; see
    :func:`app.vat.services.vat_amendment_service.withdraw` for why the order and
    the re-check after the lock are not optional.

    Returns the original, not the amendment: it is the record the office works
    with from here.
    """
    requested = service.get_payment_for_client(client_record_id, payment_id)
    assert_withdrawable(requested)

    original = service.repo.get_by_id_for_update(requested.amends_id)
    amendment = service.repo.get_by_id_for_update(payment_id)
    if original is None or amendment is None:
        raise NotFoundError(
            f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
            ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
        )
    assert_withdrawable(amendment)

    status_before = amendment.status.value
    metadata = service._audit_metadata(amendment)
    withdraw_amendment(amendment, original, actor_id=actor_id)
    service.repo.db.flush()

    service._audit.record_action(
        ENTITY_ADVANCE_PAYMENT,
        amendment.id,
        actor_id,
        ACTION_ADVANCE_PAYMENT_AMENDMENT_WITHDRAWN,
        old_value={"status": status_before, "amends_id": original.id},
        actor_display_name=actor_name,
        metadata_json={**metadata, "restored_original_id": original.id},
    )

    return original


def list_chain(service, *, client_record_id: int, payment_id: int) -> list[AdvancePayment]:
    """Every payment for this period, oldest first — the correction history."""
    payment = service.get_payment_for_client(client_record_id, payment_id)
    return list(
        service.repo.db.scalars(
            select_chain(
                AdvancePayment,
                client_record_id=payment.client_record_id,
                period_column=AdvancePayment.period,
                period_value=payment.period,
            )
        ).all()
    )
