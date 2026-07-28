from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from itertools import count
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.common.enums import (
    ObligationStatus,
    ObligationType,
    SubmissionMethod,
    VatType,
)
from app.users.models.user import User
from app.vat.models.vat_work_item import VatWorkItem
from tests.helpers.factory_utils import (
    TEST_DUE_DATE,
    ClientRef,
    resolve_exclusive,
    sequence_period,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory
    from tests.factories.tax_calendar import TaxCalendarEntryFactory


class VatWorkItemFactory:
    """Model-level VatWorkItem factory."""

    def __init__(
        self,
        db: Session,
        client_factory: ClientFactory,
        tax_calendar_entry_factory: TaxCalendarEntryFactory,
        actor_user: User,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.tax_calendar_entry_factory = tax_calendar_entry_factory
        self.actor_user = actor_user
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        created_by: int | None = None,
        assigned_to: int | None = None,
        period: str | None = None,
        period_type: VatType = VatType.MONTHLY,
        status: ObligationStatus = ObligationStatus.INPUT_RECEIVED,
        pending_materials_note: str | None = None,
        total_output_vat: Decimal | int | str = Decimal("0.00"),
        total_input_vat: Decimal | int | str = Decimal("0.00"),
        net_vat: Decimal | int | str = Decimal("0.00"),
        total_output_net: Decimal | int | str = Decimal("0.00"),
        total_input_net: Decimal | int | str = Decimal("0.00"),
        final_vat_amount: Decimal | int | str | None = None,
        is_overridden: bool = False,
        override_justification: str | None = None,
        submission_method: SubmissionMethod | None = None,
        filed_at: datetime | None = None,
        filed_by: int | None = None,
        submission_reference: str | None = None,
        is_amendment: bool = False,
        amends_item_id: int | None = None,
        tax_calendar_entry_id: int | None = None,
        due_date_original: date | None = None,
        due_date_effective: date | None = None,
        due_date_override_reason: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> VatWorkItem:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        if created_by is None:
            created_by = self.actor_user.id
        resolved_period = sequence_period(sequence) if period is None else period
        months_count = 2 if period_type == VatType.BIMONTHLY else 1
        if tax_calendar_entry_id is None:
            entry = self.tax_calendar_entry_factory(
                obligation_type=ObligationType.VAT,
                period=resolved_period,
                period_months_count=months_count,
                tax_year=int(resolved_period[:4]),
                due_date=(TEST_DUE_DATE if due_date_original is None else due_date_original),
            )
            tax_calendar_entry_id = entry.id
            due_date_original = entry.due_date
        work_item_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "created_by": created_by,
            "assigned_to": assigned_to,
            "period": resolved_period,
            "period_type": period_type,
            "status": status,
            "pending_materials_note": pending_materials_note,
            "total_output_vat": Decimal(str(total_output_vat)),
            "total_input_vat": Decimal(str(total_input_vat)),
            "net_vat": Decimal(str(net_vat)),
            "total_output_net": Decimal(str(total_output_net)),
            "total_input_net": Decimal(str(total_input_net)),
            "final_vat_amount": None
            if final_vat_amount is None
            else Decimal(str(final_vat_amount)),
            "is_overridden": is_overridden,
            "override_justification": override_justification,
            "submission_method": submission_method,
            "filed_at": filed_at,
            "filed_by": filed_by,
            "submission_reference": submission_reference,
            "is_amendment": is_amendment,
            "amends_item_id": amends_item_id,
            "tax_calendar_entry_id": tax_calendar_entry_id,
            "due_date_original": due_date_original,
            "due_date_effective": due_date_effective,
            "due_date_override_reason": due_date_override_reason,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
        }
        if created_at is not None:
            work_item_fields["created_at"] = created_at
        if updated_at is not None:
            work_item_fields["updated_at"] = updated_at
        work_item = VatWorkItem(**work_item_fields)
        self.db.add(work_item)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(work_item)
        return work_item
