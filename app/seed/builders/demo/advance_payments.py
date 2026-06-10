from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from random import Random

from sqlalchemy import select

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
    PaymentMethod,
)
from app.clients.models.client_record import ClientRecord
from app.clients.models.legal_entity import LegalEntity
from app.common.enums import EntityType, ObligationType
from app.common.obligation_plan import advance_payment_obligation_plan
from app.tax_calendar.services.materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem

from ..shared.client_refs import get_seed_client_record, get_seed_client_record_id

_VAT_FINAL_STATUSES = (VatWorkItemStatus.FILED,)
_VAT_PENDING_STATUSES = (VatWorkItemStatus.READY_FOR_REVIEW,)


def _lookup_vat_turnover(db, client_record_id: int, period: str) -> Decimal | None:
    for statuses in (_VAT_FINAL_STATUSES, _VAT_PENDING_STATUSES):
        row = db.execute(
            select(VatWorkItem.total_output_net).where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.period == period,
                VatWorkItem.status.in_(statuses),
                VatWorkItem.deleted_at.is_(None),
            )
        ).first()
        if row is not None and row.total_output_net is not None:
            return Decimal(str(row.total_output_net))
    return None


_HISTORICAL_YEARS = 3


def _resolve_status(period: str, current_year: int) -> AdvancePaymentStatus:
    period_year = int(period.split("-")[0])
    if period_year < current_year:
        return AdvancePaymentStatus.PAID
    return AdvancePaymentStatus.PENDING


def _apply_payment_fields(
    rng: Random,
    payment: AdvancePayment,
    status: AdvancePaymentStatus,
    period: str,
    le: LegalEntity | None = None,
    db=None,
    client_record_id: int | None = None,
) -> None:
    rate = Decimal(str(le.advance_rate)) if le and le.advance_rate else Decimal("0")
    vat_turnover = (
        _lookup_vat_turnover(db, client_record_id, period)
        if db is not None and client_record_id is not None
        else None
    )
    turnover_amount = (
        vat_turnover
        if vat_turnover is not None
        else Decimal(str(round(rng.uniform(10_000, 150_000), 2)))
    )
    calculated_amount = (turnover_amount * rate / 100).quantize(
        Decimal("0.01"), ROUND_HALF_UP
    )
    payment.advance_rate = rate
    payment.turnover_amount = turnover_amount
    payment.calculated_amount = calculated_amount
    payment.override_amount = None
    payment.expected_amount = calculated_amount

    payment.status = status
    if status == AdvancePaymentStatus.PAID:
        payment.paid_amount = payment.expected_amount
        payment.payment_method = rng.choice(list(PaymentMethod))
        period_dt = datetime.strptime(f"{period}-01", "%Y-%m-%d").replace(tzinfo=UTC)
        paid_at = period_dt + timedelta(days=rng.randint(14, 45))
        payment.paid_at = min(paid_at, datetime.now(UTC))
    elif status == AdvancePaymentStatus.PARTIAL:
        expected = payment.expected_amount
        payment.paid_amount = (
            expected * Decimal(str(round(rng.uniform(0.2, 0.8), 2)))
        ).quantize(Decimal("0.01"))
        payment.payment_method = rng.choice(list(PaymentMethod))
        period_dt = datetime.strptime(f"{period}-01", "%Y-%m-%d").replace(tzinfo=UTC)
        paid_at = period_dt + timedelta(days=rng.randint(14, 45))
        payment.paid_at = min(paid_at, datetime.now(UTC))
    else:
        payment.paid_amount = Decimal("0.00")
        payment.payment_method = None
        payment.paid_at = None


def create_advance_payments(db, rng: Random, cfg, businesses) -> list[AdvancePayment]:
    current_year = cfg.reference_date.year
    # Include current year so past-due periods in the current year are backfilled,
    # matching the VAT demo builder which also covers YTD periods.
    all_years = list(range(current_year - _HISTORICAL_YEARS, current_year + 1))
    mat = TaxCalendarMaterializationService(db)
    payments: list[AdvancePayment] = []

    _crs = [
        get_seed_client_record(b)
        for b in businesses
        if get_seed_client_record(b) is not None
    ]
    _le_ids = list({cr.legal_entity_id for cr in _crs})
    legal_entity_map: dict[int, LegalEntity] = {
        le.id: le
        for le in db.scalars(
            select(LegalEntity).where(LegalEntity.id.in_(_le_ids))
        ).all()
    }

    seen_clients: set[int] = set()
    for business in businesses:
        cr = get_seed_client_record(business)
        if cr is None:
            continue
        client_record_id = get_seed_client_record_id(business)
        if client_record_id in seen_clients:
            continue
        seen_clients.add(client_record_id)

        le = legal_entity_map.get(cr.legal_entity_id)
        frequency = le.advance_payment_frequency if le else None
        entity_type = le.entity_type if le else None
        if frequency is None or entity_type == EntityType.EMPLOYEE:
            continue

        for year in all_years:
            plans = advance_payment_obligation_plan(
                frequency=frequency,
                year=year,
                entity_type=entity_type,
            )
            for plan in plans:
                entry = mat.ensure_periodic_entry(
                    ObligationType.ADVANCE_PAYMENT,
                    plan.period,
                    plan.period_months_count,
                )
                # For the current year, only backfill periods whose due date has passed.
                if year == current_year and entry.due_date >= cfg.reference_date:
                    continue

                existing = db.scalars(
                    select(AdvancePayment).where(
                        AdvancePayment.client_record_id == client_record_id,
                        AdvancePayment.period == plan.period,
                        AdvancePayment.deleted_at.is_(None),
                    )
                ).first()
                status = _resolve_status(plan.period, current_year)

                if existing:
                    _apply_payment_fields(
                        rng, existing, status, plan.period, le, db, client_record_id
                    )
                    payments.append(existing)
                    continue

                payment = AdvancePayment(
                    client_record_id=client_record_id,
                    period=plan.period,
                    period_months_count=plan.period_months_count,
                    due_date=entry.due_date,
                    due_date_original=entry.due_date,
                    due_date_effective=entry.due_date,
                    expected_amount=Decimal("0.00"),
                    paid_amount=Decimal("0.00"),
                    status=AdvancePaymentStatus.PENDING,
                    tax_calendar_entry_id=entry.id,
                )
                _apply_payment_fields(
                    rng, payment, status, plan.period, le, db, client_record_id
                )
                db.add(payment)
                payments.append(payment)

    db.flush()

    # Sweep: fix any remaining PENDING payments from onboarding not reached above.
    db.expire_all()
    stragglers = db.scalars(
        select(AdvancePayment).where(
            AdvancePayment.period < f"{current_year}-01",
            AdvancePayment.status == AdvancePaymentStatus.PENDING,
            AdvancePayment.deleted_at.is_(None),
        )
    ).all()
    straggler_client_ids = {p.client_record_id for p in stragglers}
    straggler_cr_map: dict[int, ClientRecord] = {
        cr.id: cr
        for cr in db.scalars(
            select(ClientRecord).where(ClientRecord.id.in_(straggler_client_ids))
        ).all()
    }
    for p in stragglers:
        cr = straggler_cr_map.get(p.client_record_id)
        le = legal_entity_map.get(cr.legal_entity_id) if cr else None
        status = _resolve_status(p.period, current_year)
        _apply_payment_fields(rng, p, status, p.period, le, db, p.client_record_id)

    db.flush()
    return payments
