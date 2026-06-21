"""Regression: BaseRepository.get() soft-delete semantics after the Session.get rewrite.

get() must still hide soft-deleted rows by default and surface them with
include_deleted=True, while delegating the PK lookup to the identity-map-aware
Session.get().
"""

from __future__ import annotations

from decimal import Decimal

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.charges.repositories.charge_repository import ChargeRepository
from app.common.enums import IdNumberType, VatType
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_identity


def _charge(test_db, client_record_id: int) -> Charge:
    charge = Charge(
        client_record_id=client_record_id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("100.00"),
        issued_at=utcnow(),
    )
    test_db.add(charge)
    test_db.flush()
    return charge


def test_get_hides_soft_deleted_by_default(test_db):
    client = seed_client_identity(
        test_db,
        full_name="Base Repo Client",
        id_number="BRC-1",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    charge = _charge(test_db, client.id)
    repo = ChargeRepository(test_db)

    # Sanity: visible while not deleted.
    assert repo.get(charge.id) is not None

    repo.soft_delete(charge.id)

    assert repo.get(charge.id) is None
    assert repo.get_by_id(charge.id) is None


def test_get_returns_soft_deleted_with_include_deleted(test_db):
    client = seed_client_identity(
        test_db,
        full_name="Base Repo Client 2",
        id_number="BRC-2",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    charge = _charge(test_db, client.id)
    repo = ChargeRepository(test_db)
    repo.soft_delete(charge.id)

    fetched = repo.get(charge.id, include_deleted=True)
    assert fetched is not None
    assert fetched.id == charge.id
    assert fetched.deleted_at is not None
