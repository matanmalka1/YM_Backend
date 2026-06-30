"""Phase 3 — per-VAT-mutation EntityAuditLog write coverage + atomicity (§17).

Each VAT mutation must emit the correct namespaced action with
``metadata_json.client_record_id`` and a real ``user`` actor, in the same
transaction as the domain change (a failed audit write rolls the mutation back).
"""

import pytest
from sqlalchemy import select

from app.audit.audit_constants import (
    ACTION_VAT_INVOICE_AMOUNT_CHANGED,
    ACTION_VAT_INVOICE_DELETED,
    ACTION_VAT_INVOICE_UPDATED,
    ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN,
    ACTION_VAT_WORK_ITEM_CREATED,
    ACTION_VAT_WORK_ITEM_FILED,
    ENTITY_VAT_INVOICE,
    ENTITY_VAT_WORK_ITEM,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import VatType
from app.core.exceptions import AppError
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.helpers.tax_calendar_links import create_linked_vat_work_item
from tests.vat.api.test_vat_reports_utils import (
    add_income_invoice,
    create_work_item,
    setup_ready_item,
)


def _rows(test_db, entity_type: str, entity_id: int) -> list[EntityAuditLog]:
    return list(
        test_db.scalars(
            select(EntityAuditLog).where(
                EntityAuditLog.entity_type == entity_type,
                EntityAuditLog.entity_id == entity_id,
            )
        )
    )


def _action(rows: list[EntityAuditLog], action: str) -> EntityAuditLog:
    return next(r for r in rows if r.action == action)


def test_create_writes_vat_work_item_created(client, test_db, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2025-07")
    row = _action(_rows(test_db, ENTITY_VAT_WORK_ITEM, item_id), ACTION_VAT_WORK_ITEM_CREATED)
    assert row.metadata_json["client_record_id"] == vat_client.id
    assert row.metadata_json["period"] == "2025-07"
    assert row.metadata_json["tax_year"] == 2025
    assert row.actor_type == "user"
    assert row.performed_by is not None
    assert row.actor_display_name  # threaded from current_user.full_name


def test_filing_writes_filed_audit(client, test_db, advisor_headers, vat_client, test_user):
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2025-08", assigned_to=test_user.id
    )
    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/file",
        headers=advisor_headers,
        json={"submission_method": "online"},
    )
    assert resp.status_code == 200
    filed = _action(_rows(test_db, ENTITY_VAT_WORK_ITEM, item_id), ACTION_VAT_WORK_ITEM_FILED)
    assert filed.new_value["is_overridden"] is False
    assert "final_vat_amount" in filed.new_value
    assert filed.metadata_json["client_record_id"] == vat_client.id


def test_override_writes_amount_overridden_audit(
    client, test_db, advisor_headers, vat_client, test_user
):
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2025-10", assigned_to=test_user.id
    )
    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/file",
        headers=advisor_headers,
        json={
            "submission_method": "online",
            "override_amount": "999.00",
            "override_justification": "manual adjustment",
        },
    )
    assert resp.status_code == 200
    rows = _rows(test_db, ENTITY_VAT_WORK_ITEM, item_id)
    override = _action(rows, ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN)
    assert float(override.new_value["final_vat_amount"]) == 999.0
    assert override.note == "manual adjustment"
    assert override.metadata_json["client_record_id"] == vat_client.id


def test_invoice_amount_change_writes_amount_changed(client, test_db, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2025-11")
    invoice = add_income_invoice(client, advisor_headers, item_id)
    invoice_id = invoice["id"]

    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"gross_amount": "2360.00"},
    )
    assert resp.status_code == 200
    row = _action(_rows(test_db, ENTITY_VAT_INVOICE, invoice_id), ACTION_VAT_INVOICE_AMOUNT_CHANGED)
    assert row.metadata_json["vat_work_item_id"] == item_id
    assert row.metadata_json["client_record_id"] == vat_client.id
    assert row.old_value["vat_amount"] != row.new_value["vat_amount"]


def test_invoice_non_amount_update_writes_updated(client, test_db, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2025-12")
    invoice = add_income_invoice(client, advisor_headers, item_id)
    invoice_id = invoice["id"]

    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"counterparty_name": "Renamed Customer"},
    )
    assert resp.status_code == 200
    actions = {r.action for r in _rows(test_db, ENTITY_VAT_INVOICE, invoice_id)}
    assert ACTION_VAT_INVOICE_UPDATED in actions
    assert ACTION_VAT_INVOICE_AMOUNT_CHANGED not in actions


def test_invoice_delete_writes_deleted(client, test_db, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-06")
    invoice = add_income_invoice(client, advisor_headers, item_id)
    invoice_id = invoice["id"]

    resp = client.delete(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
    )
    assert resp.status_code == 204
    row = _action(_rows(test_db, ENTITY_VAT_INVOICE, invoice_id), ACTION_VAT_INVOICE_DELETED)
    assert row.old_value["invoice_id"] == invoice_id
    assert row.metadata_json["vat_work_item_id"] == item_id


def test_audit_failure_rolls_back_vat_mutation(test_db, test_user, vat_client):
    """A failing audit write rolls back the VAT mutation in the same transaction
    (savepoint == the domain mutation's transaction); no orphan domain row remains."""
    repo = VatWorkItemRepository(test_db)
    writer = EntityAuditWriter(test_db)

    with pytest.raises(AppError):
        with test_db.begin_nested():
            item = create_linked_vat_work_item(
                test_db,
                repo=repo,
                client_record_id=vat_client.id,
                period="2026-07",
                period_type=VatType.MONTHLY,
                created_by=test_user.id,
            )
            # Forbidden field -> fail-closed validation raises -> savepoint rolls back.
            writer.record_action(
                ENTITY_VAT_WORK_ITEM,
                item.id,
                test_user.id,
                ACTION_VAT_WORK_ITEM_CREATED,
                new_value={"token_hash": "leak"},
                metadata_json={"client_record_id": vat_client.id},
            )

    persisted = test_db.scalars(
        select(VatWorkItem).where(
            VatWorkItem.client_record_id == vat_client.id,
            VatWorkItem.period == "2026-07",
        )
    ).all()
    assert persisted == []
