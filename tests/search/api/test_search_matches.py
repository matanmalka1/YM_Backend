"""Record matching: the typed term matches records of every type, phase-1 exact only."""

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
    TRIGGER_LABELS,
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


def _make_binder(db, client_record_id, binder_number, user_id):
    binder = Binder(
        client_record_id=client_record_id,
        binder_number=binder_number,
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
    )
    db.add(binder)
    db.commit()
    db.refresh(binder)
    return binder


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


def _make_notification(db, client_record_id, *, recipient="client@example.com"):
    notification = Notification(
        client_record_id=client_record_id,
        trigger=NotificationTrigger.PAYMENT_REMINDER,
        channel=NotificationChannel.EMAIL,
        recipient=recipient,
        content_snapshot="גוף ההודעה",
        subject_snapshot="תזכורת תשלום",
        status=NotificationStatus.SENT,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def _make_task(db, client_record_id, user_id, title, **fields):
    task = Task(
        title=title, client_record_id=client_record_id, created_by_user_id=user_id, **fields
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _matches(client, headers, term):
    response = client.get(f"/api/v1/search?search={term}", headers=headers)
    assert response.status_code == 200
    return response.json()["matches"]


def test_a_binder_number_matches_the_binder_itself(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="בעל קלסר")
    binder = _make_binder(test_db, crm_client.id, "MATCH-101", test_user.id)

    group = _matches(client, advisor_headers, "MATCH-101")["binders"]

    assert [row["id"] for row in group["items"]] == [binder.id]
    assert group["total"] == 1
    row = group["items"][0]
    assert row["title"] == "קלסר MATCH-101"
    assert row["client_record_id"] == crm_client.id
    assert row["client_name"] == "בעל קלסר"
    assert row["href"] == f"/binders?binder_id={binder.id}"


def test_a_full_filename_matches_the_document(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, business = create_client_with_business(full_name="בעל מסמך")
    document = _make_document(
        test_db,
        client_record_id=crm_client.id,
        business_id=business.id,
        filename="audit_2026.pdf",
        user_id=test_user.id,
    )

    group = _matches(client, advisor_headers, "audit_2026.pdf")["documents"]

    assert [row["id"] for row in group["items"]] == [document.id]
    row = group["items"][0]
    assert row["status"] is None
    assert row["title"] == "audit_2026.pdf"
    assert row["detail"] == PermanentDocumentType.OTHER.value
    assert row["href"] == f"/clients/{crm_client.id}/documents?document_id={document.id}"


def test_a_period_matches_vat_and_advance_payments_in_every_written_form(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """`03/2026`, `3/2026` and `2026-03` are the same period — users type what screens show."""
    crm_client, _ = create_client_with_business(full_name="לקוח תקופה")
    vat = create_linked_vat_work_item(
        test_db, client_record_id=crm_client.id, period="2026-03", created_by=test_user.id
    )
    advance = create_linked_advance_payment(
        test_db,
        client_record_id=crm_client.id,
        period="2026-03",
        due_date=date(2026, 4, 15),
        expected_amount=Decimal("800"),
    )

    for term in ("2026-03", "03/2026", "3/2026"):
        matches = _matches(client, advisor_headers, term)
        assert [row["id"] for row in matches["vat_work_items"]["items"]] == [vat.id], term
        assert [row["id"] for row in matches["advance_payments"]["items"]] == [advance.id], term


def test_a_tax_year_and_an_ita_reference_match_the_annual_report(
    client, test_db, advisor_headers, test_user, create_client_with_business, annual_report_factory
):
    crm_client, _ = create_client_with_business(full_name="לקוח שנתי")
    report = annual_report_factory(client=crm_client, actor=test_user, tax_year=2027)
    report.ita_reference = "900123456"
    test_db.commit()

    by_year = _matches(client, advisor_headers, "2027")["annual_reports"]
    by_reference = _matches(client, advisor_headers, "900123456")["annual_reports"]

    assert [row["id"] for row in by_year["items"]] == [report.id]
    assert [row["id"] for row in by_reference["items"]] == [report.id]


def test_a_charge_id_matches_the_charge(
    client, test_db, advisor_headers, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="לקוח חיוב")
    charge = Charge(
        client_record_id=crm_client.id,
        charge_type=ChargeType.ANNUAL_REPORT_FEE,
        status=ChargeStatus.ISSUED,
        amount=Decimal("1500"),
        period="2026-01",
    )
    test_db.add(charge)
    test_db.commit()
    test_db.refresh(charge)

    group = _matches(client, advisor_headers, str(charge.id))["charges"]

    assert [row["id"] for row in group["items"]] == [charge.id]
    assert group["items"][0]["title"] == f"חיוב #{charge.id}"
    assert group["items"][0]["amount"] == "1500.00"


def test_an_exact_title_matches_the_task(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="לקוח משימה")
    task = _make_task(
        test_db, crm_client.id, test_user.id, "השלמת מסמכים", due_date=date(2026, 3, 15)
    )

    group = _matches(client, advisor_headers, "השלמת מסמכים")["tasks"]

    assert [row["id"] for row in group["items"]] == [task.id]
    assert group["items"][0]["occurred_on"] == "2026-03-15"


def test_a_recipient_email_matches_the_notification(
    client, test_db, advisor_headers, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="לקוח התראה")
    notification = _make_notification(test_db, crm_client.id, recipient="דוא@example.com")

    group = _matches(client, advisor_headers, "דוא@example.com")["notifications"]

    assert [row["id"] for row in group["items"]] == [notification.id]
    row = group["items"][0]
    assert row["title"] == TRIGGER_LABELS[NotificationTrigger.PAYMENT_REMINDER]
    assert row["detail"] == "תזכורת תשלום"


def test_recipient_matching_is_case_sensitive_in_phase_one(
    client, test_db, advisor_headers, create_client_with_business
):
    """Exact means exact: no ILIKE ships before the index that serves it (D7).

    Documented product decision (2026-07-21) — revisit with phase-2 measurement.
    """
    crm_client, _ = create_client_with_business(full_name="לקוח רישיות")
    _make_notification(test_db, crm_client.id, recipient="User@Example.com")

    group = _matches(client, advisor_headers, "user@example.com")["notifications"]

    assert group == {"items": [], "total": 0}


def test_an_internal_db_id_matches_nothing(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """D4: a column participates only if the UI shows it as the record's identifier."""
    crm_client, _ = create_client_with_business(full_name="לקוח פנימי")
    task = _make_task(test_db, crm_client.id, test_user.id, "משימה חסויה")
    notification = _make_notification(test_db, crm_client.id)

    for internal_id in (task.id, notification.id):
        matches = _matches(client, advisor_headers, str(internal_id))
        assert matches["tasks"] == {"items": [], "total": 0}
        assert matches["notifications"] == {"items": [], "total": 0}


def test_a_bare_number_does_not_match_free_text(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """A bare integer is an identifier; titles and filenames are not identifiers."""
    crm_client, _ = create_client_with_business(full_name="לקוח מספרי")
    _make_task(test_db, crm_client.id, test_user.id, "2026")

    assert _matches(client, advisor_headers, "2026")["tasks"] == {"items": [], "total": 0}


def test_preview_caps_at_five_and_reports_the_true_total(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="לקוח תקרה")
    for _ in range(7):
        _make_task(test_db, crm_client.id, test_user.id, "אותו שם בדיוק")

    group = _matches(client, advisor_headers, "אותו שם בדיוק")["tasks"]

    assert len(group["items"]) == 5
    assert group["total"] == 7


def test_expansion_pages_the_type_and_agrees_with_the_preview(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """The preview is the first page of the expansion: same rows, same order, same total."""
    crm_client, _ = create_client_with_business(full_name="לקוח הרחבה")
    for _ in range(7):
        _make_task(test_db, crm_client.id, test_user.id, "כפילות מותרת")

    preview = _matches(client, advisor_headers, "כפילות מותרת")["tasks"]
    base = "/api/v1/search/items?search=כפילות מותרת&result_type=task"
    first = client.get(f"{base}&page=1&page_size=5", headers=advisor_headers).json()
    second = client.get(f"{base}&page=2&page_size=5", headers=advisor_headers).json()

    assert first["total"] == preview["total"] == 7
    assert [row["id"] for row in first["items"]] == [row["id"] for row in preview["items"]]
    assert len(second["items"]) == 2
    assert {row["id"] for row in first["items"]}.isdisjoint({row["id"] for row in second["items"]})


def test_identical_titles_on_different_records_are_not_deduped(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    first_client, _ = create_client_with_business(full_name="לקוח אחד")
    second_client, _ = create_client_with_business(full_name="לקוח שני")
    mine = _make_task(test_db, first_client.id, test_user.id, "שם משותף")
    theirs = _make_task(test_db, second_client.id, test_user.id, "שם משותף")

    group = _matches(client, advisor_headers, "שם משותף")["tasks"]

    assert {row["id"] for row in group["items"]} == {mine.id, theirs.id}
    assert group["total"] == 2
    names = {row["client_name"] for row in group["items"]}
    assert names == {"לקוח אחד", "לקוח שני"}


def test_clients_and_matches_coexist_in_one_response(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    """Both sections non-empty at once is the point of the page."""
    crm_client, _ = create_client_with_business(full_name="חופף")
    _make_task(test_db, crm_client.id, test_user.id, "חופף")

    response = client.get("/api/v1/search?search=חופף", headers=advisor_headers).json()

    assert [row["id"] for row in response["clients"]["items"]] == [crm_client.id]
    assert len(response["matches"]["tasks"]["items"]) == 1


def test_match_rows_carry_the_same_client_name_resolution_returns(
    client, test_db, advisor_headers, test_user, create_client_with_business
):
    crm_client, _ = create_client_with_business(full_name="שם קנוני")
    _make_task(test_db, crm_client.id, test_user.id, "שם קנוני")

    response = client.get("/api/v1/search?search=שם קנוני", headers=advisor_headers).json()

    resolved_name = response["clients"]["items"][0]["name"]
    match_row = response["matches"]["tasks"]["items"][0]
    assert match_row["client_name"] == resolved_name
    assert (
        match_row["client_office_number"] == response["clients"]["items"][0]["office_client_number"]
    )
