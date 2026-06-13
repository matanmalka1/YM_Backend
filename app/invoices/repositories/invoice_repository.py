from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.invoices.models.invoice import Invoice


class InvoiceRepository(BaseRepository[Invoice]):
    """Data access layer for Invoice entities."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        charge_id: int,
        provider: str,
        external_invoice_id: str,
        issued_at: datetime,
        document_url: str | None = None,
    ) -> Invoice:
        """Create new invoice reference."""
        invoice = Invoice(
            charge_id=charge_id,
            provider=provider,
            external_invoice_id=external_invoice_id,
            document_url=document_url,
            issued_at=issued_at,
        )
        self.db.add(invoice)
        self.db.flush()
        return invoice

    def get_by_id(self, invoice_id: int) -> Invoice | None:
        """Retrieve invoice by ID."""
        return self.db.scalars(select(Invoice).where(Invoice.id == invoice_id)).first()

    def get_by_charge_id(self, charge_id: int) -> Invoice | None:
        """Retrieve invoice by charge ID."""
        return self.db.scalars(select(Invoice).where(Invoice.charge_id == charge_id)).first()

    def list_by_charge_ids(self, charge_ids: list[int]) -> list[Invoice]:
        """Batch-fetch invoices for a list of charge IDs (single query)."""
        if not charge_ids:
            return []
        return self.db.scalars(select(Invoice).where(Invoice.charge_id.in_(charge_ids))).all()

    def exists_for_charge(self, charge_id: int) -> bool:
        """Check if invoice exists for charge."""
        return (
            self.db.scalar(select(func.count(Invoice.id)).where(Invoice.charge_id == charge_id)) > 0
        )
