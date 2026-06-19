import pytest
from sqlalchemy.exc import IntegrityError

from app.binders.repositories.binder_repository import BinderRepository
from app.clients.models.client_record import ClientRecord
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.services.client_lifecycle_service import ClientLifecycleService
from app.clients.services.client_query_service import ClientQueryService
from app.clients.services.client_service import get_client_or_raise
from app.clients.services.client_update_service import ClientUpdateService
from app.clients.services.client_create_service import (
    CreateClientService,
    create_client_identity_only,
)
from app.common.enums import EntityType, IdNumberType
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.utils.time_utils import utcnow
from app.vat.repositories.vat_client_summary_repository import VatClientSummaryRepository
from tests.helpers.identity import seed_client_identity


def _create_client(db, *, full_name: str, id_number: str, deleted: bool = False):
    client = seed_client_identity(
        db,
        full_name=full_name,
        id_number=id_number,
        id_number_type=IdNumberType.CORPORATION,
        created_by=1,
        deleted_at=utcnow() if deleted else None,
    )
    db.flush()
    return client


def _svc_create(service, *, full_name, id_number, actor_id=3):
    """Helper: create via service, return ClientRecord."""
    return create_client_identity_only(
        service.db,
        full_name=full_name,
        id_number=id_number,
        id_number_type=IdNumberType.CORPORATION,
        entity_type=EntityType.COMPANY_LTD,
        actor_id=actor_id,
    )


def test_create_client_success(test_db):
    service = CreateClientService(test_db)

    cr = _svc_create(service, full_name="Service Client", id_number="610000002")

    assert cr.id is not None
    assert cr.office_client_number == 100001
    assert cr.created_by == 3


def test_create_client_assigns_next_office_client_number_and_creates_initial_binder(
    test_db,
):
    service = CreateClientService(test_db)

    first = _svc_create(service, full_name="First Client", id_number="610000010")
    created = _svc_create(service, full_name="Binder Client", id_number="610000028")

    assert first.office_client_number == 100001
    assert created.office_client_number == 100002

    binder = BinderRepository(test_db).get_active_by_client_record(created.id)
    assert binder is not None
    assert binder.binder_number == "100002/1"


def test_create_client_conflict_when_active_exists(test_db):
    _create_client(test_db, full_name="Existing", id_number="620000000")
    service = CreateClientService(test_db)

    with pytest.raises(AppError) as exc:
        service.create_client(
            full_name="Duplicate",
            id_number="620000000",
            id_number_type=IdNumberType.CORPORATION,
            actor_id=1,
        )

    assert exc.value.code == "CLIENT.CONFLICT"
    assert exc.value.details is not None
    assert "conflict" in exc.value.details


def test_create_client_deleted_exists_conflict(test_db):
    _create_client(test_db, full_name="Deleted", id_number="630000008", deleted=True)

    service = CreateClientService(test_db)
    with pytest.raises(AppError) as exc:
        service.create_client(
            full_name="New",
            id_number="630000008",
            id_number_type=IdNumberType.CORPORATION,
            actor_id=1,
        )

    assert exc.value.code == "CLIENT.DELETED_EXISTS"
    assert exc.value.details is not None
    assert "conflict" in exc.value.details


def test_create_client_rejects_employee_entity_type(test_db):
    service = CreateClientService(test_db)

    with pytest.raises(ValueError, match="שכיר"):
        service.create_client(
            full_name="Employee",
            id_number="087654321",
            id_number_type=IdNumberType.INDIVIDUAL,
            entity_type=EntityType.EMPLOYEE,
            actor_id=1,
        )


def test_create_client_rejects_company_with_non_corporation_id_type(test_db):
    service = CreateClientService(test_db)

    with pytest.raises(ValueError, match="חייבת להיווצר עם ח.פ"):
        service.create_client(
            full_name="Bad Company",
            id_number="039337423",
            id_number_type=IdNumberType.INDIVIDUAL,
            entity_type=EntityType.COMPANY_LTD,
            actor_id=1,
        )


def test_get_client_or_raise_not_found(test_db):
    with pytest.raises(NotFoundError) as exc:
        get_client_or_raise(test_db, 999)

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_update_delete_restore_flow(test_db):
    creation_service = CreateClientService(test_db)
    created = _svc_create(
        creation_service, full_name="Before Update", id_number="640000006", actor_id=10
    )

    updated = ClientUpdateService(test_db).update_client(
        created.id,
        actor_id=10,
        full_name="After Update",
        phone="0501234567",
    )
    assert updated["full_name"] == "After Update"
    assert updated["phone"] == "0501234567"

    lifecycle_service = ClientLifecycleService(test_db)
    lifecycle_service.delete_client(created.id, actor_id=11)
    with pytest.raises(NotFoundError):
        get_client_or_raise(test_db, created.id)

    restored = lifecycle_service.restore_client(created.id, actor_id=12)
    restored_record = ClientRecordRepository(test_db).get_by_id(created.id)
    assert restored_record is not None
    assert restored_record.deleted_at is None
    assert restored_record.restored_by == 12
    assert restored["id"] == created.id


def test_update_advance_rate_change_stamps_server_owned_timestamp(test_db):
    from decimal import Decimal

    from app.utils.time_utils import israel_today

    created = _svc_create(
        CreateClientService(test_db), full_name="Advance Rate", id_number="640000099", actor_id=10
    )
    service = ClientUpdateService(test_db)

    updated = service.update_client(created.id, actor_id=10, advance_rate=Decimal("12.50"))
    assert updated["advance_rate"] == Decimal("12.50")
    assert updated["advance_rate_updated_at"] == israel_today()


def test_update_advance_rate_unchanged_does_not_restamp_timestamp(test_db):
    from decimal import Decimal

    created = _svc_create(
        CreateClientService(test_db), full_name="Advance Same", id_number="640000098", actor_id=10
    )
    service = ClientUpdateService(test_db)
    first = service.update_client(created.id, actor_id=10, advance_rate=Decimal("9.00"))
    sentinel_date = first["advance_rate_updated_at"]
    assert sentinel_date is not None

    # Re-send the same advance_rate together with another change; the timestamp
    # must not move because advance_rate did not actually change.
    again = service.update_client(
        created.id, actor_id=10, advance_rate=Decimal("9.00"), phone="0500000000"
    )
    assert again["advance_rate_updated_at"] == sentinel_date


def test_create_client_always_creates_initial_binder(test_db):
    service = CreateClientService(test_db)
    created = _svc_create(
        service, full_name="Auto Binder Client", id_number="640000022", actor_id=10
    )

    assert BinderRepository(test_db).count_by_client(created.id) == 1
    binder = BinderRepository(test_db).get_active_by_client_record(created.id)
    assert binder is not None
    assert binder.binder_number == f"{created.office_client_number}/1"


def test_delete_raises_not_found_when_client_already_deleted(test_db):
    created = _svc_create(
        CreateClientService(test_db),
        full_name="Delete Twice",
        id_number="640000014",
    )
    service = ClientLifecycleService(test_db)
    service.delete_client(created.id, actor_id=1)

    with pytest.raises(NotFoundError) as exc:
        service.delete_client(created.id, actor_id=2)

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_restore_raises_when_not_deleted(test_db):
    client = _create_client(test_db, full_name="Alive", id_number="650000003")
    service = ClientLifecycleService(test_db)

    with pytest.raises(ConflictError) as exc:
        service.restore_client(client.id, actor_id=1)

    assert exc.value.code == "CLIENT.NOT_DELETED"


def test_restore_raises_when_active_duplicate_exists(test_db):
    deleted = _create_client(test_db, full_name="Old", id_number="660000001", deleted=True)
    active = ClientRecord(legal_entity_id=deleted.legal_entity_id, created_by=1)
    test_db.add(active)
    test_db.commit()

    service = ClientLifecycleService(test_db)
    with pytest.raises(ConflictError) as exc:
        service.restore_client(deleted.id, actor_id=2)

    assert exc.value.code == "CLIENT.CONFLICT"


def test_list_clients_and_conflict_info(test_db):
    creation_service = CreateClientService(test_db)
    one = _svc_create(creation_service, full_name="Alpha", id_number="670000009")
    two = _svc_create(creation_service, full_name="Beta", id_number="670000017")
    ClientLifecycleService(test_db).delete_client(two.id, actor_id=1)

    query_service = ClientQueryService(test_db)
    result = query_service.list_full_clients(search="Alpha", page=1, page_size=10)
    assert result.total == 1
    assert [c.id for c in result.items] == [one.id]

    info_active = query_service.get_conflict_info("670000009")
    assert len(info_active.active_clients) == 1
    assert len(info_active.deleted_clients) == 0

    info_deleted = query_service.get_conflict_info("670000017")
    assert len(info_deleted.active_clients) == 0
    assert len(info_deleted.deleted_clients) == 1


def test_list_clients_uses_thin_dto_without_turnover_lookup(test_db, monkeypatch):
    """The clients list returns the thin ClientRecordListItem.

    The thin row does not expose annual turnover, so the list must not perform
    the per-page turnover lookup (that data is detail-only, on GET /clients/{id}).
    """
    creation_service = CreateClientService(test_db)
    reported = _svc_create(
        creation_service,
        full_name="Reported Turnover",
        id_number="670000041",
    )
    manual = _svc_create(
        creation_service,
        full_name="Manual Turnover",
        id_number="670000050",
    )

    def fail_batch(self, client_record_ids, year):
        raise AssertionError("clients list must not load annual turnover")

    def fail_scalar(self, client_record_id, year):
        raise AssertionError("clients list must not load annual turnover")

    monkeypatch.setattr(
        VatClientSummaryRepository,
        "get_annual_turnover_by_client_ids",
        fail_batch,
    )
    monkeypatch.setattr(VatClientSummaryRepository, "get_annual_turnover", fail_scalar)

    result = ClientQueryService(test_db).list_full_clients(page=1, page_size=10)
    by_id = {item.id: item for item in result.items}

    assert {reported.id, manual.id} <= set(by_id)
    # Thin DTO carries no turnover field at all.
    assert not hasattr(by_id[reported.id], "annual_turnover")


def test_create_client_does_not_reuse_deleted_office_client_number(test_db):
    service = CreateClientService(test_db)
    first = _svc_create(service, full_name="First", id_number="670000025")
    ClientLifecycleService(test_db).delete_client(first.id, actor_id=1)

    second = _svc_create(service, full_name="Second", id_number="670000033")

    assert first.office_client_number == 100001
    assert second.office_client_number == 100002


def test_create_client_converts_integrity_error_to_conflict(test_db, monkeypatch):
    service = CreateClientService(test_db)

    def _raise_integrity(*_args, **_kwargs):
        raise IntegrityError("insert", {}, Exception("ix_clients_id_number duplicate"))

    monkeypatch.setattr(service.record_repo, "create", _raise_integrity)

    with pytest.raises(AppError) as exc:
        service.create_client(
            full_name="Integrity",
            id_number="690000005",
            id_number_type=IdNumberType.CORPORATION,
            actor_id=1,
        )

    assert exc.value.code == "CLIENT.CONFLICT"
    assert exc.value.details is not None
    assert "conflict" in exc.value.details


def test_restore_raises_not_found_when_client_missing(test_db):
    service = ClientLifecycleService(test_db)

    with pytest.raises(NotFoundError) as exc:
        service.restore_client(9999, actor_id=1)

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_restore_raises_not_found_when_repo_restore_returns_none(test_db, monkeypatch):
    created = _svc_create(
        CreateClientService(test_db),
        full_name="To Restore",
        id_number="690000013",
    )
    service = ClientLifecycleService(test_db)
    service.delete_client(created.id, actor_id=1)

    monkeypatch.setattr(service.record_repo, "restore", lambda *_args, **_kwargs: None)

    with pytest.raises(NotFoundError) as exc:
        service.restore_client(created.id, actor_id=2)

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"
