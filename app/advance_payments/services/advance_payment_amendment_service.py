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
from app.audit.audit_constants import ACTION_ADVANCE_PAYMENT_AMENDED, ENTITY_ADVANCE_PAYMENT
from app.common.enums import ObligationStatus
from app.common.obligation_chain import assert_amendable, copy_for_amendment, select_chain


def create_amendment(
    service,
    *,
    client_record_id: int,
    payment_id: int,
    actor_id: int,
    actor_name: str | None = None,
) -> AdvancePayment:
    """Open a correction of a closed advance period."""
    original = service.get_payment_for_client(client_record_id, payment_id)
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
