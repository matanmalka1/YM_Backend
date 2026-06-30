from datetime import datetime

from sqlalchemy.orm import Session

from app.audit.audit_constants import ACTION_INVOICE_CREATED, ENTITY_INVOICE
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.charges.models.charge import ChargeStatus
from app.charges.repositories.charge_repository import ChargeRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.invoices.models.invoice import Invoice
from app.invoices.repositories.invoice_repository import InvoiceRepository

_SYSTEM_ACTOR_DISPLAY = "מערכת"


class InvoiceService:
    """Invoice reference management business logic."""

    def __init__(self, db: Session):
        self.db = db
        self.invoice_repo = InvoiceRepository(db)
        self.charge_repo = ChargeRepository(db)
        self._audit = EntityAuditWriter(db)

    def _actor_kwargs(self, actor_id: int | None, actor_name: str | None) -> dict:
        if actor_id is None:
            return {
                "actor_type": "system",
                "actor_display_name": actor_name or _SYSTEM_ACTOR_DISPLAY,
            }
        return {"actor_display_name": actor_name}

    def attach_invoice_to_charge(  # TODO(sprint-future): call from BillingService.issue_charge when external invoice provider is integrated
        self,
        charge_id: int,
        provider: str,
        external_invoice_id: str,
        issued_at: datetime,
        document_url: str | None = None,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> Invoice:
        """
        Attach external invoice reference to a charge.

        Rules:
        - Charge must exist and be issued
        - Each charge can have at most one invoice
        - Invoice metadata is immutable once stored

        Raises:
            AppError: If charge not found, not issued, or already has invoice
        """
        charge = self.charge_repo.get_by_id(charge_id)
        if not charge:
            raise NotFoundError(f"חיוב {charge_id} לא נמצא", ErrorCode.INVOICE_NOT_FOUND)

        if charge.status != ChargeStatus.ISSUED:
            raise AppError(
                f"לא ניתן לצרף חשבונית לחיוב במצב {charge.status.value}",
                ErrorCode.INVOICE_INVALID_STATUS,
            )

        if self.invoice_repo.exists_for_charge(charge_id):
            raise ConflictError(
                f"לחיוב {charge_id} כבר קיימת חשבונית",
                ErrorCode.INVOICE_CONFLICT,
            )

        invoice = self.invoice_repo.create(
            charge_id=charge_id,
            provider=provider,
            external_invoice_id=external_invoice_id,
            issued_at=issued_at,
            document_url=document_url,
        )
        self._audit.record_action(
            ENTITY_INVOICE,
            invoice.id,
            actor_id,
            ACTION_INVOICE_CREATED,
            new_value={
                "charge_id": invoice.charge_id,
                "provider": invoice.provider,
                "external_invoice_id": invoice.external_invoice_id,
                "document_url": invoice.document_url,
                "issued_at": invoice.issued_at,
            },
            metadata_json={
                "client_record_id": charge.client_record_id,
                "business_id": charge.business_id,
                "annual_report_id": charge.annual_report_id,
                "invoice_id": invoice.id,
            },
            **self._actor_kwargs(actor_id, actor_name),
        )
        return invoice
