from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.actions.services.obligation_orchestrator import generate_client_obligations
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.client_onboarding_service import create_initial_binder
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import ObligationType
from app.common.obligation_plan import (
    advance_payment_obligation_plan,
    vat_obligation_plan,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.tax_calendar.services.materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.services.intake import create_work_item
from app.utils.time_utils import israel_today


@dataclass(slots=True)
class ClientOnboardingResult:
    obligations_created: int = 0
    vat_work_items_created: int = 0
    advance_payments_created: int = 0


class ClientOnboardingOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.client_repo = ClientRecordRepository(db)
        self.binder_repo = BinderRepository(db)
        self.vat_repo = VatWorkItemRepository(db)
        self.advance_repo = AdvancePaymentRepository(db)
        self.advance_service = AdvancePaymentService(db)
        self.tax_calendar = TaxCalendarMaterializationService(db)

    def run(
        self,
        client_record_id: int,
        *,
        actor_id: int | None,
        entity_type=None,
        reference_date: date | None = None,
    ) -> ClientOnboardingResult:
        record = self.client_repo.get_by_id(client_record_id)
        if not record:
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה",
                "CLIENT_RECORD.NOT_FOUND",
            )
        result = ClientOnboardingResult()
        self._ensure_initial_binder(record, actor_id)
        result.obligations_created = generate_client_obligations(
            self.db,
            client_record_id,
            actor_id=actor_id,
            entity_type=entity_type,
            reference_date=reference_date,
            best_effort=False,
        )
        today = reference_date or israel_today()
        le = LegalEntityRepository(self.db).get_by_id(record.legal_entity_id) if record else None
        vat_type = getattr(le, "vat_reporting_frequency", None) if le else None
        ap_frequency = getattr(le, "advance_payment_frequency", None) if le else None
        ap_entity_type = getattr(le, "entity_type", None) if le else None

        result.vat_work_items_created = self._sync_vat_work_items(
            client_record_id, actor_id, vat_type, today
        )
        result.advance_payments_created = self._sync_advance_payments(
            client_record_id, ap_frequency, ap_entity_type, today
        )
        return result

    def _ensure_initial_binder(self, record, actor_id: int | None) -> None:
        if self.binder_repo.count_all_by_client(record.id) > 0:
            return
        create_initial_binder(self.db, record, actor_id)

    def _sync_vat_work_items(
        self,
        client_record_id: int,
        actor_id: int | None,
        vat_type,
        reference_date: date,
    ) -> int:
        from app.actions.services.obligation_orchestrator import _years_to_generate

        years = _years_to_generate(reference_date)
        created = 0
        for year in years:
            plans = vat_obligation_plan(vat_type, year)
            for plan in plans:
                entry = self.tax_calendar.ensure_periodic_entry(
                    ObligationType.VAT,
                    plan.period,
                    plan.period_months_count,
                )
                if entry.due_date < reference_date:
                    continue
                item = self.vat_repo.get_by_client_record_period(client_record_id, plan.period)
                if item is None and actor_id is not None:
                    try:
                        create_work_item(
                            self.vat_repo,
                            self.db,
                            client_record_id=client_record_id,
                            period=plan.period,
                            created_by=actor_id,
                            mark_pending=True,
                            pending_materials_note="נוצר אוטומטית מפתיחת לקוח",
                        )
                        created += 1
                    except ConflictError:
                        pass
        return created

    def _sync_advance_payments(
        self,
        client_record_id: int,
        frequency,
        entity_type,
        reference_date: date,
    ) -> int:
        if frequency is None:
            return 0
        from app.actions.services.obligation_orchestrator import _years_to_generate

        years = _years_to_generate(reference_date)
        created = 0
        for year in years:
            plans = advance_payment_obligation_plan(
                frequency=frequency,
                year=year,
                entity_type=entity_type,
            )
            for plan in plans:
                entry = self.tax_calendar.ensure_periodic_entry(
                    ObligationType.ADVANCE_PAYMENT,
                    plan.period,
                    plan.period_months_count,
                )
                if entry.due_date < reference_date:
                    continue
                payment = self.advance_repo.get_by_period(client_record_id, plan.period)
                if payment is None:
                    try:
                        self.advance_service.create_payment_for_client(
                            client_record_id=client_record_id,
                            period=plan.period,
                            period_months_count=plan.period_months_count,
                        )
                        created += 1
                    except ConflictError:
                        pass
                elif (
                    payment.period_months_count != plan.period_months_count
                    or payment.due_date != entry.due_date
                ):
                    self.advance_repo.update_payment(
                        payment,
                        period_months_count=plan.period_months_count,
                        due_date=entry.due_date,
                    )
        return created
