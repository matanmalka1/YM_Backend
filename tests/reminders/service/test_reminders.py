from decimal import Decimal

import pytest

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.core.exceptions import AppError, NotFoundError
from app.reminders.models.reminder import ReminderActionType, ReminderStatus
from app.reminders.schemas.reminder import ReminderCreateRequest
from app.reminders.services.reminder_service import ReminderService
from app.tasks.models.task import Task, TaskPriority, TaskStatus
from app.utils.time_utils import utcnow


def _charge_for_client(charge_factory, client_record_id: int) -> Charge:
    return charge_factory(
        client_record_id=client_record_id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("100.00"),
    )


def _task_for_source(task_factory, *, source_domain: str, source_id: int) -> Task:
    return task_factory(
        title="Reminder target task",
        status=TaskStatus.OPEN,
        priority=TaskPriority.NORMAL,
        source_domain=source_domain,
        source_id=source_id,
    )


def test_create_scheduled_reminder_from_request(test_db, actor_user):
    now = utcnow()
    reminder = ReminderService(test_db).create_from_request(
        ReminderCreateRequest(
            fire_at=now,
            action_type=ReminderActionType.SEND_NOTIFICATION,
            source_domain="charge",
            source_id=12,
            notification_template_key="charge_due",
            payload={"charge_id": 12},
        ),
        created_by_user_id=actor_user.id,
    )

    assert reminder.status == ReminderStatus.SCHEDULED
    assert reminder.created_by_user_id == actor_user.id
    assert reminder.payload == {"charge_id": 12}


def test_list_reminders_batch_enriches_client_display(test_db, client_factory, actor_user):
    first = client_factory(
        full_name="Reminder Client One",
        id_number="REM001",
        office_client_number=101,
    )
    second = client_factory(
        full_name="Reminder Client Two",
        id_number="REM002",
        office_client_number=202,
    )
    service = ReminderService(test_db)
    service.create_from_request(
        ReminderCreateRequest(
            fire_at=utcnow(),
            action_type=ReminderActionType.SEND_NOTIFICATION,
            payload={"client_record_id": first.id},
        ),
        created_by_user_id=actor_user.id,
    )
    service.create_from_request(
        ReminderCreateRequest(
            fire_at=utcnow(),
            action_type=ReminderActionType.SEND_NOTIFICATION,
            payload={"client_record_id": str(second.id)},
        ),
        created_by_user_id=actor_user.id,
    )

    reminders, total = service.get_reminders(status="scheduled")
    items = service.to_responses(reminders)

    assert total == 2
    profiles = {
        item.client_record_id: (item.client_name, item.office_client_number) for item in items
    }
    assert profiles[first.id] == ("Reminder Client One", 101)
    assert profiles[second.id] == ("Reminder Client Two", 202)


def test_reminder_response_enriches_client_display_from_source_link(
    test_db, client_factory, charge_factory, actor_user
):
    client = client_factory(
        full_name="Reminder Source Client",
        id_number="REM003",
        office_client_number=303,
    )
    charge = _charge_for_client(charge_factory, client.id)
    service = ReminderService(test_db)
    reminder = service.create_from_request(
        ReminderCreateRequest(
            fire_at=utcnow(),
            action_type=ReminderActionType.SEND_NOTIFICATION,
            source_domain="charge",
            source_id=charge.id,
        ),
        created_by_user_id=actor_user.id,
    )

    response = service.to_response(reminder)

    assert response.client_record_id == client.id
    assert response.client_name == "Reminder Source Client"
    assert response.office_client_number == 303


def test_reminder_response_enriches_client_display_from_target_task_source(
    test_db, client_factory, charge_factory, task_factory, actor_user
):
    client = client_factory(
        full_name="Reminder Task Client",
        id_number="REM004",
        office_client_number=404,
    )
    charge = _charge_for_client(charge_factory, client.id)
    task = _task_for_source(task_factory, source_domain="charge", source_id=charge.id)
    service = ReminderService(test_db)
    reminder = service.create_from_request(
        ReminderCreateRequest(
            fire_at=utcnow(),
            action_type=ReminderActionType.CREATE_TASK,
            target_task_id=task.id,
        ),
        created_by_user_id=actor_user.id,
    )

    response = service.to_response(reminder)

    assert response.client_record_id == client.id
    assert response.client_name == "Reminder Task Client"
    assert response.office_client_number == 404


def test_cancel_only_scheduled_reminders(test_db, actor_user):
    service = ReminderService(test_db)
    reminder = service.create_from_request(
        ReminderCreateRequest(
            fire_at=utcnow(),
            action_type=ReminderActionType.CREATE_TASK,
        ),
        created_by_user_id=actor_user.id,
    )

    canceled = service.cancel_reminder(reminder.id)
    assert canceled.status == ReminderStatus.CANCELED
    with pytest.raises(AppError):
        service.cancel_reminder(reminder.id)


@pytest.mark.parametrize(
    "terminal_status",
    [ReminderStatus.FAILED, ReminderStatus.FIRED],
)
def test_cancel_terminal_reminder_rejected(test_db, terminal_status, actor_user):
    service = ReminderService(test_db)
    reminder = service.create_from_request(
        ReminderCreateRequest(
            fire_at=utcnow(),
            action_type=ReminderActionType.CREATE_TASK,
        ),
        created_by_user_id=actor_user.id,
    )
    service.reminder_repo.update_status(reminder.id, terminal_status)

    with pytest.raises(AppError):
        service.cancel_reminder(reminder.id)


def test_cancel_missing_reminder_raises_not_found(test_db):
    with pytest.raises(NotFoundError):
        ReminderService(test_db).cancel_reminder(999999)
