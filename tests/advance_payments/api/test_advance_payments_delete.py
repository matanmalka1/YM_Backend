from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.audit.audit_constants import (
    ACTION_ADVANCE_PAYMENT_DELETED,
    ENTITY_ADVANCE_PAYMENT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.common.enums import ObligationStatus
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_delete_advance_payment_success(
    client, test_db, advisor_headers, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Advance Delete Client", id_number="ADV-DEL-001"
    )
    repo = AdvancePaymentRepository(test_db)
    payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-04",
        period_months_count=1,
        due_date=date(2026, 5, 15),
    )

    resp = client.request(
        "DELETE",
        f"/api/v1/clients/{business.client_record_id}/advance-payments/{payment.id}",
        headers=advisor_headers,
        json={"reason": "נוצר בטעות"},
    )

    assert resp.status_code == 204
    assert repo.get_by_id(payment.id) is None

    logged = test_db.scalars(
        select(EntityAuditLog).where(
            EntityAuditLog.entity_type == ENTITY_ADVANCE_PAYMENT,
            EntityAuditLog.entity_id == payment.id,
            EntityAuditLog.action == ACTION_ADVANCE_PAYMENT_DELETED,
        )
    ).all()
    assert len(logged) == 1
    assert logged[0].metadata_json["reason"] == "נוצר בטעות"


def test_delete_advance_payment_requires_reason(
    client, test_db, advisor_headers, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Advance Delete Client", id_number="ADV-DEL-001"
    )
    repo = AdvancePaymentRepository(test_db)
    payment = create_linked_advance_payment(
        test_db,
        repo=repo,
        client_record_id=business.client_record_id,
        period="2026-05",
        period_months_count=1,
        due_date=date(2026, 6, 15),
    )
    url = f"/api/v1/clients/{business.client_record_id}/advance-payments/{payment.id}"

    no_body = client.request("DELETE", url, headers=advisor_headers)
    blank_reason = client.request("DELETE", url, headers=advisor_headers, json={"reason": "   "})

    assert no_body.status_code == 422
    assert blank_reason.status_code == 422
    assert repo.get_by_id(payment.id) is not None


def test_delete_advance_payment_not_found(
    client, test_db, advisor_headers, create_client_with_business
):
    _client, business = create_client_with_business(
        full_name="Advance Delete Client", id_number="ADV-DEL-001"
    )
    resp = client.request(
        "DELETE",
        f"/api/v1/clients/{business.client_record_id}/advance-payments/999999",
        headers=advisor_headers,
        json={"reason": "בדיקה"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ADVANCE_PAYMENT.NOT_FOUND"


def test_delete_advance_payment_rejects_an_amendment(
    client, test_db, advisor_headers, create_client_with_business, test_user
):
    """An amendment is born open, so the lock gate lets it through.

    Deleting it would leave the payment it corrects stamped as superseded — the
    period would show no row at all, and it could be neither amended again nor
    recreated.
    """
    crm_client, _business = create_client_with_business(
        full_name="Advance Amendment Delete Client", id_number="ADV-AMEND-DEL-001"
    )
    repo = AdvancePaymentRepository(test_db)
    original = create_linked_advance_payment(
        test_db,
        client_record_id=crm_client.id,
        period="2026-07",
        due_date=date(2026, 8, 15),
        expected_amount=Decimal("1000.00"),
        paid_amount=Decimal("1000.00"),
        assigned_to=test_user.id,
        status=ObligationStatus.SUBMITTED,
    )
    test_db.commit()
    amendment = client.post(
        f"/api/v1/clients/{crm_client.id}/advance-payments/{original.id}/amend",
        headers=advisor_headers,
    )
    assert amendment.status_code == 201
    amendment_id = amendment.json()["id"]

    resp = client.request(
        "DELETE",
        f"/api/v1/clients/{crm_client.id}/advance-payments/{amendment_id}",
        headers=advisor_headers,
        json={"reason": "נוצר בטעות"},
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "OBLIGATION.AMENDMENT_NOT_DELETABLE"
    # The tip survives, so the period is still one visible row.
    assert repo.get_by_id(amendment_id) is not None
