import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.advance_payments.advance_payment_constants import (
    ADVANCE_PAYMENT_EXPECTED_NOT_COMPUTED_ISSUE,
    ADVANCE_PAYMENT_NOT_READY_TO_CLOSE,
    ADVANCE_PAYMENT_TURNOVER_UNKNOWN_ISSUE,
    BULK_GENERATE_CLIENT_CHUNK_SIZE,
)
from app.advance_payments.models.advance_payment import AdvancePayment, TurnoverSource
from app.advance_payments.repositories.advance_payment_generation_repository import (
    AdvancePaymentGenerationRepository,
)
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.advance_payments.repositories.advance_payment_turnover_lookup_repository import (
    TurnoverLookupRepository,
    TurnoverResolution,
)
from app.advance_payments.schemas.advance_payment import (
    AdvancePaymentClosingReadinessResponse,
)
from app.advance_payments.services import advance_payment_amendment_service as amendment
from app.audit.audit_constants import (
    ACTION_ADVANCE_PAYMENT_CREATED,
    ACTION_ADVANCE_PAYMENT_DELETED,
    ACTION_ADVANCE_PAYMENT_TURNOVER_REFRESHED,
    ACTION_ADVANCE_PAYMENT_UPDATED,
    ENTITY_ADVANCE_PAYMENT,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.clients.guards.client_record_guards import assert_client_record_is_active
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import AdvancePaymentFrequency, ObligationStatus, ObligationType
from app.common.obligation_chain import assert_deletable, closing_lateness_fields
from app.common.obligation_closing import (
    CLOSING_ASSIGNEE_REQUIRED_ISSUE,
    compute_closed_late,
)
from app.common.obligation_lifecycle import (
    LOCKED_MESSAGE,
    assert_transition_allowed,
    is_locked,
    is_terminal,
    stage_index,
    stages_between,
)
from app.common.obligation_plan import advance_payment_obligation_plan
from app.common.period_utils import parse_period_year
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.utils.time_utils import israel_today, utcnow

logger = logging.getLogger(__name__)

_SYSTEM_ACTOR_DISPLAY = "מערכת"

# Marks audit entries written by the office-wide run, so a schedule created in
# bulk is distinguishable from one an advisor generated for a single client.
_BULK_GENERATE_AUDIT_SOURCE = "bulk_generate"

# Required audit metadata on advance_payment.deleted. Says what removed the row,
# since no advisor typed a reason for this one.
_STALE_CADENCE_DELETE_REASON = "ניקוי אוטומטי: תדירות המקדמות של הלקוח שונתה"


@dataclass
class StaleCadenceOutcome:
    """Superseded-cadence rows blocking a year's schedule, split by what can be done.

    ``pending`` rows a confirmed cleanup can remove; ``settled`` rows it never
    will, because a paid or part-paid period is a fact, not a leftover.
    """

    pending: int = 0
    settled: int = 0


@dataclass
class BulkGenerateResult:
    """One chunk of an office-wide generation.

    ``next_cursor`` is ``None`` on the final chunk. ``failed`` carries the
    clients whose own generation raised — reported, never swallowed.
    """

    clients_processed: int = 0
    created: int = 0
    skipped: int = 0
    stale_removed: int = 0
    stale_pending: int = 0
    stale_settled: int = 0
    failed: list[tuple[int, str, str]] = field(default_factory=list)
    next_cursor: int | None = None


@dataclass
class BulkRefreshTurnoverResult:
    """Outcome counts of a bulk turnover refresh.

    Skips are split by reason because each one asks the advisor for a different
    follow-up: chase the missing return, or wait for the pending one to be filed.
    """

    refreshed: int = 0
    skipped_no_vat: int = 0
    skipped_not_filed: int = 0
    skipped_paid: int = 0
    skipped_closed: int = 0


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
            "assigned_to": payment.assigned_to,
            "expected_amount": payment.expected_amount,
            "paid_amount": payment.paid_amount,
            "payment_method": payment.payment_method,
            "payment_reference": payment.payment_reference,
            "annual_report_id": payment.annual_report_id,
            "notes": payment.notes,
            "advance_rate": payment.advance_rate,
            "turnover_amount": payment.turnover_amount,
            "turnover_source": payment.turnover_source,
            "turnover_snapshot_at": payment.turnover_snapshot_at,
            "calculated_amount": payment.calculated_amount,
            "override_amount": payment.override_amount,
            "withheld_amount": payment.withheld_amount,
            "status": payment.status,
            "paid_at": payment.paid_at,
            "closed_at": payment.closed_at,
            "closed_by": payment.closed_by,
            "closed_late": payment.closed_late,
        }

    @staticmethod
    def _assert_unlocked(payment: AdvancePayment) -> None:
        """Nothing on a closed record changes (D-13) — not figures, metadata, or notes."""
        if is_locked(payment.status):
            raise AppError(LOCKED_MESSAGE, ErrorCode.OBLIGATION_LOCKED)

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
        # The shared guard is the single client-eligibility rule across domains; this
        # used to re-derive it locally and raise 403 CLIENT.CLOSED / CLIENT.FROZEN,
        # which meant no caller could detect "not eligible" generically.
        assert_client_record_is_active(self._get_record_or_raise(client_record_id))

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

    def _compute_amounts(
        self,
        turnover_amount,
        advance_rate,
        override_amount,
        withheld_amount=None,
        fallback_expected=None,
    ) -> tuple[Decimal, Decimal]:
        # calculated_amount always stays gross (turnover × rate) — withheld_amount
        # is a deduction line applied only when deriving expected_amount, never
        # folded into calculated_amount itself.
        calculated = Decimal("0.00")
        if turnover_amount is not None and advance_rate is not None:
            calculated = (
                Decimal(str(turnover_amount)) * Decimal(str(advance_rate)) / 100
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if override_amount is not None:
            # override_amount is the final say — it wins even over withheld_amount.
            expected = Decimal(str(override_amount))
        elif fallback_expected is not None and calculated == 0:
            expected = Decimal(str(fallback_expected))
        else:
            withheld = Decimal(str(withheld_amount or 0))
            expected = max(Decimal("0.00"), calculated - withheld)
        return calculated, expected

    @staticmethod
    def _payment_status_steps(
        current: ObligationStatus, paid_amount, expected_amount
    ) -> tuple[ObligationStatus, ...]:
        """Each stage a money event walks through, in order — empty when it stays put.

        Status used to be *derived* from the amounts on every write, which had two
        consequences. Recomputing the expected amount could silently drag a settled
        period backwards — a turnover refresh could turn a paid advance into a
        part-paid one. And money alone could mark a period finished, with nobody
        confirming it had been reported.

        Money now advances the obligation and never locks or rewinds it:

        - a recorded payment moves it to `in_progress`
        - paid in full moves it to `awaiting_verification`
        - only a person moves it to `submitted`
        - a terminal record is untouched, and the stage never goes down

        Reaching `in_progress` from `awaiting_input` crosses two stages. That is two
        real transitions performed by one event, not a skipped stage: the shared
        graph validates each step and the caller records each one.
        """
        if is_terminal(current):
            return ()
        paid = Decimal(str(paid_amount or 0))
        if paid <= 0:
            return ()
        expected = Decimal(str(expected_amount or 0))
        target = (
            ObligationStatus.AWAITING_VERIFICATION
            if expected > 0 and paid >= expected
            else ObligationStatus.IN_PROGRESS
        )
        if stage_index(target) <= stage_index(current):
            return ()
        steps = stages_between(current, target)
        previous = current
        for step in steps:
            assert_transition_allowed(previous, step)
            previous = step
        return steps

    def _record_status_steps(
        self,
        payment: AdvancePayment,
        from_status: ObligationStatus,
        steps: tuple[ObligationStatus, ...],
        *,
        actor_id: int | None,
        actor_name: str | None,
        source: str | None = None,
    ) -> None:
        """One ``status_changed`` audit row per stage crossed, like the other domains."""
        previous = from_status
        for step in steps:
            self._audit.record_status_change(
                ENTITY_ADVANCE_PAYMENT,
                payment.id,
                actor_id,
                previous,
                step,
                metadata_json=self._audit_metadata(payment, source=source),
                **self._actor_kwargs(actor_id, actor_name),
            )
            previous = step

    def _invalidate_annual_report_tax(self, client_record_id: int, periods) -> None:
        """Clear the persisted tax of any open annual report these periods feed.

        The annual report's ``advances_paid`` comes from an aggregate that both sums
        ``paid_amount`` and filters on ``status == PAID``, so *any* write that can move
        either one invalidates a previously saved ``tax_due``/``refund_due`` — including
        a settled row dropping back to PARTIAL, not only a row becoming PAID.

        Called unconditionally by every such write path rather than gated on the
        resulting status: the gate is what made this miss transitions. It is a cheap
        no-op when the client has no open pre-submission report for the year.

        The import is deferred because ``annual_reports`` imports this domain's
        repositories, so a module-level import would close the cycle. Relocating this
        dependency behind a published contract is tracked in the tax-lifecycle plan.
        """
        from app.annual_reports.services.annual_report_tax_service import (
            AnnualReportTaxService,
        )

        tax_years = {parse_period_year(period) for period in periods if period}
        if not tax_years:
            return
        tax_service = AnnualReportTaxService(self.db)
        for tax_year in tax_years:
            tax_service.invalidate_tax_if_open(client_record_id, tax_year)

    # ─── List ─────────────────────────────────────────────────────────────────

    def list_payments_for_client(
        self,
        client_record_id: int,
        year: int | None = None,
        status: list[ObligationStatus] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AdvancePayment], int]:
        if year is None:
            year = utcnow().year
        self._get_record_or_raise(client_record_id)
        return self.repo.list_by_client_record_year(
            client_record_id, year, status=status, page=page, page_size=page_size
        )

    def create_amendment(self, **kwargs) -> AdvancePayment:
        return amendment.create_amendment(self, **kwargs)

    def withdraw_amendment(self, **kwargs) -> AdvancePayment:
        return amendment.withdraw(self, **kwargs)

    def list_chain(self, **kwargs) -> list[AdvancePayment]:
        return amendment.list_chain(self, **kwargs)

    def get_payment_for_client(self, client_record_id: int, payment_id: int) -> AdvancePayment:
        self._get_record_or_raise(client_record_id)
        payment = self.repo.get_by_id_for_client_record(payment_id, client_record_id)
        if payment is None:
            raise NotFoundError(
                f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
                ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
            )
        return payment

    # ─── Closing gate ─────────────────────────────────────────────────────────

    @staticmethod
    def _closing_issues(payment: AdvancePayment) -> list[str]:
        """What blocks this period from being closed (§4.1.8).

        Payment in full is not a gate (D-16). "Expected amount is computed" means
        the row can state what should be paid: an override, a rate to derive it
        from, or a hand-entered expected amount (which bulk repricing preserves).
        """
        issues: list[str] = []
        if payment.assigned_to is None:
            issues.append(CLOSING_ASSIGNEE_REQUIRED_ISSUE)
        if payment.turnover_amount is None:
            issues.append(ADVANCE_PAYMENT_TURNOVER_UNKNOWN_ISSUE)
        expected_computable = (
            payment.override_amount is not None
            or payment.advance_rate is not None
            or payment.expected_amount > 0
        )
        if not expected_computable:
            issues.append(ADVANCE_PAYMENT_EXPECTED_NOT_COMPUTED_ISSUE)
        return issues

    def get_closing_readiness(
        self, client_record_id: int, payment_id: int
    ) -> AdvancePaymentClosingReadinessResponse:
        payment = self.get_payment_for_client(client_record_id, payment_id)
        issues = self._closing_issues(payment)
        return AdvancePaymentClosingReadinessResponse(
            advance_payment_id=payment.id,
            is_ready=not issues,
            issues=issues,
        )

    # ─── Manual status transition ─────────────────────────────────────────────

    def transition_status_for_client(
        self,
        client_record_id: int,
        payment_id: int,
        *,
        new_status: ObligationStatus,
        note: str | None = None,
        actor_id: int,
        actor_name: str | None = None,
    ) -> AdvancePayment:
        """One advisor-driven step on the shared ladder (§4.1.9).

        Money still advances the record on its own (D-8's shortcut); this is the
        human route — including the close, which only a person may perform. On
        SUBMITTED the closing gate is asserted and the closing facts are written:
        who, when, and whether it was late (D-13, D-20).
        """
        self._get_record_or_raise(client_record_id)
        payment = self.repo.get_by_id_for_client_record(payment_id, client_record_id)
        if not payment:
            raise NotFoundError(
                f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
                ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
            )
        assert_transition_allowed(payment.status, new_status, reason=note)

        fields: dict = {"status": new_status}
        if new_status == ObligationStatus.SUBMITTED:
            issues = self._closing_issues(payment)
            if issues:
                raise AppError(
                    ADVANCE_PAYMENT_NOT_READY_TO_CLOSE.format(issues="; ".join(issues)),
                    ErrorCode.ADVANCE_PAYMENT_NOT_READY,
                )
            close_time = utcnow()
            fields["closed_at"] = close_time
            fields["closed_by"] = actor_id
            fields.update(
                closing_lateness_fields(
                    payment,
                    compute_closed_late(close_time, payment.due_date_effective or payment.due_date),
                )
            )

        old_status = payment.status
        updated = self.repo.update_payment(payment, **fields)
        metadata = self._audit_metadata(updated)
        if new_status == ObligationStatus.SUBMITTED:
            metadata["closed_by"] = updated.closed_by
            metadata["closed_late"] = updated.closed_late
        self._audit.record_status_change(
            ENTITY_ADVANCE_PAYMENT,
            updated.id,
            actor_id,
            old_status,
            new_status,
            note=note,
            metadata_json=metadata,
            **self._actor_kwargs(actor_id, actor_name),
        )
        return updated

    # ─── Create ───────────────────────────────────────────────────────────────

    def create_payment_for_client(
        self,
        client_record_id: int,
        period: str,
        period_months_count: int | None,
        assigned_to: int | None = None,
        expected_amount=None,
        paid_amount=None,
        payment_method=None,
        payment_reference: str | None = None,
        annual_report_id: int | None = None,
        notes: str | None = None,
        turnover_amount=None,
        advance_rate=None,
        override_amount=None,
        withheld_amount=None,
        actor_id: int | None = None,
        actor_name: str | None = None,
        audit_source: str | None = None,
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
        # Period alignment and the supported months-count are validated once, by
        # TaxCalendarMaterializationService.ensure_periodic_entry below.
        # Slot occupancy, not visibility: a cancelled period is free to be created
        # fresh (D-23) and a superseded original still holds its slot.
        if self.repo.get_slot_occupant_for_period(client_record_id, period):
            raise ConflictError(
                f"תשלום מקדמה לתקופה {period} כבר קיים",
                ErrorCode.ADVANCE_PAYMENT_CONFLICT,
            )

        if advance_rate is None:
            record = self._get_record_or_raise(client_record_id)
            le = LegalEntityRepository(self.db).get_by_id(record.legal_entity_id)
            advance_rate = le.advance_rate if le else None

        calculated_amount, resolved_expected = self._compute_amounts(
            turnover_amount,
            advance_rate,
            override_amount,
            withheld_amount=withheld_amount,
            fallback_expected=expected_amount,
        )

        mat = TaxCalendarMaterializationService(self.db)
        entry = mat.ensure_periodic_entry(
            ObligationType.ADVANCE_PAYMENT,
            period,
            period_months_count,
        )
        status_steps = self._payment_status_steps(
            ObligationStatus.AWAITING_INPUT, paid_amount, resolved_expected
        )
        payment = self.repo.create(
            client_record_id=client_record_id,
            assigned_to=assigned_to,
            period=period,
            period_months_count=period_months_count,
            due_date=entry.due_date,
            expected_amount=resolved_expected,
            paid_amount=paid_amount,
            payment_method=payment_method,
            payment_reference=payment_reference,
            annual_report_id=annual_report_id,
            tax_calendar_entry_id=entry.id,
            notes=notes,
            advance_rate=advance_rate,
            turnover_amount=turnover_amount,
            turnover_source=None if turnover_amount is None else TurnoverSource.MANUAL,
            turnover_snapshot_at=None if turnover_amount is None else utcnow(),
            calculated_amount=calculated_amount,
            override_amount=override_amount,
            withheld_amount=withheld_amount,
            status=status_steps[-1] if status_steps else ObligationStatus.AWAITING_INPUT,
        )
        payment = mat.link_advance_payment(payment)
        self._audit.record_action(
            ENTITY_ADVANCE_PAYMENT,
            payment.id,
            actor_id,
            ACTION_ADVANCE_PAYMENT_CREATED,
            new_value=self._audit_snapshot(payment),
            metadata_json=self._audit_metadata(payment, source=audit_source),
            **self._actor_kwargs(actor_id, actor_name),
        )
        self._record_status_steps(
            payment,
            ObligationStatus.AWAITING_INPUT,
            status_steps,
            actor_id=actor_id,
            actor_name=actor_name,
            source=audit_source,
        )
        return payment

    # ─── Update ───────────────────────────────────────────────────────────────

    _ALLOWED_UPDATE_FIELDS = {
        "paid_amount",
        "expected_amount",
        "paid_at",
        "payment_method",
        "payment_reference",
        "notes",
        "turnover_amount",
        "override_amount",
        "withheld_amount",
        "assigned_to",
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
        self._assert_unlocked(payment)
        filtered = {k: v for k, v in fields.items() if k in self._ALLOWED_UPDATE_FIELDS}

        # A hand-typed turnover must stop claiming VAT provenance, otherwise the
        # record keeps showing a VAT source for a figure the advisor overwrote.
        if "turnover_amount" in filtered:
            filtered["turnover_source"] = (
                None if filtered["turnover_amount"] is None else TurnoverSource.MANUAL
            )
            filtered["turnover_snapshot_at"] = (
                None if filtered["turnover_amount"] is None else utcnow()
            )

        calc_fields = {"turnover_amount", "override_amount", "withheld_amount"}
        if calc_fields & filtered.keys():
            effective_t = filtered.get("turnover_amount", payment.turnover_amount)
            effective_r = payment.advance_rate
            effective_o = filtered.get("override_amount", payment.override_amount)
            effective_w = filtered.get("withheld_amount", payment.withheld_amount)
            calculated_amount, new_expected = self._compute_amounts(
                effective_t, effective_r, effective_o, withheld_amount=effective_w
            )
            filtered["calculated_amount"] = calculated_amount
            filtered["expected_amount"] = new_expected
        old_status = payment.status
        status_steps: tuple[ObligationStatus, ...] = ()
        status_inputs = {"paid_amount", "expected_amount", "turnover_amount", "override_amount"}
        if status_inputs & filtered.keys():
            paid = filtered.get("paid_amount", payment.paid_amount)
            expected = filtered.get("expected_amount", payment.expected_amount)
            status_steps = self._payment_status_steps(old_status, paid, expected)
            if status_steps:
                filtered["status"] = status_steps[-1]

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
        self._record_status_steps(
            updated, old_status, status_steps, actor_id=actor_id, actor_name=actor_name
        )
        self._invalidate_annual_report_tax(client_record_id, [updated.period])
        return updated

    # ─── Bulk mark-paid ───────────────────────────────────────────────────────

    def bulk_mark_paid(
        self,
        payment_ids: list[int],
        *,
        paid_at=None,
        payment_method=None,
        reference_prefix: str | None = None,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> tuple[list[int], list[tuple[int, str]]]:
        """Top up each payment to its expected amount and mark it paid.

        Partial payments are included by decision — the client settled the
        difference. Fully-paid rows and rows with nothing due are skipped and
        reported by reason. Returns (updated_ids, [(id, skip_reason), ...]).
        """
        if paid_at is None:
            paid_at = utcnow()
        payments = {p.id: p for p in self.repo.get_active_by_ids(payment_ids)}
        updated: list[int] = []
        skipped: list[tuple[int, str]] = []
        # This command is cross-client (it is driven by the org-wide overview), so the
        # settled periods are grouped per client before invalidating annual reports.
        settled_periods_by_client: dict[int, list[str]] = {}

        for payment_id in payment_ids:
            payment = payments.get(payment_id)
            if payment is None:
                skipped.append((payment_id, "not_found"))
                continue
            # A closed period is immutable (D-13). Checked before the money
            # questions: a closed-but-underpaid period must be skipped as closed,
            # not topped up.
            if is_locked(payment.status):
                skipped.append((payment_id, "closed"))
                continue
            # Money, not lifecycle: this asks whether there is anything left to
            # top up.
            if payment.is_paid_in_full:
                skipped.append((payment_id, "already_paid"))
                continue
            if payment.expected_amount <= 0:
                skipped.append((payment_id, "no_amount"))
                continue

            # Recording money in bulk moves the period to awaiting verification,
            # not to submitted. Someone still has to confirm it was reported.
            old_status = payment.status
            status_steps = self._payment_status_steps(
                old_status, payment.expected_amount, payment.expected_amount
            )
            fields: dict = {
                "paid_amount": payment.expected_amount,
                "paid_at": paid_at,
            }
            if status_steps:
                fields["status"] = status_steps[-1]
            if payment_method is not None:
                fields["payment_method"] = payment_method
            if reference_prefix:
                fields["payment_reference"] = f"{reference_prefix}-{payment.id}"

            old_snapshot = self._audit_snapshot(payment)
            saved = self.repo.update_payment(payment, **fields)
            self._audit.record_action(
                ENTITY_ADVANCE_PAYMENT,
                saved.id,
                actor_id,
                ACTION_ADVANCE_PAYMENT_UPDATED,
                old_value=old_snapshot,
                new_value=self._audit_snapshot(saved),
                metadata_json=self._audit_metadata(saved, source="bulk_mark_paid"),
                **self._actor_kwargs(actor_id, actor_name),
            )
            self._record_status_steps(
                saved,
                old_status,
                status_steps,
                actor_id=actor_id,
                actor_name=actor_name,
                source="bulk_mark_paid",
            )
            updated.append(saved.id)
            settled_periods_by_client.setdefault(saved.client_record_id, []).append(saved.period)

        for settled_client_id, settled_periods in settled_periods_by_client.items():
            self._invalidate_annual_report_tax(settled_client_id, settled_periods)
        return updated, skipped

    # ─── Bulk rate update ───────────────────────────────────────────────────────

    def bulk_update_rate_from_period(
        self,
        client_record_id: int,
        *,
        advance_rate: Decimal,
        from_period: str,
        actor_id: int | None = None,
        actor_role=None,
        actor_name: str | None = None,
    ) -> tuple[int, int]:
        """Apply a new advance rate to a client's future unpaid periods.

        Reprices only PENDING rows at or after ``from_period`` (partial rows are
        already mid-settlement, paid rows are closed — both are reported as
        skipped). Recomputes each row's expected amount from the new rate, then
        rewrites the legal-entity default rate so newly generated periods inherit
        it. Returns ``(updated, skipped)``.

        Rows with no turnover have nothing to reprice (rate × nothing is nothing),
        so their manually entered expected amount is preserved via
        ``fallback_expected`` — the new rate is still stamped on the row so a later
        turnover refresh computes from it.
        """
        self._get_record_or_raise(client_record_id)
        rows = self.repo.list_from_period(client_record_id, from_period)
        updated = 0
        skipped = 0

        for payment in rows:
            if payment.status != ObligationStatus.AWAITING_INPUT:
                skipped += 1
                continue
            calculated_amount, new_expected = self._compute_amounts(
                payment.turnover_amount,
                advance_rate,
                payment.override_amount,
                withheld_amount=payment.withheld_amount,
                fallback_expected=payment.expected_amount,
            )
            old_status = payment.status
            status_steps = self._payment_status_steps(old_status, payment.paid_amount, new_expected)
            fields: dict = {
                "advance_rate": advance_rate,
                "calculated_amount": calculated_amount,
                "expected_amount": new_expected,
            }
            if status_steps:
                fields["status"] = status_steps[-1]
            old_snapshot = self._audit_snapshot(payment)
            saved = self.repo.update_payment(payment, **fields)
            self._audit.record_action(
                ENTITY_ADVANCE_PAYMENT,
                saved.id,
                actor_id,
                ACTION_ADVANCE_PAYMENT_UPDATED,
                old_value=old_snapshot,
                new_value=self._audit_snapshot(saved),
                metadata_json=self._audit_metadata(saved, source="bulk_rate_update"),
                **self._actor_kwargs(actor_id, actor_name),
            )
            self._record_status_steps(
                saved,
                old_status,
                status_steps,
                actor_id=actor_id,
                actor_name=actor_name,
                source="bulk_rate_update",
            )
            updated += 1

        # The rate change is going-forward: the legal-entity default must follow
        # so the next generated schedule seeds from it (stamp + LE audit are owned
        # by ClientUpdateService). Imported locally to avoid a service import cycle.
        from app.clients.services.client_update_service import ClientUpdateService

        ClientUpdateService(self.db).update_client(
            client_record_id,
            advance_rate=advance_rate,
            actor_id=actor_id,
            actor_role=actor_role,
            actor_name=actor_name,
        )
        # No annual-report invalidation here by design: this loop skips every row that is
        # not PENDING, and a PENDING row has paid_amount == 0, so repricing can never move
        # a row into or out of the PAID set the annual report's advances_paid sums over.
        return updated, skipped

    # ─── Delete ───────────────────────────────────────────────────────────────

    def delete_payment_for_client(
        self,
        client_record_id: int,
        payment_id: int,
        actor_id: int,
        actor_name: str | None = None,
        *,
        reason: str,
    ) -> None:
        self._get_record_or_raise(client_record_id)
        payment = self.repo.get_by_id_for_client_record(payment_id, client_record_id)
        if not payment:
            raise NotFoundError(
                f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
                ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
            )
        # A closed period is never removed — it is kept and reported (D-13, D-22).
        self._assert_unlocked(payment)
        self._soft_delete_payment(payment, actor_id=actor_id, actor_name=actor_name, reason=reason)

    def _soft_delete_payment(
        self,
        payment: AdvancePayment,
        *,
        actor_id: int | None,
        actor_name: str | None,
        reason: str,
    ) -> None:
        """Soft-delete one payment and audit why.

        Shared by the advisor's explicit delete and the stale-cadence cleanup;
        ``reason`` is required metadata on ``advance_payment.deleted``, so every
        path that removes a row has to say what removed it. The chain gate lives
        here rather than at the advisor's entry point because it is a fact about
        the row, and the cleanup selects on cadence and due date — neither of
        which excludes an amendment.
        """
        assert_deletable(payment)
        old_snapshot = self._audit_snapshot(payment)
        self.repo.soft_delete(payment.id, deleted_by=actor_id)
        metadata = self._audit_metadata(payment)
        metadata["reason"] = reason
        self._audit.record_action(
            ENTITY_ADVANCE_PAYMENT,
            payment.id,
            actor_id,
            ACTION_ADVANCE_PAYMENT_DELETED,
            old_value=old_snapshot,
            metadata_json=metadata,
            **self._actor_kwargs(actor_id, actor_name),
        )

    # ─── Stale cadence cleanup ────────────────────────────────────────────────

    def _future_stale_cadence_rows(
        self,
        client_record_id: int,
        year: int,
        period_months_count: int,
        reference_date: date,
    ) -> list[AdvancePayment]:
        """Rows of a superseded cadence that still lie ahead of ``reference_date``.

        Past-due rows are deliberately left out however stale their cadence is:
        an unpaid period whose due date has passed is a real debt, and the
        generator would not have recreated it anyway.
        """
        rows = self.repo.list_stale_cadence_for_year(client_record_id, year, period_months_count)
        return [row for row in rows if (row.due_date_effective or row.due_date) >= reference_date]

    def count_stale_cadence(
        self,
        client_record_id: int,
        year: int,
        reference_date: date | None = None,
    ) -> StaleCadenceOutcome:
        """Report the superseded-cadence rows standing in the new schedule's way.

        Split by what can be done about them: ``pending`` rows are removable by a
        confirmed cleanup, ``settled`` rows never are — a paid period from the old
        cadence permanently occupies its ``YYYY-MM`` key, so that part of the year
        stays on the old shape until someone resolves it by hand.
        """
        if reference_date is None:
            reference_date = israel_today()
        self._get_record_or_raise(client_record_id)
        period_months_count = self.default_period_months_count_for_client(client_record_id)
        outcome = StaleCadenceOutcome()
        for row in self._future_stale_cadence_rows(
            client_record_id, year, period_months_count, reference_date
        ):
            if row.status == ObligationStatus.AWAITING_INPUT:
                outcome.pending += 1
            else:
                outcome.settled += 1
        return outcome

    # ─── Generate schedule ────────────────────────────────────────────────────

    def generate_annual_schedule(
        self,
        client_record_id: int,
        year: int,
        period_months_count: int | None = None,
        reference_date: date | None = None,
        actor_id: int | None = None,
        actor_name: str | None = None,
        audit_source: str | None = None,
        cleanup_stale_cadence: bool = False,
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

        # Resolved before the loop, never as a consequence of it: the existence
        # check below matches on the YYYY-MM key alone, so a row of the superseded
        # cadence makes the generator skip the very period it should replace.
        removable = [
            row
            for row in self._future_stale_cadence_rows(
                client_record_id, year, period_months_count, reference_date
            )
            if row.status == ObligationStatus.AWAITING_INPUT
        ]
        if removable and not cleanup_stale_cadence:
            # Generate nothing rather than part of the year. Only the periods the
            # stale rows do *not* occupy would be created, which is how a client
            # ends up with both cadences covering the same month — the exact mess
            # the confirmation exists to prevent. The caller reports and re-asks.
            return [], 0
        for row in removable:
            self._soft_delete_payment(
                row,
                actor_id=actor_id,
                actor_name=actor_name,
                reason=_STALE_CADENCE_DELETE_REASON,
            )

        tax_calendar = TaxCalendarMaterializationService(self.db)
        created: list[AdvancePayment] = []
        skipped = 0
        # The obligation plan decides which periods are owed — the same answer
        # onboarding uses. This loop used to build its own month list and then trim
        # it with `entry.due_date < reference_date`, which is a *calendar* guard
        # standing in for a *liability* guard: it created periods the client was
        # not yet liable for and skipped genuinely owed past-due ones. Two
        # generation paths with two different rules is the divergence this
        # refactor exists to remove.
        record = self._get_record_or_raise(client_record_id)
        legal_entity = LegalEntityRepository(self.db).get_by_id(record.legal_entity_id)
        plans = advance_payment_obligation_plan(
            frequency=legal_entity.advance_payment_frequency,
            year=year,
            entity_type=getattr(legal_entity, "entity_type", None),
            liable_from=getattr(legal_entity, "advance_liable_from", None),
            liable_to=getattr(legal_entity, "advance_liable_to", None),
        )
        for plan in plans:
            period = plan.period
            tax_calendar.ensure_periodic_entry(
                ObligationType.ADVANCE_PAYMENT,
                period,
                period_months_count,
            )
            if self.repo.get_slot_occupant_for_period(client_record_id, period):
                skipped += 1
                continue
            payment = self.create_payment_for_client(
                client_record_id=client_record_id,
                period=period,
                period_months_count=period_months_count,
                actor_id=actor_id,
                actor_name=actor_name,
                audit_source=audit_source,
            )
            created.append(payment)
        return created, skipped

    # ─── Office-wide generation ───────────────────────────────────────────────

    def bulk_generate_annual_schedules(
        self,
        year: int,
        *,
        cursor: int | None = None,
        cleanup_stale_cadence: bool = False,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> BulkGenerateResult:
        """Generate one chunk of the office's annual schedules.

        The run is deliberately split across requests: the caller repeats with
        the returned cursor until it comes back ``None``. Chunk boundaries are
        chosen here, not by the caller — eligibility and ordering are domain
        rules, and a caller-chosen batch could silently omit clients.

        Per-client business failures are collected rather than raised, so one
        misconfigured client cannot cost the chunk its other clients. A database
        error still fails the whole chunk: the transaction is no longer
        trustworthy at that point, and the caller can safely retry the same
        chunk under the same idempotency key.
        """
        gen_repo = AdvancePaymentGenerationRepository(self.db)
        client_ids = gen_repo.list_eligible_client_ids(
            after_id=cursor, limit=BULK_GENERATE_CLIENT_CHUNK_SIZE
        )
        result = BulkGenerateResult()
        if not client_ids:
            return result

        names = gen_repo.get_client_names(client_ids)
        for client_record_id in client_ids:
            try:
                # Measured before generating: once a cleanup has run the rows are
                # gone, and "how many did we remove" is exactly this count.
                stale = self.count_stale_cadence(client_record_id, year)
                created, skipped = self.generate_annual_schedule(
                    client_record_id,
                    year,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    audit_source=_BULK_GENERATE_AUDIT_SOURCE,
                    cleanup_stale_cadence=cleanup_stale_cadence,
                )
            except AppError as exc:
                result.failed.append(
                    (client_record_id, names.get(client_record_id, ""), exc.message)
                )
                logger.warning(
                    "Office-wide advance generation skipped client %s for year %s: %s",
                    client_record_id,
                    year,
                    exc.message,
                )
                continue
            result.created += len(created)
            result.skipped += skipped
            if cleanup_stale_cadence:
                result.stale_removed += stale.pending
            else:
                result.stale_pending += stale.pending
            result.stale_settled += stale.settled
        result.clients_processed = len(client_ids)

        # A short chunk means the keyset ran out — this was the last one.
        if len(client_ids) == BULK_GENERATE_CLIENT_CHUNK_SIZE:
            result.next_cursor = client_ids[-1]
        return result

    # ─── Snapshot turnover from VAT ───────────────────────────────────────────

    def refresh_turnover_from_vat(
        self,
        client_record_id: int,
        payment_id: int,
        *,
        confirm_pending: bool = False,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> AdvancePayment:
        """Snapshot the period's VAT turnover onto the payment and recompute amounts.

        Snapshotting from an unfiled VAT return requires ``confirm_pending``:
        the figure can still change before filing, but the snapshot it produces
        is indistinguishable from a settled one once written.
        """
        self._get_record_or_raise(client_record_id)
        payment = self.repo.get_by_id_for_client_record(payment_id, client_record_id)
        if not payment:
            raise NotFoundError(
                f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
                ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
            )

        self._assert_unlocked(payment)
        resolution = TurnoverLookupRepository(self.db).resolve_turnover(
            client_record_id, payment.period, payment.period_months_count
        )
        if not resolution.is_resolved:
            raise NotFoundError(
                f"לא נמצא דוח מע״מ לתקופה {payment.period}",
                ErrorCode.ADVANCE_PAYMENT_VAT_TURNOVER_NOT_FOUND,
            )
        if resolution.source == TurnoverSource.VAT_PENDING and not confirm_pending:
            raise ConflictError(
                f"דוח המע״מ לתקופה {payment.period} טרם הוגש",
                ErrorCode.ADVANCE_PAYMENT_VAT_NOT_FILED,
            )

        return self._apply_turnover_snapshot(
            payment, resolution, actor_id=actor_id, actor_name=actor_name
        )

    def refresh_turnover_bulk(
        self,
        client_record_id: int,
        payment_ids: list[int],
        *,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> BulkRefreshTurnoverResult:
        """Snapshot every listed period that has a fully filed VAT return.

        Unfiled returns and already-settled payments are never snapshotted in
        bulk: both are per-row judgements that cannot be given meaningfully for a
        whole batch, so those periods are reported as skipped instead.

        Not atomic by design. Each period is an independent business fact, so a
        period without a VAT return must not prevent its neighbours from being
        snapshotted. Ownership of every id is validated up front, before any
        write, so a malformed request still fails whole.
        """
        self._get_record_or_raise(client_record_id)
        # The API schema already rejects duplicate ids; this dedupe guards
        # direct service callers so one period can never be snapshotted (and
        # audited) twice within a single request.
        payments = []
        for payment_id in dict.fromkeys(payment_ids):
            payment = self.repo.get_by_id_for_client_record(payment_id, client_record_id)
            if not payment:
                raise NotFoundError(
                    f"תשלום מקדמה {payment_id} לא נמצא עבור לקוח {client_record_id}",
                    ErrorCode.ADVANCE_PAYMENT_NOT_FOUND,
                )
            payments.append(payment)

        resolved = TurnoverLookupRepository(self.db).resolve_turnover_for_client(
            client_record_id, [(p.period, p.period_months_count) for p in payments]
        )

        result = BulkRefreshTurnoverResult()
        for payment in payments:
            # A closed period is immutable (D-13) — skipped, not raised: one
            # closed row must not block its neighbours in a bulk sweep.
            if is_locked(payment.status):
                result.skipped_closed += 1
                continue
            # Money, not lifecycle: the question is whether the amounts are
            # settled, and a settled row now sits at awaiting_verification rather
            # than submitted. Snapshotting rewrites expected_amount, which is a
            # per-row judgement, not something one click should do to a whole
            # screenful of settled records.
            if payment.is_paid_in_full:
                result.skipped_paid += 1
                continue
            resolution = resolved.get(payment.period)
            if resolution is None or not resolution.is_resolved:
                result.skipped_no_vat += 1
                continue
            if resolution.source == TurnoverSource.VAT_PENDING:
                result.skipped_not_filed += 1
                continue
            self._apply_turnover_snapshot(
                payment, resolution, actor_id=actor_id, actor_name=actor_name
            )
            result.refreshed += 1
        return result

    def _apply_turnover_snapshot(
        self,
        payment: AdvancePayment,
        resolution: TurnoverResolution,
        *,
        actor_id: int | None,
        actor_name: str | None,
    ) -> AdvancePayment:
        """Freeze a resolved turnover onto the payment and record why."""
        calculated_amount, new_expected = self._compute_amounts(
            resolution.amount, payment.advance_rate, payment.override_amount
        )
        old_status = payment.status
        status_steps = self._payment_status_steps(old_status, payment.paid_amount, new_expected)
        fields: dict = {
            "turnover_amount": resolution.amount,
            "turnover_source": resolution.source,
            "turnover_snapshot_at": utcnow(),
            "calculated_amount": calculated_amount,
            "expected_amount": new_expected,
        }
        if status_steps:
            fields["status"] = status_steps[-1]
        old_snapshot = self._audit_snapshot(payment)
        updated = self.repo.update_payment(payment, **fields)
        self._audit.record_action(
            ENTITY_ADVANCE_PAYMENT,
            updated.id,
            actor_id,
            ACTION_ADVANCE_PAYMENT_TURNOVER_REFRESHED,
            old_value=old_snapshot,
            new_value=self._audit_snapshot(updated),
            metadata_json={
                **self._audit_metadata(updated, source=resolution.source.value),
                "vat_work_item_ids": resolution.vat_work_item_ids,
            },
            **self._actor_kwargs(actor_id, actor_name),
        )
        self._record_status_steps(
            updated,
            old_status,
            status_steps,
            actor_id=actor_id,
            actor_name=actor_name,
            source=resolution.source.value,
        )
        # Snapshotting rewrites expected_amount, which moves a row into or out of
        # paid-in-full — and that changes the annual report's advances_paid.
        self._invalidate_annual_report_tax(updated.client_record_id, [updated.period])
        return updated
