"""Tests for Task client_record_id scoping: create, update, source resolution."""

from datetime import date

import pytest

from app.charges.models.charge import ChargeStatus, ChargeType
from app.core.exceptions import AppError, NotFoundError
from app.tasks.schemas.task import TaskCreateRequest, TaskUpdateRequest
from app.tasks.services.task_service import TaskService


def _create(db, **kwargs):
    req = TaskCreateRequest(title="Scoping task", **kwargs)
    return TaskService(db).create(req, created_by_user_id=None)


def _charge(charge_factory, biz):
    return charge_factory(
        client_record_id=biz.client_id,
        business_id=biz.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today(),
        commit=True,
    )


# ── Create: source → client resolution ───────────────────────────────────────


def test_create_with_source_populates_client_record_id(
    test_db, create_client_with_business, charge_factory
):
    _, biz = create_client_with_business(full_name="Task Test Client")
    charge = _charge(charge_factory, biz)
    task = _create(test_db, source_domain="charge", source_id=charge.id)
    assert task.client_record_id == biz.client_id  # type: ignore[attr-defined]


def test_create_without_source_client_record_id_is_none(test_db):
    task = _create(test_db)
    assert task.client_record_id is None


def test_create_direct_client_record_id_no_source(test_db, create_client_with_business):
    _, biz = create_client_with_business(full_name="Task Test Client")
    task = _create(test_db, client_record_id=biz.client_id)  # type: ignore[attr-defined]
    assert task.client_record_id == biz.client_id  # type: ignore[attr-defined]


def test_create_source_and_matching_client_record_id_succeeds(
    test_db, create_client_with_business, charge_factory
):
    _, biz = create_client_with_business(full_name="Task Test Client")
    charge = _charge(charge_factory, biz)
    task = _create(
        test_db, source_domain="charge", source_id=charge.id, client_record_id=biz.client_id
    )  # type: ignore[attr-defined]
    assert task.client_record_id == biz.client_id  # type: ignore[attr-defined]


def test_create_source_and_mismatching_client_record_id_raises(
    test_db, create_client_with_business, charge_factory
):
    _, biz1 = create_client_with_business(full_name="Task Test Client")
    _, biz2 = create_client_with_business(full_name="Task Test Client")
    charge = _charge(charge_factory, biz1)
    with pytest.raises(AppError) as exc_info:
        _create(
            test_db, source_domain="charge", source_id=charge.id, client_record_id=biz2.client_id
        )  # type: ignore[attr-defined]
    assert exc_info.value.code == "TASK.CLIENT_SOURCE_MISMATCH"


def test_create_nonexistent_direct_client_record_id_raises(test_db):
    with pytest.raises(NotFoundError) as exc_info:
        _create(test_db, client_record_id=999999)
    assert exc_info.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_create_soft_deleted_source_raises_not_found(
    test_db, create_client_with_business, charge_factory
):
    from app.utils.time_utils import utcnow

    _, biz = create_client_with_business(full_name="Task Test Client")
    charge = _charge(charge_factory, biz)
    charge.deleted_at = utcnow()
    test_db.flush()
    with pytest.raises(NotFoundError):
        _create(test_db, source_domain="charge", source_id=charge.id)


# ── Update: source change recomputes client_record_id ────────────────────────


def test_update_source_recomputes_client_record_id(
    test_db, create_client_with_business, charge_factory
):
    _, biz1 = create_client_with_business(full_name="Task Test Client")
    _, biz2 = create_client_with_business(full_name="Task Test Client")
    charge1 = _charge(charge_factory, biz1)
    charge2 = _charge(charge_factory, biz2)

    task = _create(test_db, source_domain="charge", source_id=charge1.id)
    assert task.client_record_id == biz1.client_id  # type: ignore[attr-defined]

    svc = TaskService(test_db)
    updated = svc.update(task.id, TaskUpdateRequest(source_domain="charge", source_id=charge2.id))  # type: ignore[call-arg]
    assert updated.client_record_id == biz2.client_id  # type: ignore[attr-defined]


def test_clear_source_preserves_client_record_id(
    test_db, create_client_with_business, charge_factory
):
    _, biz = create_client_with_business(full_name="Task Test Client")
    charge = _charge(charge_factory, biz)
    task = _create(test_db, source_domain="charge", source_id=charge.id)
    assert task.client_record_id == biz.client_id  # type: ignore[attr-defined]

    svc = TaskService(test_db)
    updated = svc.update(task.id, TaskUpdateRequest(source_domain=None, source_id=None))  # type: ignore[call-arg]
    assert updated.client_record_id == biz.client_id  # type: ignore[attr-defined]


def test_update_request_does_not_expose_client_record_id():
    """client_record_id is create-only; TaskUpdateRequest must not include it."""
    assert "client_record_id" not in TaskUpdateRequest.model_fields
