from itertools import count

import pytest

from app.businesses.models.business import BusinessStatus
from app.businesses.repositories.business_repository import BusinessRepository
from app.common.enums import IdNumberType
from app.legal_entities.models.legal_entity import LegalEntity
from app.utils.time_utils import utcnow

_entity_seq = count(1)


@pytest.fixture()
def repo(test_db):
    return BusinessRepository(test_db)


def _legal_entity(db):
    seq = next(_entity_seq)
    entity = LegalEntity(
        id_number=f"LE-{seq}",
        id_number_type=IdNumberType.INDIVIDUAL,
        official_name=f"Test Entity {seq}",
    )
    db.add(entity)
    db.flush()
    return entity


def _business(business_factory, legal_entity_id, *, status=BusinessStatus.ACTIVE, deleted=False):
    return business_factory(
        legal_entity_id=legal_entity_id,
        status=status,
        deleted_at=utcnow() if deleted else None,
    )


def test_exists_for_legal_entity_ignores_deleted_and_handles_empty(test_db, repo, business_factory):
    active_entity = _legal_entity(test_db)
    deleted_entity = _legal_entity(test_db)
    empty_entity = _legal_entity(test_db)
    _business(business_factory, active_entity.id)
    _business(business_factory, deleted_entity.id, deleted=True)

    assert repo.exists_for_legal_entity(active_entity.id) is True
    assert repo.exists_for_legal_entity(deleted_entity.id) is False
    assert repo.exists_for_legal_entity(empty_entity.id) is False


def test_all_non_deleted_are_closed_requires_nonempty_closed_set(test_db, repo, business_factory):
    closed_entity = _legal_entity(test_db)
    active_entity = _legal_entity(test_db)
    empty_entity = _legal_entity(test_db)
    _business(business_factory, closed_entity.id, status=BusinessStatus.CLOSED)
    _business(business_factory, active_entity.id, status=BusinessStatus.ACTIVE)

    assert repo.all_non_deleted_are_closed_for_legal_entity(closed_entity.id) is True
    assert repo.all_non_deleted_are_closed_for_legal_entity(active_entity.id) is False
    assert repo.all_non_deleted_are_closed_for_legal_entity(empty_entity.id) is False


def test_active_list_ids_and_count_share_soft_delete_scope(test_db, repo, business_factory):
    entity = _legal_entity(test_db)
    first = _business(business_factory, entity.id)
    second = _business(business_factory, entity.id)
    _business(business_factory, entity.id, deleted=True)

    assert {item.id for item in repo.list_by_legal_entity(entity.id)} == {first.id, second.id}
    assert set(repo.get_ids_by_legal_entity(entity.id)) == {first.id, second.id}
    assert repo.count_by_legal_entity(entity.id) == 2


def test_list_by_legal_entity_including_deleted(test_db, repo, business_factory):
    entity = _legal_entity(test_db)
    active = _business(business_factory, entity.id)
    deleted = _business(business_factory, entity.id, deleted=True)

    assert {item.id for item in repo.list_by_legal_entity_including_deleted(entity.id)} == {
        active.id,
        deleted.id,
    }


def test_list_by_legal_entity_ids_matches_multiple_entities_and_empty_input(
    test_db, repo, business_factory
):
    first_entity = _legal_entity(test_db)
    second_entity = _legal_entity(test_db)
    first = _business(business_factory, first_entity.id)
    second = _business(business_factory, second_entity.id)
    _business(business_factory, first_entity.id, deleted=True)

    assert {
        item.id for item in repo.list_by_legal_entity_ids([first_entity.id, second_entity.id])
    } == {
        first.id,
        second.id,
    }
    assert repo.list_by_legal_entity_ids([]) == []


def test_list_by_legal_entity_empty_returns_empty_and_zero_count(test_db, repo):
    entity = _legal_entity(test_db)

    assert repo.list_by_legal_entity(entity.id) == []
    assert repo.count_by_legal_entity(entity.id) == 0


def test_list_by_legal_entity_deterministic_tie_breaker(test_db, repo, business_factory):
    entity = _legal_entity(test_db)
    # All share opened_at=date(2024, 1, 1); id asc tie-breaker fixes the order.
    first = _business(business_factory, entity.id)
    second = _business(business_factory, entity.id)
    third = _business(business_factory, entity.id)

    items = repo.list_by_legal_entity(entity.id)

    assert [b.id for b in items] == [first.id, second.id, third.id]
