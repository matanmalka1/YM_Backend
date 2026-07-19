from app.businesses.services.business_status_card_service import StatusCardService
from app.tasks.models.task import Task, TaskStatus


def test_status_card_counts_only_open_client_tasks(test_db, test_user, create_client_with_business):
    client, _business = create_client_with_business(full_name="Status Card Client")
    test_db.add_all(
        [
            Task(
                title="Open client task",
                status=TaskStatus.OPEN,
                client_record_id=client.id,
                created_by_user_id=test_user.id,
            ),
            Task(
                title="Completed client task",
                status=TaskStatus.DONE,
                client_record_id=client.id,
                created_by_user_id=test_user.id,
            ),
            Task(
                title="Unrelated open task",
                status=TaskStatus.OPEN,
                created_by_user_id=test_user.id,
            ),
        ]
    )
    test_db.commit()

    result = StatusCardService(test_db).get_status_card(client.id, year=2026)

    assert result.tasks.open_count == 1
