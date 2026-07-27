from datetime import date, datetime, timedelta

from app.communications.models.correspondence import CorrespondenceType
from app.communications.repositories.correspondence_repository import (
    CorrespondenceRepository,
)
from app.authority_contacts.models.authority_contact import ContactType


def _business(create_client_with_business, idx: int):
    _, business = create_client_with_business(
        full_name=f"Correspondence Repo Client {idx}",
        id_number=f"{idx:09d}",
        business_name=f"Correspondence Repo Business {idx}",
        opened_at=date.today(),
    )
    return business


def _user(user_factory):
    return user_factory(
        full_name="Correspondence Repo User",
        email="correspondence.repo@example.com",
        commit=True,
    )


def test_list_by_client_paginated_and_soft_delete(
    test_db, user_factory, create_client_with_business
):
    repo = CorrespondenceRepository(test_db)
    user = _user(user_factory)
    business_a = _business(create_client_with_business, 1)
    business_b = _business(create_client_with_business, 2)
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


def test_list_by_client_filters_business_and_sort(
    test_db, user_factory, create_client_with_business, authority_contact_factory
):
    repo = CorrespondenceRepository(test_db)
    user = _user(user_factory)
    business = _business(create_client_with_business, 3)
    primary_contact = authority_contact_factory(
        client_record_id=business.client_id,
        contact_type=ContactType.VAT_BRANCH,
        name="Primary Contact",
    )
    secondary_contact = authority_contact_factory(
        client_record_id=business.client_id,
        contact_type=ContactType.ASSESSING_OFFICER,
        name="Secondary Contact",
    )
    base = datetime(2026, 1, 1, 8, 0, 0)

    e1 = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        correspondence_type=CorrespondenceType.EMAIL,
        subject="Email 1",
        occurred_at=base,
        created_by=user.id,
        contact_id=primary_contact.id,
    )
    e2 = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        correspondence_type=CorrespondenceType.CALL,
        subject="Call",
        occurred_at=base + timedelta(days=1),
        created_by=user.id,
        contact_id=secondary_contact.id,
    )
    e3 = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        correspondence_type=CorrespondenceType.EMAIL,
        subject="Email 2",
        occurred_at=base + timedelta(days=2),
        created_by=user.id,
        contact_id=primary_contact.id,
    )

    items, total = repo.list_by_client_paginated(
        business.client_id,
        page=1,
        page_size=10,
        business_id=business.id,
        correspondence_type=CorrespondenceType.EMAIL,
        contact_id=primary_contact.id,
        occurred_after=base + timedelta(hours=1),
        occurred_before=base + timedelta(days=2),
        order="asc",
    )

    assert total == 1
    assert [i.id for i in items] == [e3.id]
    assert e1.id != e2.id
