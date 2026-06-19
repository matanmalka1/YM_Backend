from datetime import date, datetime, timedelta
from itertools import count

from app.businesses.models.business import Business
from app.communications.models.correspondence import CorrespondenceType
from app.communications.repositories.correspondence_repository import (
    CorrespondenceRepository,
)
from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService
from tests.helpers.identity import seed_client_with_business

_client_seq = count(1)


def _business(db) -> Business:
    idx = next(_client_seq)
    _, b = seed_client_with_business(
        db,
        full_name=f"Correspondence Repo Client {idx}",
        id_number=f"{idx:09d}",
        business_name=f"Correspondence Repo Business {idx}",
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(b)
    return b


def _user(test_db) -> User:
    user = User(
        full_name="Correspondence Repo User",
        email="correspondence.repo@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def test_list_by_client_paginated_and_soft_delete(test_db):
    repo = CorrespondenceRepository(test_db)
    user = _user(test_db)
    business_a = _business(test_db)
    business_b = _business(test_db)
    base = datetime(2026, 1, 1, 12, 0, 0)

    first = repo.create(
        client_record_id=business_a.client_id,
        business_id=business_a.id,
        correspondence_type=CorrespondenceType.EMAIL,
        subject="First",
        occurred_at=base + timedelta(days=1),
        created_by=user.id,
    )
    second = repo.create(
        client_record_id=business_a.client_id,
        business_id=business_a.id,
        correspondence_type=CorrespondenceType.CALL,
        subject="Second",
        occurred_at=base + timedelta(days=2),
        created_by=user.id,
    )
    third = repo.create(
        client_record_id=business_a.client_id,
        business_id=business_a.id,
        correspondence_type=CorrespondenceType.MEETING,
        subject="Third",
        occurred_at=base + timedelta(days=3),
        created_by=user.id,
    )
    repo.create(
        client_record_id=business_b.client_id,
        business_id=business_b.id,
        correspondence_type=CorrespondenceType.LETTER,
        subject="Other client",
        occurred_at=base + timedelta(days=4),
        created_by=user.id,
    )

    page_1_items, page_1_total = repo.list_by_client_paginated(
        business_a.client_id, page=1, page_size=2
    )
    assert page_1_total == 3
    assert [entry.id for entry in page_1_items] == [third.id, second.id]

    page_2_items, page_2_total = repo.list_by_client_paginated(
        business_a.client_id, page=2, page_size=2
    )
    assert page_2_total == 3
    assert [entry.id for entry in page_2_items] == [first.id]

    assert repo.soft_delete(second.id, deleted_by=user.id) is True
    assert repo.get_by_id(second.id) is None

    remaining, total_after_delete = repo.list_by_client_paginated(
        business_a.client_id, page=1, page_size=10
    )
    assert total_after_delete == 2
    assert {entry.id for entry in remaining} == {first.id, third.id}
    assert repo.soft_delete(999999, deleted_by=user.id) is False


def test_list_by_client_filters_business_and_sort(test_db):
    repo = CorrespondenceRepository(test_db)
    user = _user(test_db)
    business = _business(test_db)
    base = datetime(2026, 1, 1, 8, 0, 0)

    e1 = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        correspondence_type=CorrespondenceType.EMAIL,
        subject="Email 1",
        occurred_at=base,
        created_by=user.id,
        contact_id=10,
    )
    e2 = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        correspondence_type=CorrespondenceType.CALL,
        subject="Call",
        occurred_at=base + timedelta(days=1),
        created_by=user.id,
        contact_id=20,
    )
    e3 = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        correspondence_type=CorrespondenceType.EMAIL,
        subject="Email 2",
        occurred_at=base + timedelta(days=2),
        created_by=user.id,
        contact_id=10,
    )

    items, total = repo.list_by_client_paginated(
        business.client_id,
        page=1,
        page_size=10,
        business_id=business.id,
        correspondence_type=CorrespondenceType.EMAIL,
        contact_id=10,
        occurred_after=base + timedelta(hours=1),
        occurred_before=base + timedelta(days=2),
        order="asc",
    )

    assert total == 1
    assert [i.id for i in items] == [e3.id]
    assert e1.id != e2.id
