"""Frequency-change cleanup: superseded-cadence rows blocking a year's schedule."""

from decimal import Decimal
from itertools import count

import pytest

from app.advance_payments.models.advance_payment import AdvancePayment, AdvancePaymentStatus
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.common.enums import AdvancePaymentFrequency
from app.legal_entities.models.legal_entity import LegalEntity
from app.utils.time_utils import israel_today
from tests.helpers.identity import seed_client_identity

_seq = count(1)

# Ahead of today so no period is skipped for a due date that already passed.
FUTURE_YEAR = israel_today().year + 1


def _client(db, frequency=AdvancePaymentFrequency.BIMONTHLY):
    idx = next(_seq)
    record = seed_client_identity(
        db,
        full_name=f"Stale Cadence Client {idx}",
        id_number=f"STC{idx:06d}",
        advance_payment_frequency=frequency,
        advance_rate=Decimal("10"),
    )
    db.commit()
    return record


def _set_frequency(db, record, frequency):
    legal_entity = db.get(LegalEntity, record.legal_entity_id)
    legal_entity.advance_payment_frequency = frequency
    db.commit()


def _active_rows(db, record):
    return (
        db.query(AdvancePayment)
        .filter(
            AdvancePayment.client_record_id == record.id,
            AdvancePayment.deleted_at.is_(None),
        )
        .order_by(AdvancePayment.period)
        .all()
    )


def test_generation_is_blocked_until_the_cleanup_is_confirmed(test_db):
    record = _client(test_db)
    service = AdvancePaymentService(test_db)
    service.generate_annual_schedule(record.id, FUTURE_YEAR)
    test_db.commit()
    _set_frequency(test_db, record, AdvancePaymentFrequency.MONTHLY)

    created, skipped = AdvancePaymentService(test_db).generate_annual_schedule(
        record.id, FUTURE_YEAR
    )

    # Nothing at all: creating only the months the bimonthly rows do not occupy
    # is what leaves February covered twice.
    assert created == []
    assert skipped == 0
    rows = _active_rows(test_db, record)
    assert len(rows) == 6
    assert {row.period_months_count for row in rows} == {2}


def test_confirmed_cleanup_replaces_the_old_cadence(test_db):
    record = _client(test_db)
    service = AdvancePaymentService(test_db)
    service.generate_annual_schedule(record.id, FUTURE_YEAR)
    test_db.commit()
    _set_frequency(test_db, record, AdvancePaymentFrequency.MONTHLY)

    created, _ = AdvancePaymentService(test_db).generate_annual_schedule(
        record.id, FUTURE_YEAR, cleanup_stale_cadence=True
    )

    assert len(created) == 12
    rows = _active_rows(test_db, record)
    assert len(rows) == 12
    assert {row.period_months_count for row in rows} == {1}


def test_monthly_to_bimonthly_is_cleaned_too(test_db):
    record = _client(test_db, frequency=AdvancePaymentFrequency.MONTHLY)
    AdvancePaymentService(test_db).generate_annual_schedule(record.id, FUTURE_YEAR)
    test_db.commit()
    _set_frequency(test_db, record, AdvancePaymentFrequency.BIMONTHLY)

    created, _ = AdvancePaymentService(test_db).generate_annual_schedule(
        record.id, FUTURE_YEAR, cleanup_stale_cadence=True
    )

    assert len(created) == 6
    rows = _active_rows(test_db, record)
    assert len(rows) == 6
    assert {row.period_months_count for row in rows} == {2}


def test_settled_rows_survive_the_cleanup_and_keep_their_period(test_db):
    record = _client(test_db)
    service = AdvancePaymentService(test_db)
    service.generate_annual_schedule(record.id, FUTURE_YEAR)
    paid = next(r for r in _active_rows(test_db, record) if r.period == f"{FUTURE_YEAR}-01")
    service.update_payment_for_client(
        client_record_id=record.id,
        payment_id=paid.id,
        paid_amount=Decimal("500"),
        expected_amount=Decimal("500"),
        actor_id=None,
    )
    test_db.commit()
    _set_frequency(test_db, record, AdvancePaymentFrequency.MONTHLY)

    created, _ = AdvancePaymentService(test_db).generate_annual_schedule(
        record.id, FUTURE_YEAR, cleanup_stale_cadence=True
    )

    # January stays bimonthly because it is paid; the other eleven months are new.
    assert len(created) == 11
    rows = _active_rows(test_db, record)
    assert len(rows) == 12
    january = next(row for row in rows if row.period == f"{FUTURE_YEAR}-01")
    assert january.period_months_count == 2
    assert january.status == AdvancePaymentStatus.PAID


def test_count_stale_cadence_splits_removable_from_settled(test_db):
    record = _client(test_db)
    service = AdvancePaymentService(test_db)
    service.generate_annual_schedule(record.id, FUTURE_YEAR)
    paid = next(r for r in _active_rows(test_db, record) if r.period == f"{FUTURE_YEAR}-01")
    service.update_payment_for_client(
        client_record_id=record.id,
        payment_id=paid.id,
        paid_amount=Decimal("500"),
        expected_amount=Decimal("500"),
        actor_id=None,
    )
    test_db.commit()
    _set_frequency(test_db, record, AdvancePaymentFrequency.MONTHLY)

    outcome = AdvancePaymentService(test_db).count_stale_cadence(record.id, FUTURE_YEAR)

    assert outcome.pending == 5
    assert outcome.settled == 1


def test_matching_cadence_reports_nothing_and_generates_normally(test_db):
    record = _client(test_db)
    service = AdvancePaymentService(test_db)

    outcome = service.count_stale_cadence(record.id, FUTURE_YEAR)
    created, _ = service.generate_annual_schedule(record.id, FUTURE_YEAR)

    assert outcome.pending == 0
    assert outcome.settled == 0
    assert len(created) == 6


def test_past_due_rows_of_the_old_cadence_are_never_removed(test_db):
    """An unpaid period whose due date has passed is a debt, not a leftover."""
    record = _client(test_db)
    service = AdvancePaymentService(test_db)
    service.generate_annual_schedule(record.id, FUTURE_YEAR)
    test_db.commit()
    _set_frequency(test_db, record, AdvancePaymentFrequency.MONTHLY)

    rows = _active_rows(test_db, record)
    reference_date = max(row.due_date for row in rows)

    outcome = AdvancePaymentService(test_db).count_stale_cadence(
        record.id, FUTURE_YEAR, reference_date=reference_date
    )

    # Only the last period is still ahead of the reference date; the earlier
    # five are past due and out of the cleanup's reach.
    assert outcome.pending == 1
    assert outcome.settled == 0


@pytest.mark.parametrize("cleanup", [False, True])
def test_cleanup_soft_deletes_and_audits_with_a_reason(test_db, cleanup):
    from app.audit.audit_constants import ACTION_ADVANCE_PAYMENT_DELETED
    from app.audit.models.audit_entity_audit_log import EntityAuditLog

    record = _client(test_db)
    service = AdvancePaymentService(test_db)
    service.generate_annual_schedule(record.id, FUTURE_YEAR)
    test_db.commit()
    _set_frequency(test_db, record, AdvancePaymentFrequency.MONTHLY)

    AdvancePaymentService(test_db).generate_annual_schedule(
        record.id, FUTURE_YEAR, cleanup_stale_cadence=cleanup
    )
    test_db.commit()

    deletions = (
        test_db.query(EntityAuditLog)
        .filter(EntityAuditLog.action == ACTION_ADVANCE_PAYMENT_DELETED)
        .all()
    )
    if not cleanup:
        assert deletions == []
        return
    assert len(deletions) == 6
    assert all(entry.metadata_json.get("reason") for entry in deletions)
