from datetime import date

from sqlalchemy import select

from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.audit.audit_constants import (
    ACTION_ADVANCE_PAYMENT_DELETED,
    ENTITY_ADVANCE_PAYMENT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.businesses.models.business import Business
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def _create_business(test_db) -> Business:
    client = seed_client_identity(
        test_db,
        full_name="Advance Delete Client",
        id_number="ADV-DEL-001",
    )
    business = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name="Advance Delete Business",
        opened_at=date.today(),
    )
    test_db.commit()
    test_db.refresh(business)
    business.client_record_id = client.id
    return business


def test_delete_advance_payment_success(client, test_db, advisor_headers):
    business = _create_business(test_db)
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


def test_delete_advance_payment_requires_reason(client, test_db, advisor_headers):
    business = _create_business(test_db)
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


def test_delete_advance_payment_not_found(client, test_db, advisor_headers):
    business = _create_business(test_db)
    resp = client.request(
        "DELETE",
        f"/api/v1/clients/{business.client_record_id}/advance-payments/999999",
        headers=advisor_headers,
        json={"reason": "בדיקה"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ADVANCE_PAYMENT.NOT_FOUND"
