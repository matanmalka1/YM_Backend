import pytest

from app.core.exceptions import NotFoundError
from app.notes.services.note_entity_note_service import EntityNoteService


def test_list_notes_includes_creator_name(test_db, test_user, client_factory):
    client = client_factory(full_name="Notes Client", id_number="NOTE-001")
    service = EntityNoteService(test_db)
    created = service.add_note(
        entity_type="client",
        entity_id=client.id,
        note="בדיקה",
        created_by=test_user.id,
    )
    test_db.commit()

    items, total = service.list_notes(entity_type="client", entity_id=client.id)

    assert total == 1
    assert items[0].id == created.id
    assert items[0].created_by == test_user.id
    assert items[0].created_by_name == test_user.full_name


def test_update_note_keeps_creator_name(test_db, test_user, client_factory):
    client = client_factory(full_name="Notes Client", id_number="NOTE-002")
    service = EntityNoteService(test_db)
    created = service.add_note(
        entity_type="client",
        entity_id=client.id,
        note="לפני",
        created_by=test_user.id,
    )
    test_db.commit()

    updated = service.update_note(
        note_id=created.id,
        entity_type="client",
        entity_id=client.id,
        note="אחרי",
        actor_id=test_user.id,
    )

    assert updated.note == "אחרי"
    assert updated.created_by_name == test_user.full_name


def test_missing_creator_does_not_fallback_to_another_user(test_db, test_user, client_factory):
    client = client_factory(full_name="Notes Client", id_number="NOTE-003")
    service = EntityNoteService(test_db)
    service.add_note(
        entity_type="client",
        entity_id=client.id,
        note="יוצר חסר",
        created_by=test_user.id + 999,
    )
    test_db.commit()

    items, total = service.list_notes(entity_type="client", entity_id=client.id)

    assert total == 1
    assert items[0].created_by_name is None


def test_list_client_notes_requires_existing_client(test_db):
    service = EntityNoteService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.list_notes(entity_type="client", entity_id=999999)

    assert exc_info.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_add_client_note_requires_existing_client(test_db):
    service = EntityNoteService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.add_note(
            entity_type="client",
            entity_id=999999,
            note="לקוח חסר",
        )

    assert exc_info.value.code == "CLIENT_RECORD.NOT_FOUND"
