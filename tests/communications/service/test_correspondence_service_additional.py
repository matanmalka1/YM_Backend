from datetime import date, datetime

import pytest

from app.authority_contacts.models.authority_contact import AuthorityContact, ContactType
from app.businesses.models.business import Business
from app.core.exceptions import ForbiddenError, NotFoundError
from app.communications.models.correspondence import CorrespondenceType
from app.communications.services.correspondence_service import CorrespondenceService
from tests.helpers.identity import seed_client_with_business


def _business(db, id_number: str) -> Business:
    _, business = seed_client_with_business(
        db,
        full_name=f"Correspondence Service {id_number}",
        id_number=id_number,
        business_name=f"Business {id_number}",
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(business)
    return business


def _contact(db, client_id: int, name: str) -> AuthorityContact:
    contact = AuthorityContact(
        client_record_id=client_id,
        contact_type=ContactType.ASSESSING_OFFICER,
        name=name,
        phone="0501111111",
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def test_update_entry_forbidden_when_contact_belongs_to_other_client(test_db, test_user):
    b1 = _business(test_db, "700000001")
    b2 = _business(test_db, "700000002")
    foreign_contact = _contact(test_db, b2.client_id, "Foreign Contact")

    service = CorrespondenceService(test_db)
    entry = service.add_entry(
        client_record_id=b1.client_id,
        business_id=b1.id,
        correspondence_type=CorrespondenceType.EMAIL,
        subject="Original",
        occurred_at=datetime(2026, 1, 1, 9, 0, 0),
        created_by=test_user.id,
    )

    with pytest.raises(ForbiddenError) as exc_info:
        service.update_entry(entry.id, b1.client_id, contact_id=foreign_contact.id)

    assert exc_info.value.code == "CORRESPONDENCE.FORBIDDEN_CONTACT"


def test_update_entry_raises_not_found_when_repo_update_returns_none(
    test_db, test_user, monkeypatch
):
    b1 = _business(test_db, "700000003")
    service = CorrespondenceService(test_db)
    entry = service.add_entry(
        client_record_id=b1.client_id,
        business_id=b1.id,
        correspondence_type=CorrespondenceType.CALL,
        subject="Will vanish",
        occurred_at=datetime(2026, 1, 2, 9, 0, 0),
        created_by=test_user.id,
    )

    monkeypatch.setattr(service.repo, "update", lambda *_args, **_kwargs: None)

    with pytest.raises(NotFoundError) as exc_info:
        service.update_entry(entry.id, b1.client_id, subject="x")

    assert exc_info.value.code == "CORRESPONDENCE.NOT_FOUND"


def test_delete_entry_raises_not_found_when_client_mismatch(test_db, test_user):
    b1 = _business(test_db, "700000004")
    b2 = _business(test_db, "700000005")
    service = CorrespondenceService(test_db)
    entry = service.add_entry(
        client_record_id=b1.client_id,
        business_id=b1.id,
        correspondence_type=CorrespondenceType.MEETING,
        subject="Delete mismatch",
        occurred_at=datetime(2026, 1, 3, 9, 0, 0),
        created_by=test_user.id,
    )

    with pytest.raises(NotFoundError) as exc_info:
        service.delete_entry(entry.id, b2.client_id, actor_id=test_user.id)

    assert exc_info.value.code == "CORRESPONDENCE.NOT_FOUND"


def test_add_entry_raises_not_found_for_missing_client(test_db, test_user):
    service = CorrespondenceService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.add_entry(
            client_record_id=999999,
            correspondence_type=CorrespondenceType.EMAIL,
            subject="Missing client",
            occurred_at=datetime(2026, 1, 4, 9, 0, 0),
            created_by=test_user.id,
        )

    assert exc_info.value.code == "CLIENT.NOT_FOUND"


def test_add_entry_rejected_for_business_client_mismatch(test_db, test_user):
    b1 = _business(test_db, "700000006")
    b2 = _business(test_db, "700000007")
    service = CorrespondenceService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.add_entry(
            client_record_id=b1.client_id,
            business_id=b2.id,
            correspondence_type=CorrespondenceType.EMAIL,
            subject="No create",
            occurred_at=datetime(2026, 1, 5, 9, 0, 0),
            created_by=test_user.id,
        )

    assert exc_info.value.code == "BUSINESS.NOT_FOUND"


def test_get_entry_not_found_for_mismatch_client(test_db, test_user):
    b1 = _business(test_db, "700000008")
    b2 = _business(test_db, "700000009")
    service = CorrespondenceService(test_db)

    entry = service.add_entry(
        client_record_id=b1.client_id,
        business_id=b1.id,
        correspondence_type=CorrespondenceType.LETTER,
        subject="Owned by b1",
        occurred_at=datetime(2026, 1, 6, 9, 0, 0),
        created_by=test_user.id,
    )

    with pytest.raises(NotFoundError) as exc_info:
        service.get_entry(entry.id, b2.client_id)

    assert exc_info.value.code == "CORRESPONDENCE.NOT_FOUND"
