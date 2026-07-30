"""Regression: BaseRepository.get() soft-delete semantics after the Session.get rewrite.

get() must still hide soft-deleted rows by default and surface them with
include_deleted=True, while delegating the PK lookup to the identity-map-aware
Session.get().
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.charges.models.charge import ChargeStatus, ChargeType
from app.charges.repositories.charge_repository import ChargeRepository
from app.common.enums import IdNumberType, VatType
from app.utils.time_utils import utcnow


def test_get_hides_soft_deleted_by_default(test_db, client_factory, charge_factory):
    client = client_factory(
        full_name="Base Repo Client",
        id_number="BRC-1",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    charge = charge_factory(
        client_record_id=client.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("100.00"),
        issued_at=utcnow(),
    )
    repo = ChargeRepository(test_db)

    # Sanity: visible while not deleted.
    assert repo.get(charge.id) is not None

    repo.soft_delete(charge.id)

    assert repo.get(charge.id) is None
    assert repo.get_by_id(charge.id) is None


def test_get_returns_soft_deleted_with_include_deleted(test_db, client_factory, charge_factory):
    client = client_factory(
        full_name="Base Repo Client 2",
        id_number="BRC-2",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    charge = charge_factory(
        client_record_id=client.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("100.00"),
        issued_at=utcnow(),
    )
    repo = ChargeRepository(test_db)
    repo.soft_delete(charge.id)

    fetched = repo.get(charge.id, include_deleted=True)
    assert fetched is not None
    assert fetched.id == charge.id
    assert fetched.deleted_at is not None


def test_get_by_id_for_update_refreshes_a_row_already_in_the_identity_map(
    test_db, client_factory, charge_factory
):
    """The lock is worthless if the row it returns is the one already loaded.

    A caller that reads an entity, then locks it, then re-checks its gate is
    guarding against exactly one thing: the state changing in between. Without
    ``populate_existing`` the second read returns the identity-mapped object with
    its original attribute values, so the re-check passes on the state that was
    already known to be stale.
    """
    client = client_factory(
        full_name="Locked Read Client",
        id_number="BRC-LOCK-1",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    charge = charge_factory(
        client_record_id=client.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("100.00"),
        issued_at=utcnow(),
    )
    repo = ChargeRepository(test_db)
    loaded = repo.get_by_id(charge.id)
    assert loaded is not None and loaded.status == ChargeStatus.ISSUED

    # Behind the ORM's back, the way another transaction would have left it.
    test_db.execute(
        text("UPDATE charges SET status = :status WHERE id = :id"),
        {"status": ChargeStatus.PAID.value, "id": charge.id},
    )

    locked = repo.get_by_id_for_update(charge.id)

    assert locked is loaded
    assert locked.status == ChargeStatus.PAID
