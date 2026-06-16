from app.core.error_codes import ErrorCode
from datetime import datetime

from sqlalchemy.orm import Session

from app.charges.models.charge import ChargeStatus
from app.charges.repositories.charge_repository import ChargeRepository
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.invoices.models.invoice import Invoice
from app.invoices.repositories.invoice_repository import InvoiceRepository


class InvoiceService:
    """Invoice reference management business logic."""

    def __init__(self, db: Session):
        self.db = db
        self.invoice_repo = InvoiceRepository(db)
        self.charge_repo = ChargeRepository(db)

    def attach_invoice_to_charge(  # TODO(sprint-future): call from BillingService.issue_charge when external invoice provider is integrated
        self,
        charge_id: int,
        provider: str,
        external_invoice_id: str,
        issued_at: datetime,
        document_url: str | None = None,
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
        # Validate charge exists
        charge = self.charge_repo.get_by_id(charge_id)
        if not charge:
            raise NotFoundError(f"חיוב {charge_id} לא נמצא", ErrorCode.INVOICE_NOT_FOUND)

        # Validate charge is issued
        if charge.status != ChargeStatus.ISSUED:
            raise AppError(
                f"לא ניתן לצרף חשבונית לחיוב במצב {charge.status.value}",
                ErrorCode.INVOICE_INVALID_STATUS,
            )

        # Validate no existing invoice
        if self.invoice_repo.exists_for_charge(charge_id):
            raise ConflictError(
                f"לחיוב {charge_id} כבר קיימת חשבונית",
                ErrorCode.INVOICE_CONFLICT,
            )

        # Create invoice reference
        return self.invoice_repo.create(
            charge_id=charge_id,
            provider=provider,
            external_invoice_id=external_invoice_id,
            issued_at=issued_at,
            document_url=document_url,
        )
