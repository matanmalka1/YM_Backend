from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from itertools import count
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.businesses.models.business import Business
from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.invoices.models.invoice import Invoice
from tests.helpers.factory_utils import (
    TEST_DATETIME,
    ClientRef,
    resolve_exclusive,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory


class ChargeFactory:
    """Model-level Charge factory: no BillingService side effects (audit/timeline)."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        business: Business | None = None,
        business_id: int | None = None,
        annual_report_id: int | None = None,
        charge_type: ChargeType = ChargeType.MONTHLY_RETAINER,
        status: ChargeStatus = ChargeStatus.DRAFT,
        amount: Decimal | int | str = Decimal("100.00"),
        period: str | None = None,
        months_covered: int = 1,
        description: str | None = None,
        created_by: int | None = None,
        issued_at: datetime | date | None = None,
        issued_by: int | None = None,
        paid_at: datetime | date | None = None,
        paid_by: int | None = None,
        canceled_at: datetime | date | None = None,
        canceled_by: int | None = None,
        cancellation_reason: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> Charge:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        resolve_exclusive(business, business_id, names="business or business_id")
        next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        charge_fields: dict[str, Any] = {
            "client_record_id": resolved_client_id,
            "business_id": business_id
            if business_id is not None
            else getattr(business, "id", None),
            "annual_report_id": annual_report_id,
            "charge_type": charge_type,
            "status": status,
            "amount": Decimal(str(amount)),
            "period": period,
            "months_covered": months_covered,
            "description": description,
            "created_by": created_by,
            "issued_at": issued_at,
            "issued_by": issued_by,
            "paid_at": paid_at,
            "paid_by": paid_by,
            "canceled_at": canceled_at,
            "canceled_by": canceled_by,
            "cancellation_reason": cancellation_reason,
            "updated_at": updated_at,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
        }
        # created_at has a model-level default; only override when the test pins it.
        if created_at is not None:
            charge_fields["created_at"] = created_at
        charge = Charge(**charge_fields)
        self.db.add(charge)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(charge)
        return charge


class InvoiceFactory:
    """Model-level Invoice factory."""

    def __init__(self, db: Session, charge_factory: ChargeFactory) -> None:
        self.db = db
        self.charge_factory = charge_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        charge: Charge | None = None,
        charge_id: int | None = None,
        provider: str = "test",
        external_invoice_id: str | None = None,
        document_url: str | None = None,
        issued_at: datetime | None = None,
        created_at: datetime | None = None,
        commit: bool = False,
    ) -> Invoice:
        resolve_exclusive(charge, charge_id, names="charge or charge_id")
        sequence = next(self._sequence)
        if charge is None and charge_id is None:
            charge = self.charge_factory()
        fields: dict[str, Any] = {
            "charge_id": charge_id if charge_id is not None else charge.id,
            "provider": provider,
            "external_invoice_id": external_invoice_id or f"TEST-INV-{sequence:04d}",
            "document_url": document_url,
            "issued_at": issued_at or TEST_DATETIME,
        }
        if created_at is not None:
            fields["created_at"] = created_at
        invoice = Invoice(**fields)
        self.db.add(invoice)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(invoice)
        return invoice
