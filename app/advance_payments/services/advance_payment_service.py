from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.advance_payments.advance_payment_constants import (
    BIMONTHLY_START_MONTHS,
    SUPPORTED_PERIOD_MONTH_COUNTS,
    get_period_start_months,
)
from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.advance_payments.repositories.advance_payment_turnover_lookup_repository import (
    TurnoverLookupRepository,
)
from app.audit.audit_constants import (
    ACTION_ADVANCE_PAYMENT_CREATED,
    ACTION_ADVANCE_PAYMENT_DELETED,
    ACTION_ADVANCE_PAYMENT_UPDATED,
    ENTITY_ADVANCE_PAYMENT,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.clients.client_enums import ClientStatus
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import AdvancePaymentFrequency, ObligationType
from app.common.period_utils import parse_period_month, parse_period_year
from app.core.error_codes import ErrorCode
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.utils.time_utils import israel_today, utcnow

_SYSTEM_ACTOR_DISPLAY = "מערכת"


class AdvancePaymentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AdvancePaymentRepository(db)
        self.client_repo = ClientRecordRepository(db)
        self._audit = EntityAuditWriter(db)

    def _audit_metadata(self, payment: AdvancePayment, *, source: str | None = None) -> dict:
        meta = {
            "client_record_id": payment.client_record_id,
            "period": payment.period,
            "tax_year": parse_period_year(payment.period),
        }
        if payment.annual_report_id is not None:
            meta["annual_report_id"] = payment.annual_report_id
        if source is not None:
            meta["source"] = source
        return meta

    def _audit_snapshot(self, payment: AdvancePayment) -> dict:
        return {
            "period": payment.period,
            "period_months_count": payment.period_months_count,
            "due_date": payment.due_date,
            "expected_amount": payment.expected_amount,
            "paid_amount": payment.paid_amount,
            "payment_method": payment.payment_method,
            "annual_report_id": payment.annual_report_id,
            "notes": payment.notes,
            "advance_rate": payment.advance_rate,
            "turnover_amount": payment.turnover_amount,
            "calculated_amount": payment.calculated_amount,
            "override_amount": payment.override_amount,
            "status": payment.status,
            "paid_at": payment.paid_at,
        }

    def _actor_kwargs(self, actor_id: int | None, actor_name: str | None) -> dict:
        if actor_id is None:
            return {
                "actor_type": "system",
                "actor_display_name": actor_name or _SYSTEM_ACTOR_DISPLAY,
            }
        return {"actor_display_name": actor_name}

    def _get_record_or_raise(self, client_record_id: int):
        record = self.client_repo.get_by_id(client_record_id)
        if record is None:
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה",
                ErrorCode.ADVANCE_PAYMENT_CLIENT_RECORD_NOT_FOUND,
            )
        return record

    def _assert_client_allows_create(self, client_record_id: int) -> None:
        record = self._get_record_or_raise(client_record_id)
        if record.status == ClientStatus.CLOSED:
            raise ForbiddenError("לקוח סגור — לא ניתן ליצור מקדמה", ErrorCode.CLIENT_CLOSED)
        if record.status == ClientStatus.FROZEN:
            raise ForbiddenError("לקוח מוקפא — לא ניתן ליצור מקדמה", ErrorCode.CLIENT_FROZEN)

    def default_period_months_count_for_client(self, client_record_id: int) -> int:
        record = self._get_record_or_raise(client_record_id)
        legal_entity = LegalEntityRepository(self.db).get_by_id(record.legal_entity_id)
        freq = legal_entity.advance_payment_frequency if legal_entity else None
        if freq == AdvancePaymentFrequency.BIMONTHLY:
            return 2
        if freq == AdvancePaymentFrequency.MONTHLY:
            return 1
        raise NotFoundError(
            "תדירות מקדמות לא מוגדרת ללקוח", ErrorCode.ADVANCE_PAYMENT_FREQUENCY_NOT_SET
        )

    def _validate_period_months_count(self, period: str, period_months_count: int) -> None:
        if period_months_count not in SUPPORTED_PERIOD_MONTH_COUNTS:
            raise ConflictError("תדירות מקדמה לא נתמכת", ErrorCode.ADVANCE_PAYMENT_INVALID_PERIOD)
        if period_months_count == 2 and parse_period_month(period) not in BIMONTHLY_START_MONTHS:
            raise ConflictError(
                "מקדמה דו-חודשית חייבת להתחיל בחודש אי-זוגי",
                ErrorCode.ADVANCE_PAYMENT_INVALID_PERIOD,
            )

    def _compute_amounts(
        self,
        turnover_amount,
        advance_rate,
        override_amount,
        fallback_expected=None,
    ) -> tuple[Decimal, Decimal]:
        calculated = Decimal("0.00")
        if turnover_amount is not None and advance_rate is not None:
            calculated = (
                Decimal(str(turnover_amount)) * Decimal(str(advance_rate)) / 100
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if override_amount is not None:
            expected = Decimal(str(override_amount))
        elif fallback_expected is not None and calculated == 0:
            expected = Decimal(str(fallback_expected))
        else:
            expected = calculated
        return calculated, expected

    # ─── List ─────────────────────────────────────────────────────────────────

    def list_payments_for_client(
        self,
        client_record_id: int,
        year: int | None = None,
        status: list[AdvancePaymentStatus] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AdvancePayment], int]:
        if year is None:
            year = utcnow().year
        self._get_record_or_raise(client_record_id)
        return self.repo.list_by_client_record_year(
            client_record_id, year, status=status, page=page, page_size=page_size
        )

    # ─── Create ───────────────────────────────────────────────────────────────

    def create_payment_for_client(
        self,
        client_record_id: int,
        period: str,
        period_months_count: int | None,
        expected_amount=None,
        paid_amount=None,
        payment_method=None,
        annual_report_id: int | None = None,
        notes: str | None = None,
        turnover_amount=None,
        advance_rate=None,
        override_amount=None,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> AdvancePayment:
        self._assert_client_allows_create(client_record_id)
        configured_count = self.default_period_months_count_for_client(client_record_id)
        if period_months_count is None:
            period_months_count = configured_count
        elif period_months_count != configured_count:
            raise ConflictError(
                "תדירות המקדמות בבקשה אינה תואמת להגדרת הלקוח",
                ErrorCode.ADVANCE_PAYMENT_FREQUENCY_MISMATCH,
            )
        self._validate_period_months_count(period, period_months_count)
        if self.repo.exists_for_period(client_record_id, period):
            raise ConflictError(
                f"תשלום מקדמה לתקופה {period} כבר קיים",
                ErrorCode.ADVANCE_PAYMENT_CONFLICT,
            )

        if advance_rate is None:
            record = self._get_record_or_raise(client_record_id)
            le = LegalEntityRepository(self.db).get_by_id(record.legal_entity_id)
            advance_rate = le.advance_rate if le else None

        calculated_amount, resolved_expected = self._compute_amounts(
            turnover_amount, advance_rate, override_amount, expected_amount
        )

        mat = TaxCalendarMaterializationService(self.db)
        entry = mat.ensure_periodic_entry(
            ObligationType.ADVANCE_PAYMENT,
            period,
            period_months_count,
        )
        payment = self.repo.create(
            client_record_id=client_record_id,
            period=period,
            period_months_count=period_months_count,
            due_date=entry.due_date,
            expected_amount=resolved_expected,
            paid_amount=paid_amount,
            payment_method=payment_method,
            annual_report_id=annual_report_id,
            tax_calendar_entry_id=entry.id,
            notes=notes,
            advance_rate=advance_rate,
            turnover_amount=turnover_amount,
            calculated_amount=calculated_amount,
            override_amount=override_amount,
        )
        payment = mat.link_advance_payment(payment)
        self._audit.record_action(
            ENTITY_ADVANCE_PAYMENT,
            payment.id,
            actor_id,
            ACTION_ADVANCE_PAYMENT_CREATED,
            new_value=self._audit_snapshot(payment),
            metadata_json=self._audit_metadata(payment),
            **self._actor_kwargs(actor_id, actor_name),
        )
        return payment

    # ─── Update ───────────────────────────────────────────────────────────────

    _ALLOWED_UPDATE_FIELDS = {
        "paid_amount",
        "expected_amount",
        "status",
        "paid_at",
        "payment_method",
        "notes",
        "turnover_amount",
        "override_amount",
    }

    def update_payment_for_client(
        self,
        client_record_id: int,
        payment_id: int,
        *,
        actor_id: int | None = None,
        actor_name: str | None = None,
        **fields,
    ) -> AdvancePayment:
        self._get_record_or_raise(client_record_id)
        payment = self.repo.get_by_id_for_client_record(payment_id, client_record_id)
        if not payment:
            raise NotFoundError(
                f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
                ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
            )
        filtered = {k: v for k, v in fields.items() if k in self._ALLOWED_UPDATE_FIELDS}

        calc_fields = {"turnover_amount", "override_amount"}
        if calc_fields & filtered.keys():
            effective_t = filtered.get("turnover_amount", payment.turnover_amount)
            effective_r = payment.advance_rate
            effective_o = filtered.get("override_amount", payment.override_amount)
            calculated_amount, new_expected = self._compute_amounts(
                effective_t, effective_r, effective_o
            )
            filtered["calculated_amount"] = calculated_amount
            filtered["expected_amount"] = new_expected
            if "paid_amount" not in filtered and "status" not in filtered:
                paid = payment.paid_amount
                if paid == 0:
                    filtered["status"] = AdvancePaymentStatus.PENDING
                elif paid >= new_expected:
                    filtered["status"] = AdvancePaymentStatus.PAID
                else:
                    filtered["status"] = AdvancePaymentStatus.PARTIAL

        if "paid_amount" in filtered and "status" not in filtered:
            paid = filtered["paid_amount"]
            expected = filtered.get("expected_amount", payment.expected_amount)
            if paid is None or paid == 0:
                filtered["status"] = AdvancePaymentStatus.PENDING
            elif paid >= expected:
                filtered["status"] = AdvancePaymentStatus.PAID
            else:
                filtered["status"] = AdvancePaymentStatus.PARTIAL

        old_snapshot = self._audit_snapshot(payment)
        updated = self.repo.update_payment(payment, **filtered)
        self._audit.record_action(
            ENTITY_ADVANCE_PAYMENT,
            updated.id,
            actor_id,
            ACTION_ADVANCE_PAYMENT_UPDATED,
            old_value=old_snapshot,
            new_value=self._audit_snapshot(updated),
            metadata_json=self._audit_metadata(updated),
            **self._actor_kwargs(actor_id, actor_name),
        )
        return updated

    # ─── Delete ───────────────────────────────────────────────────────────────

    def delete_payment_for_client(
        self,
        client_record_id: int,
        payment_id: int,
        actor_id: int,
        actor_name: str | None = None,
    ) -> None:
        self._get_record_or_raise(client_record_id)
        payment = self.repo.get_by_id_for_client_record(payment_id, client_record_id)
        if not payment:
            raise NotFoundError(
                f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
                ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
            )
        old_snapshot = self._audit_snapshot(payment)
        self.repo.soft_delete(payment_id, deleted_by=actor_id)
        self._audit.record_action(
            ENTITY_ADVANCE_PAYMENT,
            payment.id,
            actor_id,
            ACTION_ADVANCE_PAYMENT_DELETED,
            old_value=old_snapshot,
            actor_display_name=actor_name,
            metadata_json=self._audit_metadata(payment),
        )

    # ─── Generate schedule ────────────────────────────────────────────────────

    def generate_annual_schedule(
        self,
        client_record_id: int,
        year: int,
        period_months_count: int | None = None,
        reference_date: date | None = None,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> tuple[list[AdvancePayment], int]:
        if reference_date is None:
            reference_date = israel_today()
        self._assert_client_allows_create(client_record_id)
        configured_count = self.default_period_months_count_for_client(client_record_id)
        if period_months_count is None:
            period_months_count = configured_count
        elif period_months_count != configured_count:
            raise ConflictError(
                "תדירות המקדמות בבקשה אינה תואמת להגדרת הלקוח",
                ErrorCode.ADVANCE_PAYMENT_FREQUENCY_MISMATCH,
            )
        tax_calendar = TaxCalendarMaterializationService(self.db)
        created: list[AdvancePayment] = []
        skipped = 0
        for month in get_period_start_months(period_months_count):
            period = f"{year}-{month:02d}"
            entry = tax_calendar.ensure_periodic_entry(
                ObligationType.ADVANCE_PAYMENT,
                period,
                period_months_count,
            )
            if entry.due_date < reference_date:
                skipped += 1
                continue
            if self.repo.exists_for_period(client_record_id, period):
                skipped += 1
                continue
            payment = self.create_payment_for_client(
                client_record_id=client_record_id,
                period=period,
                period_months_count=period_months_count,
                actor_id=actor_id,
                actor_name=actor_name,
            )
            created.append(payment)
        return created, skipped

    # ─── Prefill ──────────────────────────────────────────────────────────────

    def get_prefill_turnover_for_client(
        self,
        client_record_id: int,
        period: str,
        period_months_count: int,
    ) -> tuple[Decimal | None, int | None, Literal["vat_filed", "vat_pending", "none"]]:
        self._get_record_or_raise(client_record_id)
        return TurnoverLookupRepository(self.db).get_prefill_turnover(
            client_record_id, period, period_months_count
        )
