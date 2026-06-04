from app.authority_contact.models.authority_contact import ContactType
from app.authority_contact.repositories.authority_contact_repository import (
    AuthorityContactRepository,
)
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from tests.helpers.identity import seed_client_identity


def test_authority_contact_repository_crud_flow(test_db):
    repo = AuthorityContactRepository(test_db)

    user = User(
        full_name="Advisor",
        email="advisor@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    client = seed_client_identity(
        test_db,
        full_name="Client A",
        id_number="AC001",
    )
    test_db.add(user)
    test_db.commit()

    contact_a = repo.create(
        client_record_id=client.id,
        contact_type=ContactType.ASSESSING_OFFICER,
        name="Officer One",
        phone="111",
    )
    contact_b = repo.create(
        client_record_id=client.id,
        contact_type=ContactType.VAT_BRANCH,
        name="Officer Two",
        phone="222",
    )

    contacts = repo.list_by_client_record(client_record_id=client.id, page=1, page_size=10)
    assert [c.id for c in contacts] == [contact_b.id, contact_a.id]
    assert repo.count_by_client_record(client_record_id=client.id) == 2
    assert (
        repo.count_by_client_record(client_record_id=client.id, contact_type=ContactType.VAT_BRANCH)
        == 1
    )

    updated = repo.update_for_client(client.id, contact_a.id, phone="999")
    assert updated is not None
    assert updated.phone == "999"
    assert updated.updated_at is not None

    deleted = repo.delete_for_client(client.id, contact_a.id, deleted_by=user.id)
    assert deleted is True
    assert contact_a.deleted_at is not None
    assert contact_a.deleted_by == user.id
    assert repo.get_by_id(contact_a.id) is None
    assert repo.count_by_client_record(client_record_id=client.id) == 1
