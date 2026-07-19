"""Phase two of search: the selected client's items, in one shape across every type."""

from datetime import date
from decimal import Decimal

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocument,
    PermanentDocumentType,
)
from app.notifications.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.tasks.models.task import Task
from tests.helpers.tax_calendar_links import (
    create_linked_advance_payment,
    create_linked_vat_work_item,
)


def _make_document(db, *, client_record_id, business_id, filename, user_id):
    document = PermanentDocument(
        client_record_id=client_record_id,
        business_id=business_id,
        scope=DocumentScope.BUSINESS,
        document_type=PermanentDocumentType.OTHER,
        storage_key=f"tests/{client_record_id}/{filename}",
        original_filename=filename,
        uploaded_by=user_id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _make_notification(db, client_record_id: int) -> Notification:
    notification = Notification(
        client_record_id=client_record_id,
        trigger=NotificationTrigger.PAYMENT_REMINDER,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="גוף ההודעה",
        subject_snapshot="תזכורת תשלום",
        status=NotificationStatus.SENT,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def test_single_client_match_auto_selects_and_returns_every_type(
    client, test_db, advisor_headers, test_user, create_client_with_business, annual_report_factory
):
    crm_client, business = create_client_with_business(full_name="פיד מלא")
    binder = Binder(
        client_record_id=crm_client.id,
        binder_number="FEED-001",
        period_start=date.today(),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
    )
    task = Task(
        title="השלמת מסמכים", client_record_id=crm_client.id, created_by_user_id=test_user.id
    )
    charge = Charge(
        client_record_id=crm_client.id,
        charge_type=ChargeType.ANNUAL_REPORT_FEE,
        status=ChargeStatus.ISSUED,
        amount=Decimal("1500"),
        period="2026-01",
    )
    test_db.add_all([binder, task, charge])
    vat = create_linked_vat_work_item(
        test_db, client_record_id=crm_client.id, period="2026-01", created_by=test_user.id
    )
    advance = create_linked_advance_payment(
        test_db,
        client_record_id=crm_client.id,
        period="2026-01",
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("800"),
    )
    report = annual_report_factory(client=crm_client, actor=test_user, tax_year=2026)
    document = _make_document(
        test_db,
        client_record_id=crm_client.id,
        business_id=business.id,
        filename="audit_2026.pdf",
        user_id=test_user.id,
    )
    notification = _make_notification(test_db, crm_client.id)

    response = client.get("/api/v1/search?search=פיד%20מלא", headers=advisor_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [row["id"] for row in items["binders"]["items"]] == [binder.id]
    assert [row["id"] for row in items["documents"]["items"]] == [document.id]
    assert [row["id"] for row in items["vat_work_items"]["items"]] == [vat.id]
    assert [row["id"] for row in items["annual_reports"]["items"]] == [report.id]
    assert [row["id"] for row in items["advance_payments"]["items"]] == [advance.id]
    assert [row["id"] for row in items["charges"]["items"]] == [charge.id]
    assert [row["id"] for row in items["tasks"]["items"]] == [task.id]
    assert [row["id"] for row in items["notifications"]["items"]] == [notification.id]
    assert all(group["total"] == 1 for group in items.values())


def test_every_item_carries_a_deep_link_to_itself(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, business = create_client_with_business(full_name="קישורים")
    task = Task(title="משימה", client_record_id=crm_client.id, created_by_user_id=test_user.id)
    binder = Binder(
        client_record_id=crm_client.id,
        binder_number="LINK-001",
        period_start=date.today(),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
    )
    test_db.add_all([task, binder])
    test_db.commit()
    document = _make_document(
        test_db,
        client_record_id=crm_client.id,
        business_id=business.id,
        filename="linked.pdf",
        user_id=test_user.id,
    )
    notification = _make_notification(test_db, crm_client.id)

    items = client.get("/api/v1/search?search=קישורים", headers=advisor_headers).json()["items"]

    assert items["tasks"]["items"][0]["href"] == f"/tasks?task_id={task.id}"
    assert items["binders"]["items"][0]["href"] == f"/binders?binder_id={binder.id}"
    assert (
        items["documents"]["items"][0]["href"]
        == f"/clients/{crm_client.id}/documents?document_id={document.id}"
    )
    assert (
        items["notifications"]["items"][0]["href"]
        == f"/notifications?notification_id={notification.id}"
    )


def test_documents_have_no_status_and_show_their_type_instead(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, business = create_client_with_business(full_name="מסמך בלבד")
    _make_document(
        test_db,
        client_record_id=crm_client.id,
        business_id=business.id,
        filename="statusless.pdf",
        user_id=test_user.id,
    )

    row = client.get("/api/v1/search?search=מסמך%20בלבד", headers=advisor_headers).json()["items"][
        "documents"
    ]["items"][0]

    assert row["status"] is None
    assert row["title"] == "statusless.pdf"
    assert row["detail"] == PermanentDocumentType.OTHER.value


def test_items_stay_empty_while_several_clients_match(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """Nothing is shown until one client is chosen — a feed of two clients is meaningless."""
    first, _ = create_client_with_business(full_name="Ambiguous Client One")
    second, _ = create_client_with_business(full_name="Ambiguous Client Two")
    test_db.add_all(
        [
            Task(title="a", client_record_id=first.id, created_by_user_id=test_user.id),
            Task(title="b", client_record_id=second.id, created_by_user_id=test_user.id),
        ]
    )
    test_db.commit()

    data = client.get("/api/v1/search?search=Ambiguous", headers=advisor_headers).json()

    assert data["clients"]["total"] == 2
    assert data["items"]["tasks"] == {"items": [], "total": 0}


def test_items_never_leak_across_clients(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    owner, owner_business = create_client_with_business(full_name="Owner Client")
    other, _ = create_client_with_business(full_name="Other Client")
    _make_document(
        test_db,
        client_record_id=owner.id,
        business_id=owner_business.id,
        filename="private.pdf",
        user_id=test_user.id,
    )

    data = client.get(f"/api/v1/search?client_record_id={other.id}", headers=advisor_headers).json()

    assert data["items"]["documents"] == {"items": [], "total": 0}


def test_selected_client_without_a_term_returns_its_items(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Selected Without Term")
    task = Task(title="latest", client_record_id=crm_client.id, created_by_user_id=test_user.id)
    test_db.add(task)
    test_db.commit()

    data = client.get(
        f"/api/v1/search?client_record_id={crm_client.id}", headers=advisor_headers
    ).json()

    assert [row["id"] for row in data["items"]["tasks"]["items"]] == [task.id]


def test_preview_caps_at_five_and_reports_the_true_total(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Preview Cap Client")
    test_db.add_all(
        [
            Task(
                title=f"task {index}",
                client_record_id=crm_client.id,
                created_by_user_id=test_user.id,
            )
            for index in range(7)
        ]
    )
    test_db.commit()

    group = client.get(
        f"/api/v1/search?client_record_id={crm_client.id}", headers=advisor_headers
    ).json()["items"]["tasks"]

    assert len(group["items"]) == 5
    assert group["total"] == 7


def test_expanding_a_group_pages_through_that_type(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="Expandable Client")
    test_db.add_all(
        [
            Task(
                title=f"task {index}",
                client_record_id=crm_client.id,
                created_by_user_id=test_user.id,
            )
            for index in range(7)
        ]
    )
    test_db.commit()

    base = f"/api/v1/search/items?client_record_id={crm_client.id}&result_type=task"
    first = client.get(f"{base}&page=1&page_size=5", headers=advisor_headers).json()
    second = client.get(f"{base}&page=2&page_size=5", headers=advisor_headers).json()

    assert first["total"] == 7
    assert len(first["items"]) == 5
    assert len(second["items"]) == 2
    assert {row["id"] for row in first["items"]}.isdisjoint({row["id"] for row in second["items"]})


def test_items_carry_the_date_they_are_anchored_to(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """A mixed feed is unreadable without dates; each type exposes its own anchor date."""
    crm_client, _ = create_client_with_business(full_name="תאריכים")
    task = Task(
        title="משימה עם תאריך",
        client_record_id=crm_client.id,
        created_by_user_id=test_user.id,
        due_date=date(2026, 3, 15),
    )
    test_db.add(task)
    test_db.commit()

    row = client.get("/api/v1/search?search=תאריכים", headers=advisor_headers).json()["items"][
        "tasks"
    ]["items"][0]

    assert row["occurred_on"] == "2026-03-15"
