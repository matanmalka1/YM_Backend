"""The SQL half of VAT's resolved-status twin.

``RESOLVED_VAT_WORK_ITEM_STATUSES`` is read by both ``is_vat_work_item_resolved``
and every SQL query asking the same question. tests/common/test_resolved_status_twins.py
pins the Python half; this pins the SQL half against a real database, because the
regression it guards was precisely a disagreement between the two — the Python set
omitted CANCELED while this repository excluded it, so a cancelled period read open
on the grouped tax calendar and closed here.
"""

from datetime import date

import pytest

from app.common.enums import VatType
from app.utils.time_utils import utcnow
from app.vat.models.vat_enums import (
    RESOLVED_VAT_WORK_ITEM_STATUSES,
    VatWorkItemStatus,
    is_vat_work_item_resolved,
)
from app.vat.repositories.vat_compliance_repository import VatComplianceRepository
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.helpers.tax_calendar_links import create_linked_vat_work_item

REFERENCE_DATE = date(2026, 6, 1)


def _item(repo, client_id: int, user_id: int, period: str, status):
    return create_linked_vat_work_item(
        repo.db,
        repo=repo,
        client_record_id=client_id,
        period=period,
        period_type=VatType.MONTHLY,
        created_by=user_id,
        status=status,
    )


@pytest.mark.parametrize("status", sorted(RESOLVED_VAT_WORK_ITEM_STATUSES, key=lambda s: s.value))
def test_resolved_statuses_are_excluded_from_overdue(test_db, user_factory, client_factory, status):
    """Every status the Python predicate calls resolved is excluded by the SQL side.

    Driven off the published set rather than a literal list, so a status added to
    it cannot pass here while the query still returns the row.
    """
    assert is_vat_work_item_resolved(status)

    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    client = client_factory(full_name="Resolved Client", id_number="VCR001")
    _item(repo, client.id, user.id, "2026-01", status)
    test_db.flush()

    overdue = VatComplianceRepository(test_db).get_overdue_unfiled(REFERENCE_DATE)

    assert overdue == []


def test_cancelled_period_is_not_overdue(test_db, user_factory, client_factory):
    """The regression, stated directly.

    A cancelled period past its due date is not outstanding work, and must not
    appear on the compliance list.
    """
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    client = client_factory(full_name="Cancel Client", id_number="VCR002")
    _item(repo, client.id, user.id, "2026-01", VatWorkItemStatus.CANCELED)
    open_item = _item(repo, client.id, user.id, "2026-02", VatWorkItemStatus.PENDING_MATERIALS)
    test_db.flush()

    overdue = VatComplianceRepository(test_db).get_overdue_unfiled(REFERENCE_DATE)

    assert [item.id for item in overdue] == [open_item.id]


@pytest.mark.parametrize(
    "status",
    [
        VatWorkItemStatus.PENDING_MATERIALS,
        VatWorkItemStatus.MATERIAL_RECEIVED,
        VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,
        VatWorkItemStatus.READY_FOR_REVIEW,
    ],
)
def test_unresolved_statuses_are_returned(test_db, user_factory, client_factory, status):
    assert not is_vat_work_item_resolved(status)

    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    client = client_factory(full_name="Open Client", id_number="VCR003")
    item = _item(repo, client.id, user.id, "2026-01", status)
    test_db.flush()

    overdue = VatComplianceRepository(test_db).get_overdue_unfiled(REFERENCE_DATE)

    assert [row.id for row in overdue] == [item.id]


def test_soft_deleted_period_is_excluded(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    client = client_factory(full_name="Deleted Client", id_number="VCR004")
    item = _item(repo, client.id, user.id, "2026-01", VatWorkItemStatus.PENDING_MATERIALS)
    item.deleted_at = utcnow()
    test_db.flush()

    assert VatComplianceRepository(test_db).get_overdue_unfiled(REFERENCE_DATE) == []
