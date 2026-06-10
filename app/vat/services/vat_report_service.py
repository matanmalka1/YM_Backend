"""
VatReportService — thin façade delegating to focused sub-modules.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.businesses.repositories.business_repository import BusinessRepository
from app.users.repositories.user_repository import UserRepository
from app.vat.repositories.vat_invoice_repository import VatInvoiceRepository
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.services import (
    filing,
    intake,
    period_options,
    vat_report_enrichment,
    vat_report_queries,
)
from app.vat.services.data_entry_invoice_delete import delete_invoice
from app.vat.services.data_entry_invoice_update import update_invoice
from app.vat.services.data_entry_invoices import add_invoice
from app.vat.services.data_entry_status import (
    mark_ready_for_review,
    send_back_for_correction,
)


class VatReportService:
    """Orchestrates the VAT reporting lifecycle."""

    def __init__(self, db: Session):
        self.db = db
        self.work_item_repo = VatWorkItemRepository(db)
        self.invoice_repo = VatInvoiceRepository(db)
        self.business_repo = BusinessRepository(db)
        self.user_repo = UserRepository(db)

    # ── Intake ───────────────────────────────────────────────────────────────

    def create_work_item(self, **kwargs):
        return intake.create_work_item(
            self.work_item_repo,
            self.db,
            **kwargs,
        )

    def mark_materials_complete(self, **kwargs):
        return intake.mark_materials_complete(self.work_item_repo, **kwargs)

    def get_period_options(self, **kwargs):
        return period_options.get_period_options(
            self.work_item_repo,
            self.db,
            **kwargs,
        )

    # ── Data entry ───────────────────────────────────────────────────────────

    def add_invoice(self, **kwargs):
        return add_invoice(self.work_item_repo, self.invoice_repo, **kwargs)

    def delete_invoice(self, **kwargs):
        return delete_invoice(self.work_item_repo, self.invoice_repo, **kwargs)

    def update_invoice(self, **kwargs):
        return update_invoice(self.work_item_repo, self.invoice_repo, **kwargs)

    def mark_ready_for_review(self, **kwargs):
        return mark_ready_for_review(self.work_item_repo, **kwargs)

    def send_back_for_correction(self, **kwargs):
        return send_back_for_correction(self.work_item_repo, **kwargs)

    # ── Filing ───────────────────────────────────────────────────────────────

    def file_vat_return(self, **kwargs):
        return filing.file_vat_return(self.work_item_repo, **kwargs)

    # ── Queries ──────────────────────────────────────────────────────────────

    def get_work_item(self, item_id: int):
        return vat_report_queries.get_work_item(self.work_item_repo, item_id)

    def list_client_work_items_paginated(self, **kwargs):
        return vat_report_queries.list_client_work_items_paginated(self.work_item_repo, **kwargs)

    def list_work_items_by_status(self, **kwargs):
        return vat_report_queries.list_work_items_by_status(self.work_item_repo, **kwargs)

    def list_all_work_items(self, **kwargs):
        return vat_report_queries.list_all_work_items(self.work_item_repo, **kwargs)

    def get_status_summary(self, **kwargs):
        return vat_report_queries.get_status_summary(self.work_item_repo, **kwargs)

    def list_invoices(self, **kwargs):
        return vat_report_queries.list_invoices(self.invoice_repo, **kwargs)

    def get_work_item_by_client_period(self, client_record_id: int, period: str):
        return vat_report_queries.get_work_item_by_client_period(
            self.work_item_repo,
            client_record_id,
            period,
        )

    def get_audit_trail(self, item_id: int, limit: int, offset: int):
        return vat_report_queries.get_audit_trail(self.work_item_repo, item_id, limit, offset)

    def get_work_item_enriched(self, item_id: int) -> dict:
        return vat_report_enrichment.get_work_item_enriched(
            self.work_item_repo, self.user_repo, item_id
        )

    def get_client_items_enriched(
        self, client_record_id: int, page: int = 1, page_size: int = 200
    ) -> dict:
        return vat_report_enrichment.get_client_items_enriched(
            self.work_item_repo,
            self.user_repo,
            client_record_id,
            page=page,
            page_size=page_size,
        )

    def get_list_enriched(self, **kwargs) -> dict:
        return vat_report_enrichment.get_list_enriched(
            self.work_item_repo, self.user_repo, **kwargs
        )

    def get_audit_trail_enriched(self, item_id: int, limit: int, offset: int) -> dict:
        return vat_report_enrichment.get_audit_trail_enriched(
            self.work_item_repo, self.user_repo, item_id, limit, offset
        )
