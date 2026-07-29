from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from itertools import count
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    PaymentMethod,
    TurnoverSource,
)
from app.common.enums import (
    ObligationStatus,
    ObligationType,
)
from tests.helpers.factory_utils import (
    TEST_DUE_DATE,
    ClientRef,
    resolve_exclusive,
    sequence_period,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory
    from tests.factories.tax_calendar import TaxCalendarEntryFactory


class AdvancePaymentFactory:
    """Model-level AdvancePayment factory."""

    def __init__(
        self,
        db: Session,
        client_factory: ClientFactory,
        tax_calendar_entry_factory: TaxCalendarEntryFactory,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.tax_calendar_entry_factory = tax_calendar_entry_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        period: str | None = None,
        period_months_count: int = 1,
        due_date: date = TEST_DUE_DATE,
        due_date_original: date | None = None,
        due_date_effective: date | None = None,
        due_date_override_reason: str | None = None,
        expected_amount: Decimal | int | str = Decimal("0.00"),
        paid_amount: Decimal | int | str = Decimal("0.00"),
        turnover_amount: Decimal | int | str | None = None,
        advance_rate: Decimal | int | str | None = None,
        calculated_amount: Decimal | int | str = Decimal("0.00"),
        override_amount: Decimal | int | str | None = None,
        withheld_amount: Decimal | int | str | None = None,
        turnover_source: TurnoverSource | None = None,
        turnover_snapshot_at: datetime | None = None,
        status: ObligationStatus = ObligationStatus.AWAITING_INPUT,
        paid_at: datetime | None = None,
        payment_method: PaymentMethod | None = None,
        payment_reference: str | None = None,
        assigned_to: int | None = None,
        closed_at: datetime | None = None,
        closed_by: int | None = None,
        closed_late: bool | None = None,
        annual_report_id: int | None = None,
        tax_calendar_entry_id: int | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        restored_at: datetime | None = None,
        restored_by: int | None = None,
        commit: bool = False,
    ) -> AdvancePayment:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        resolved_period = sequence_period(sequence) if period is None else period
        if tax_calendar_entry_id is None:
            entry = self.tax_calendar_entry_factory(
                obligation_type=ObligationType.ADVANCE_PAYMENT,
                period=resolved_period,
                period_months_count=period_months_count,
                tax_year=int(resolved_period[:4]),
                due_date=due_date,
            )
            tax_calendar_entry_id = entry.id
        payment_fields: dict[str, Any] = {
            "client_record_id": resolved_client_id,
            "period": resolved_period,
            "period_months_count": period_months_count,
            "due_date": due_date,
            "due_date_original": due_date_original,
            "due_date_effective": due_date_effective,
            "due_date_override_reason": due_date_override_reason,
            "expected_amount": Decimal(str(expected_amount)),
            "paid_amount": Decimal(str(paid_amount)),
            "turnover_amount": None if turnover_amount is None else Decimal(str(turnover_amount)),
            "advance_rate": None if advance_rate is None else Decimal(str(advance_rate)),
            "calculated_amount": Decimal(str(calculated_amount)),
            "override_amount": None if override_amount is None else Decimal(str(override_amount)),
            "withheld_amount": None if withheld_amount is None else Decimal(str(withheld_amount)),
            "turnover_source": turnover_source,
            "turnover_snapshot_at": turnover_snapshot_at,
            "status": status,
            "paid_at": paid_at,
            "payment_method": payment_method,
            "payment_reference": payment_reference,
            "assigned_to": assigned_to,
            "closed_at": closed_at,
            "closed_by": closed_by,
            "closed_late": closed_late,
            "annual_report_id": annual_report_id,
            "tax_calendar_entry_id": tax_calendar_entry_id,
            "notes": notes,
            "updated_at": updated_at,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
            "restored_at": restored_at,
            "restored_by": restored_by,
        }
        if created_at is not None:
            payment_fields["created_at"] = created_at
        payment = AdvancePayment(**payment_fields)
        self.db.add(payment)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(payment)
        return payment
