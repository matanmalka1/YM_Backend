import pytest
from sqlalchemy import select

from app.authority_contacts.models.authority_contact import AuthorityContact, ContactType
from app.authority_contacts.repositories.authority_contact_repository import (
    AuthorityContactRepository,
)
from app.authority_contacts.services.authority_contact_service import (
    AuthorityContactService,
)
from app.core.exceptions import NotFoundError
from tests.helpers.identity import seed_client_identity


def _client(db, id_number: str = "888888888"):
    client = seed_client_identity(db, full_name="AC Service Client", id_number=id_number)
    db.commit()
    return client


def test_add_contact_missing_client_raises_not_found(test_db):
    service = AuthorityContactService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.add_contact(
            client_record_id=999,
            contact_type=ContactType.VAT_BRANCH,
            name="Missing Client",
        )
    assert exc_info.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_update_contact_missing_raises_not_found(test_db):
    client = _client(test_db)
    service = AuthorityContactService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.update_contact(client.id, 999, name="Nobody")

    assert exc_info.value.code == "AUTHORITY_CONTACT.NOT_FOUND"


def test_update_contact_wrong_client_raises_not_found(test_db):
    owner = _client(test_db, id_number="111000111")
    other = _client(test_db, id_number="222000222")
    repo = AuthorityContactRepository(test_db)
    contact = repo.create(
        client_record_id=owner.id, contact_type=ContactType.VAT_BRANCH, name="Real Contact"
    )
    service = AuthorityContactService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.update_contact(other.id, contact.id, name="Stolen")

    assert exc_info.value.code == "AUTHORITY_CONTACT.NOT_FOUND"


def test_delete_contact_missing_raises_not_found(test_db):
    client = _client(test_db)
    service = AuthorityContactService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.delete_contact(client.id, 999, actor_id=1)

    assert exc_info.value.code == "AUTHORITY_CONTACT.NOT_FOUND"


def test_delete_contact_wrong_client_raises_not_found(test_db):
    owner = _client(test_db, id_number="333000333")
    other = _client(test_db, id_number="444000444")
    repo = AuthorityContactRepository(test_db)
    contact = repo.create(
        client_record_id=owner.id, contact_type=ContactType.VAT_BRANCH, name="Real Contact"
    )
    service = AuthorityContactService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.delete_contact(other.id, contact.id, actor_id=1)

    assert exc_info.value.code == "AUTHORITY_CONTACT.NOT_FOUND"

    # Original contact untouched
    assert repo.get_by_id(contact.id) is not None


def test_get_contact_missing_raises_not_found(test_db):
    client = _client(test_db)
    service = AuthorityContactService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.get_contact(client.id, 999)

    assert exc_info.value.code == "AUTHORITY_CONTACT.NOT_FOUND"


def test_get_contact_wrong_client_raises_not_found(test_db):
    owner = _client(test_db, id_number="555000555")
    other = _client(test_db, id_number="666000666")
    repo = AuthorityContactRepository(test_db)
    contact = repo.create(
        client_record_id=owner.id, contact_type=ContactType.VAT_BRANCH, name="Real Contact"
    )
    service = AuthorityContactService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.get_contact(other.id, contact.id)

    assert exc_info.value.code == "AUTHORITY_CONTACT.NOT_FOUND"


def test_list_contacts_filters_and_paginates(test_db):
    client = _client(test_db)
    repo = AuthorityContactRepository(test_db)
    repo.create(client_record_id=client.id, contact_type=ContactType.VAT_BRANCH, name="VAT 1")
    repo.create(
        client_record_id=client.id,
        contact_type=ContactType.ASSESSING_OFFICER,
        name="AO 1",
    )
    repo.create(client_record_id=client.id, contact_type=ContactType.VAT_BRANCH, name="VAT 2")

    service = AuthorityContactService(test_db)
    items, total = service.list_client_contacts(
        client.id, ContactType.VAT_BRANCH, page=1, page_size=1
    )

    assert total == 2
    assert len(items) == 1
    assert items[0].contact_type == ContactType.VAT_BRANCH


def test_repository_soft_delete_marks_deleted_metadata(test_db):
    client = _client(test_db)
    repo = AuthorityContactRepository(test_db)
    contact = repo.create(
        client_record_id=client.id,
        contact_type=ContactType.VAT_BRANCH,
        name="To Delete",
    )

    deleted = repo.delete_for_client(client.id, contact.id, deleted_by=42)

    assert deleted is True
    assert repo.get_by_id(contact.id) is None

    persisted = test_db.scalars(
        select(AuthorityContact).filter(AuthorityContact.id == contact.id)
    ).first()
    assert persisted.deleted_by == 42
    assert persisted.deleted_at is not None
