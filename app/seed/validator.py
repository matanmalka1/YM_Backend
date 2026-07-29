from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder
from app.clients.models.client_record import ClientRecord
from app.common.enums import EntityType
from app.legal_entities.models.legal_entity import LegalEntity
from app.tax_calendar.tax_calendar_link_diagnostics import (
    find_active_null_tax_calendar_links,
)
from app.vat.models.vat_work_item import VatWorkItem


class SeedIntegrityError(RuntimeError):
    pass


class SeedIntegrityValidator:
    def __init__(self, db: Session):
        self.db = db
        self._errors: list[str] = []

    def validate(self) -> None:
        self._errors = []
        self._check_active_clients_have_binders()
        self._check_no_vat_items_for_exempt_clients()
        self._check_no_duplicate_annual_reports()
        self._check_amendment_chains_are_stamped()
        self._check_no_null_tax_calendar_links()
        self._check_vat_advance_period_sync()
        self._check_advance_payment_amounts()
        if self._errors:
            error_list = "\n".join(f"  - {e}" for e in self._errors)
            raise SeedIntegrityError(
                f"Seed integrity check failed ({len(self._errors)} error(s)):\n{error_list}"
            )

    def _check_active_clients_have_binders(self) -> None:
        active_clients = (
            self.db.execute(select(ClientRecord.id).where(ClientRecord.deleted_at.is_(None)))
            .scalars()
            .all()
        )
        for client_id in active_clients:
            count = self.db.execute(
                select(func.count())
                .select_from(Binder)
                .where(Binder.client_record_id == client_id, Binder.deleted_at.is_(None))
            ).scalar_one()
            if count == 0:
                self._errors.append(f"Client {client_id} has no binders")

    def _check_no_vat_items_for_exempt_clients(self) -> None:
        exempt_types = {EntityType.OSEK_PATUR, EntityType.EMPLOYEE}
        exempt_client_ids = (
            self.db.execute(
                select(ClientRecord.id)
                .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
                .where(
                    LegalEntity.entity_type.in_(exempt_types),
                    ClientRecord.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for client_id in exempt_client_ids:
            count = self.db.execute(
                select(func.count())
                .select_from(VatWorkItem)
                .where(
                    VatWorkItem.client_record_id == client_id,
                    VatWorkItem.deleted_at.is_(None),
                )
            ).scalar_one()
            if count > 0:
                self._errors.append(
                    f"Client {client_id} is EXEMPT but has {count} VAT work item(s)"
                )

    def _check_no_duplicate_annual_reports(self) -> None:
        """One *original* report per client and year (§4.1.13).

        Amendments are excluded, not counted: a correction is a second row for
        the same year by design (D-10). Without the exclusion this check would
        report every corrected year as a duplicate — a true statement about the
        row count and a false one about the data.
        """
        dupes = self.db.execute(
            select(AnnualReport.client_record_id, AnnualReport.tax_year, func.count())
            .where(
                AnnualReport.deleted_at.is_(None),
                AnnualReport.amends_id.is_(None),
            )
            .group_by(AnnualReport.client_record_id, AnnualReport.tax_year)
            .having(func.count() > 1)
        ).all()
        for client_id, tax_year, count in dupes:
            self._errors.append(
                f"Client {client_id} has {count} annual reports for year {tax_year}"
            )

    def _check_amendment_chains_are_stamped(self) -> None:
        """Every amended row carries its ``superseded_at`` stamp (D-12).

        The link and the stamp are written together by ``link_amendment``, but
        they are two columns and nothing at the database level ties them. A row
        that someone amended without stamping stays visible to every list and
        sum alongside its own correction — the exact double-count the chain-tip
        predicate exists to prevent, and silent, because both rows are valid on
        their own.
        """
        for model in (VatWorkItem, AnnualReport, AdvancePayment):
            amended = self.db.execute(
                select(func.count())
                .select_from(model)
                .join(
                    aliased_amendment := aliased(model),
                    aliased_amendment.amends_id == model.id,
                )
                .where(
                    model.deleted_at.is_(None),
                    aliased_amendment.deleted_at.is_(None),
                    model.superseded_at.is_(None),
                )
            ).scalar()
            if amended:
                self._errors.append(
                    f"{model.__tablename__} has {amended} amended row(s) with no superseded_at"
                )

    def _check_no_null_tax_calendar_links(self) -> None:
        diagnostics = find_active_null_tax_calendar_links(self.db)
        for table, result in diagnostics.items():
            if result["count"]:
                self._errors.append(
                    f"{table} has {result['count']} active row(s) without tax_calendar_entry_id"
                )

    def _check_advance_payment_amounts(self) -> None:
        payments = (
            self.db.execute(
                select(AdvancePayment).where(
                    AdvancePayment.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for p in payments:
            if p.turnover_amount is None or p.advance_rate is None:
                # Incomplete source snapshot — formula not applicable.
                continue
            expected_calc = (
                Decimal(str(p.turnover_amount)) * Decimal(str(p.advance_rate)) / 100
            ).quantize(Decimal("0.01"), ROUND_HALF_UP)
            if Decimal(str(p.calculated_amount)).quantize(Decimal("0.01")) != expected_calc:
                self._errors.append(f"AdvancePayment {p.id}: calculated_amount mismatch")
            expected_final = (
                p.override_amount if p.override_amount is not None else p.calculated_amount
            )
            if Decimal(str(p.expected_amount)) != Decimal(str(expected_final)):
                self._errors.append(f"AdvancePayment {p.id}: expected_amount mismatch")

    def _check_vat_advance_period_sync(self) -> None:
        """Clients with VAT work items but no advance payments for the same periods are a data gap."""
        non_exempt_types = {EntityType.OSEK_MURSHE, EntityType.COMPANY_LTD}
        eligible_client_ids = set(
            self.db.execute(
                select(ClientRecord.id)
                .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
                .where(
                    LegalEntity.entity_type.in_(non_exempt_types),
                    LegalEntity.advance_payment_frequency.isnot(None),
                    ClientRecord.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for client_id in eligible_client_ids:
            vat_periods = set(
                self.db.execute(
                    select(VatWorkItem.period).where(
                        VatWorkItem.client_record_id == client_id,
                        VatWorkItem.deleted_at.is_(None),
                    )
                )
                .scalars()
                .all()
            )
            ap_periods = set(
                self.db.execute(
                    select(AdvancePayment.period).where(
                        AdvancePayment.client_record_id == client_id,
                        AdvancePayment.deleted_at.is_(None),
                    )
                )
                .scalars()
                .all()
            )
            if vat_periods and not ap_periods:
                self._errors.append(
                    f"Client {client_id} has {len(vat_periods)} VAT period(s) but zero advance payments"
                )
