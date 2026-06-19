from decimal import Decimal

from sqlalchemy.orm import Session

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.binders.models.binder import BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository
from app.businesses.schemas.business_status_card import (
    AdvancePaymentsCard,
    AnnualReportCard,
    BindersCard,
    ChargesCard,
    ClientStatusCardResponse,
    DocumentsCard,
    VatSummaryCard,
)
from app.charges.models.charge import ChargeStatus
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.services.client_service import get_client_or_raise
from app.documents.permanent_documents.repositories.permanent_document_repository import (
    PermanentDocumentRepository,
)
from app.utils.time_utils import utcnow
from app.vat.models.vat_work_item import VatWorkItemStatus
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)


class StatusCardService:
    """
    Status card ללקוח ספציפי.
    endpoint: GET /clients/{client_id}/status-card
    """

    def __init__(self, db: Session):
        self._db = db
        self._vat_repo = VatWorkItemRepository(db)
        self._annual_repo = AnnualReportRepository(db)
        self._charge_repo = ChargeRepository(db)
        self._advance_repo = AdvancePaymentRepository(db)
        self._binder_repo = BinderRepository(db)
        self._doc_repo = PermanentDocumentRepository(db)

    def get_status_card(
        self,
        client_id: int,
        year: int | None = None,
    ) -> ClientStatusCardResponse:
        resolved_year = year or utcnow().year
        client_record = get_client_or_raise(self._db, client_id)
        return ClientStatusCardResponse(
            client_id=client_id,
            year=resolved_year,
            client_vat=self._vat_card(client_record.id, resolved_year),
            annual_report=self._annual_report_card(client_record.id, resolved_year),
            charges=self._charges_card(client_record.id),
            advance_payments=self._advance_payments_card(client_record.id, resolved_year),
            binders=self._binders_card(client_record.id),
            documents=self._documents_card(client_record.id),
        )

    def _vat_card(self, client_record_id: int, year: int) -> VatSummaryCard:
        prefix = f"{year}-"
        rows = [
            r
            for r in self._vat_repo.list_by_client_record(client_record_id)
            if r.period and r.period.startswith(prefix)
        ]
        net_total = sum((r.net_vat or Decimal(0)) for r in rows)
        filed = sum(1 for r in rows if r.status == VatWorkItemStatus.FILED)
        latest = max((r.period for r in rows), default=None)
        return VatSummaryCard(
            net_vat_total=net_total,
            periods_filed=filed,
            periods_total=len(rows),
            latest_period=latest,
        )

    def _annual_report_card(self, client_record_id: int, year: int) -> AnnualReportCard:
        report = self._annual_repo.get_by_client_record_year(client_record_id, year)
        if not report:
            return AnnualReportCard()
        return AnnualReportCard(
            status=report.status.value if report.status else None,
            form_type=report.form_type.value if report.form_type else None,
            filing_deadline=report.filing_deadline,
            refund_due=report.refund_due,
            tax_due=report.tax_due,
        )

    def _charges_card(self, client_record_id: int) -> ChargesCard:
        rows = self._charge_repo.list_charges_by_client_record(
            client_record_id=client_record_id,
            status=ChargeStatus.ISSUED,
            page=1,
            page_size=10_000,
        )
        total = sum((r.amount or Decimal(0)) for r in rows)
        return ChargesCard(total_outstanding=total, unpaid_count=len(rows))

    def _advance_payments_card(self, client_record_id: int, year: int) -> AdvancePaymentsCard:
        rows, _ = self._advance_repo.list_by_client_record_year(
            client_record_id=client_record_id,
            year=year,
            page=1,
            page_size=10_000,
        )
        total = sum((r.paid_amount or Decimal(0)) for r in rows)
        return AdvancePaymentsCard(total_paid=total, count=len(rows))

    def _binders_card(self, client_record_id: int) -> BindersCard:
        rows = self._binder_repo.list_by_client_record(client_record_id)
        active = [r for r in rows if r.location_status != BinderLocationStatus.HANDED_OVER]
        in_office = sum(1 for r in active if r.location_status == BinderLocationStatus.IN_OFFICE)
        return BindersCard(active_count=len(active), in_office_count=in_office)

    def _documents_card(self, client_record_id: int) -> DocumentsCard:
        total, present = self._doc_repo.count_present_by_client_record(client_record_id)
        return DocumentsCard(total_count=total, present_count=present)
