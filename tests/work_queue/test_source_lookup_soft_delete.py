"""load_source_states must keep its deliberate lack of soft-delete / active-client scoping.

The work queue distinguishes deleted vs missing source rows, so the batched repo reads
use include_deleted=True and apply no active-client scope:

- a soft-deleted source resolves with is_deleted=True (not is_missing)
- a live source owned by a soft-deleted client still resolves (not is_missing)
"""

from __future__ import annotations

from decimal import Decimal

from app.charges.models.charge import ChargeStatus, ChargeType
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.client_enums import ClientStatus
from app.common.enums import IdNumberType, VatType
from app.common.source_types import WorkQueueSourceType
from app.utils.time_utils import utcnow
from app.work_queue.work_queue_source_lookup import load_source_states
from tests.helpers.identity import seed_client_identity


def test_soft_deleted_source_is_marked_deleted_not_missing(test_db, charge_factory):
    client = seed_client_identity(
        test_db,
        full_name="SL Client",
        id_number="SL-1",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    charge = charge_factory(
        client_record_id=client.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("90.00"),
        issued_at=utcnow(),
    )
    ChargeRepository(test_db).soft_delete(charge.id)

    states = load_source_states(test_db, [(WorkQueueSourceType.CHARGE, charge.id)])
    state = states[(WorkQueueSourceType.CHARGE.value, charge.id)]

    assert state.is_deleted is True
    assert state.is_missing is False


def test_live_source_of_soft_deleted_client_still_resolves(test_db, charge_factory):
    client = seed_client_identity(
        test_db,
        full_name="SL Deleted-Client",
        id_number="SL-2",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
        status=ClientStatus.CLOSED,
        deleted_at=utcnow(),
    )
    charge = charge_factory(
        client_record_id=client.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("90.00"),
        issued_at=utcnow(),
    )

    states = load_source_states(test_db, [(WorkQueueSourceType.CHARGE, charge.id)])
    state = states[(WorkQueueSourceType.CHARGE.value, charge.id)]

    assert state.is_missing is False
    assert state.is_deleted is False
    assert state.client_record_id == client.id
