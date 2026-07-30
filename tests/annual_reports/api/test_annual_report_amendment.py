from decimal import Decimal

from app.annual_reports.models.annual_report_credit_point_reason import (
    AnnualReportCreditPoint,
    CreditPointReason,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.common.enums import ObligationStatus


def _force_submitted(db, report_id: int):
    AnnualReportService(db).repo.update(report_id, status=ObligationStatus.SUBMITTED)
    db.commit()


def test_an_open_amendment_cannot_be_deleted(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """Deleting the tip would leave the tax year with no visible report at all.

    An amendment is born open, so the lock gate lets it through: the original
    keeps its ``superseded_at`` stamp and would be hidden as corrected while the
    amendment is hidden as deleted — and the year could then be neither amended
    again nor recreated.
    """
    crm_client = client_factory()
    original_id = annual_report_service_factory(actor=test_user, client=crm_client).id
    _force_submitted(test_db, original_id)

    amendment = client.post(f"/api/v1/annual-reports/{original_id}/amend", headers=advisor_headers)
    assert amendment.status_code == 201
    amendment_id = amendment.json()["id"]
    assert amendment.json()["amends_id"] == original_id

    resp = client.delete(f"/api/v1/annual-reports/{amendment_id}", headers=advisor_headers)

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "OBLIGATION.AMENDMENT_NOT_DELETABLE"
    # The tip survives, so the year is still one visible report.
    assert (
        client.get(f"/api/v1/annual-reports/{amendment_id}", headers=advisor_headers).status_code
        == 200
    )


def _amend(client, headers, original_id: int) -> int:
    resp = client.post(f"/api/v1/annual-reports/{original_id}/amend", headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def test_amendment_copies_the_whole_material(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """D-21: the correction starts from everything the original held.

    Every child table is represented, because each is copied by its own parent
    key and the detail's is named differently from the rest — ``report_id``
    where the lines and schedules use ``annual_report_id``. A copy that names
    the wrong column does not fail quietly; it fails the whole amendment.
    """
    crm_client = client_factory()
    original_id = annual_report_service_factory(actor=test_user, client=crm_client).id

    assert (
        client.patch(
            f"/api/v1/annual-reports/{original_id}/details",
            headers=advisor_headers,
            json={"pension_contribution": "1200.50", "internal_notes": "מקור"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/annual-reports/{original_id}/income",
            headers=advisor_headers,
            json={"source_type": "salary", "amount": "5000.00", "description": "משכורת"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/annual-reports/{original_id}/expenses",
            headers=advisor_headers,
            json={"category": "office_rent", "amount": "900.00"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/annual-reports/{original_id}/annex/schedule_b",
            headers=advisor_headers,
            json={"data": {"rental_income": 12000}, "notes": "שורת נספח"},
        ).status_code
        == 201
    )
    test_db.add(
        AnnualReportCreditPoint(
            annual_report_id=original_id,
            reason=CreditPointReason.RESIDENT,
            points=Decimal("2.25"),
        )
    )
    test_db.commit()
    _force_submitted(test_db, original_id)

    amendment_id = _amend(client, advisor_headers, original_id)

    test_db.expire_all()
    amendment = test_db.get(AnnualReport, amendment_id)
    assert amendment.detail is not None
    assert amendment.detail.report_id == amendment_id
    assert amendment.detail.pension_contribution == Decimal("1200.50")
    assert amendment.detail.internal_notes == "מקור"
    assert [(line.source_type.value, line.amount) for line in amendment.income_lines] == [
        ("salary", Decimal("5000.00"))
    ]
    assert [(line.category.value, line.amount) for line in amendment.expense_lines] == [
        ("office_rent", Decimal("900.00"))
    ]
    assert [(cp.reason, cp.points) for cp in amendment.credit_points] == [
        (CreditPointReason.RESIDENT, Decimal("2.25"))
    ]
    copied_entries = {entry.schedule.value: entry for entry in amendment.schedule_entries}
    assert "schedule_b" in copied_entries
    assert [line.data for line in copied_entries["schedule_b"].annex_lines] == [
        {"rental_income": 12000}
    ]

    # The original keeps its own material — the copy re-parents nothing.
    original = test_db.get(AnnualReport, original_id)
    assert original.detail is not None and original.detail.report_id == original_id
    assert len(original.income_lines) == 1
    assert len(original.expense_lines) == 1
    assert len(original.credit_points) == 1


def test_withdrawing_an_amendment_restores_the_original_and_frees_the_chain(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """The whole point of the act: the year comes back, and can be corrected again.

    The second amendment is what proves the ``amends_id`` slot was freed — its
    unique index excludes deleted rows only, so a withdrawal that moved the
    correction to ``CANCELED`` instead would fail here on a unique violation.
    """
    crm_client = client_factory()
    original_id = annual_report_service_factory(actor=test_user, client=crm_client).id
    _force_submitted(test_db, original_id)
    amendment_id = _amend(client, advisor_headers, original_id)

    resp = client.post(f"/api/v1/annual-reports/{amendment_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == original_id
    assert body["status"] == ObligationStatus.SUBMITTED.value
    assert body["superseded_at"] is None
    assert body["amends_id"] is None

    assert (
        client.get(f"/api/v1/annual-reports/{amendment_id}", headers=advisor_headers).status_code
        == 404
    )
    assert _amend(client, advisor_headers, original_id) != amendment_id


def test_a_withdrawn_amendment_stays_in_the_chain(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """The one read that shows what happened, not what counts."""
    crm_client = client_factory()
    original_id = annual_report_service_factory(actor=test_user, client=crm_client).id
    _force_submitted(test_db, original_id)
    amendment_id = _amend(client, advisor_headers, original_id)
    assert (
        client.post(
            f"/api/v1/annual-reports/{amendment_id}/withdraw", headers=advisor_headers
        ).status_code
        == 200
    )

    chain = client.get(f"/api/v1/annual-reports/{original_id}/chain", headers=advisor_headers)

    assert chain.status_code == 200
    records = {record["id"]: record for record in chain.json()}
    assert set(records) == {original_id, amendment_id}
    assert records[amendment_id]["is_withdrawn"] is True
    assert records[original_id]["is_withdrawn"] is False
    assert records[original_id]["superseded_at"] is None


def test_withdrawing_a_report_that_is_not_an_amendment_is_rejected(
    client, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """Withdrawing undoes a link; a standalone report has none to undo."""
    crm_client = client_factory()
    report_id = annual_report_service_factory(actor=test_user, client=crm_client).id

    resp = client.post(f"/api/v1/annual-reports/{report_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.NOT_AN_AMENDMENT"


def test_a_filed_amendment_cannot_be_withdrawn(
    client, test_db, advisor_headers, test_user, client_factory, annual_report_service_factory
):
    """Once a correction is filed it is the record of a filing (D-13)."""
    crm_client = client_factory()
    original_id = annual_report_service_factory(actor=test_user, client=crm_client).id
    _force_submitted(test_db, original_id)
    amendment_id = _amend(client, advisor_headers, original_id)
    _force_submitted(test_db, amendment_id)

    resp = client.post(f"/api/v1/annual-reports/{amendment_id}/withdraw", headers=advisor_headers)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "OBLIGATION.LOCKED"
