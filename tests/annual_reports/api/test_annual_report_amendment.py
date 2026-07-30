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
