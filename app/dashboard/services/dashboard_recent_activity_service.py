from datetime import UTC

from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.audit.audit_constants import (
    ACTION_BINDER_CREATED,
    ACTION_BINDER_HANDED_OVER,
    ACTION_BINDER_INTAKE_UPDATED,
    ACTION_BINDER_MARKED_FULL,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_BINDER_MATERIAL_RECEIVED,
    ACTION_BINDER_REOPENED,
    ACTION_BINDER_REVERTED_READY,
    ACTION_CHARGE_ISSUED,
    ACTION_CHARGE_PAID,
    ACTION_CREATED,
    ACTION_EXPENSE_ADDED,
    ACTION_EXPENSE_DELETED,
    ACTION_EXPENSE_UPDATED,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ACTION_INCOME_UPDATED,
    ACTION_STATUS_CHANGED,
    ACTION_UPDATED,
    ACTION_VAT_INVOICE_AMOUNT_CHANGED,
    ACTION_VAT_INVOICE_CREATED,
    ACTION_VAT_INVOICE_DELETED,
    ACTION_VAT_INVOICE_UPDATED,
    ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN,
    ACTION_VAT_WORK_ITEM_CREATED,
    ACTION_VAT_WORK_ITEM_DELETED,
    ACTION_VAT_WORK_ITEM_FILED,
    ACTION_VAT_WORK_ITEM_STATUS_CHANGED,
    ACTION_VAT_WORK_ITEM_UPDATED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_BINDER,
    ENTITY_BINDER_INTAKE,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
    ENTITY_VAT_INVOICE,
    ENTITY_VAT_WORK_ITEM,
    entity_action,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.repositories.audit_entity_audit_log_repository import EntityAuditLogRepository
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.repositories.client_record_read_repository import get_full_records_bulk
from app.common.entity_links import LinkedEntity, entity_route

_ACTIVITY_LIMIT = 5
# Fetches more than displayed to allow merging audit + binder rows before trimming to _ACTIVITY_LIMIT.
_ACTIVITY_FETCH_LIMIT = 20

_ENTITY_LABELS = {
    ENTITY_ANNUAL_REPORT: "דוח שנתי",
    ENTITY_CHARGE: "חיוב",
    ENTITY_CLIENT: "לקוח",
    ENTITY_BINDER: "קלסר",
    ENTITY_BINDER_INTAKE: "קליטת חומר",
    ENTITY_VAT_WORK_ITEM: "תיק מע״מ",
    ENTITY_VAT_INVOICE: "חשבונית מע״מ",
}

# Keyed by the namespaced persisted action value (e.g. "client.created").
_ACTION_LABELS = {
    entity_action(ENTITY_ANNUAL_REPORT, ACTION_CREATED): "נוצר דוח שנתי חדש",
    entity_action(ENTITY_CHARGE, ACTION_CREATED): "נוצר חיוב חדש",
    entity_action(ENTITY_CLIENT, ACTION_CREATED): "נוצר לקוח חדש",
    entity_action(ENTITY_ANNUAL_REPORT, ACTION_UPDATED): "עודכן דוח שנתי",
    entity_action(ENTITY_CHARGE, ACTION_UPDATED): "עודכן חיוב",
    entity_action(ENTITY_CLIENT, ACTION_UPDATED): "עודכן לקוח",
    ACTION_CHARGE_ISSUED: "נפתח חיוב חדש",
    ACTION_CHARGE_PAID: "חיוב סומן כשולם",
    entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED): "עודכן סטטוס דוח שנתי",
    entity_action(ENTITY_CHARGE, ACTION_STATUS_CHANGED): "עודכן סטטוס חיוב",
    entity_action(ENTITY_CLIENT, ACTION_STATUS_CHANGED): "עודכן סטטוס לקוח",
    ACTION_INCOME_ADDED: "נוספה שורת הכנסה בדוח שנתי",
    ACTION_INCOME_UPDATED: "עודכנה שורת הכנסה בדוח שנתי",
    ACTION_INCOME_DELETED: "נמחקה שורת הכנסה בדוח שנתי",
    ACTION_EXPENSE_ADDED: "נוספה שורת הוצאה בדוח שנתי",
    ACTION_EXPENSE_UPDATED: "עודכנה שורת הוצאה בדוח שנתי",
    ACTION_EXPENSE_DELETED: "נמחקה שורת הוצאה בדוח שנתי",
    ACTION_BINDER_CREATED: "נוצר קלסר חדש",
    ACTION_BINDER_MATERIAL_RECEIVED: "התקבל חומר לקלסר",
    ACTION_BINDER_MARKED_FULL: "קלסר סומן כמלא",
    ACTION_BINDER_REOPENED: "קלסר נפתח מחדש",
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER: "קלסר מוכן למסירה",
    ACTION_BINDER_REVERTED_READY: "קלסר חזר לעבודה במשרד",
    ACTION_BINDER_HANDED_OVER: "קלסר נמסר ללקוח",
    ACTION_BINDER_INTAKE_UPDATED: "עודכן אירוע קליטת חומר",
    ACTION_VAT_WORK_ITEM_CREATED: "נוצר תיק מע״מ",
    ACTION_VAT_WORK_ITEM_STATUS_CHANGED: "עודכן סטטוס תיק מע״מ",
    ACTION_VAT_WORK_ITEM_FILED: "דיווח מע״מ הוגש",
    ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN: "עודכן סכום מע״מ סופי",
    ACTION_VAT_WORK_ITEM_UPDATED: "עודכן תיק מע״מ",
    ACTION_VAT_WORK_ITEM_DELETED: "נמחק תיק מע״מ",
    ACTION_VAT_INVOICE_CREATED: "נוספה חשבונית מע״מ",
    ACTION_VAT_INVOICE_UPDATED: "עודכנה חשבונית מע״מ",
    ACTION_VAT_INVOICE_AMOUNT_CHANGED: "עודכן סכום חשבונית מע״מ",
    ACTION_VAT_INVOICE_DELETED: "נמחקה חשבונית מע״מ",
}

_ACTIVITY_TYPES = {
    entity_action(ENTITY_ANNUAL_REPORT, ACTION_CREATED): "created",
    entity_action(ENTITY_CHARGE, ACTION_CREATED): "created",
    entity_action(ENTITY_CLIENT, ACTION_CREATED): "created",
    ACTION_CHARGE_ISSUED: "charge",
    ACTION_CHARGE_PAID: "done",
    entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED): "done",
    entity_action(ENTITY_CHARGE, ACTION_STATUS_CHANGED): "done",
    entity_action(ENTITY_CLIENT, ACTION_STATUS_CHANGED): "done",
    entity_action(ENTITY_ANNUAL_REPORT, ACTION_UPDATED): "updated",
    entity_action(ENTITY_CHARGE, ACTION_UPDATED): "updated",
    entity_action(ENTITY_CLIENT, ACTION_UPDATED): "updated",
    ACTION_INCOME_ADDED: "created",
    ACTION_INCOME_UPDATED: "updated",
    ACTION_INCOME_DELETED: "updated",
    ACTION_EXPENSE_ADDED: "created",
    ACTION_EXPENSE_UPDATED: "updated",
    ACTION_EXPENSE_DELETED: "updated",
    ACTION_BINDER_CREATED: "created",
    ACTION_BINDER_MATERIAL_RECEIVED: "updated",
    ACTION_BINDER_MARKED_FULL: "updated",
    ACTION_BINDER_REOPENED: "updated",
    # ready-for-handover is the binder "done" signal (preserved from the legacy branch).
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER: "done",
    ACTION_BINDER_REVERTED_READY: "updated",
    ACTION_BINDER_HANDED_OVER: "done",
    ACTION_BINDER_INTAKE_UPDATED: "updated",
    ACTION_VAT_WORK_ITEM_CREATED: "created",
    ACTION_VAT_WORK_ITEM_STATUS_CHANGED: "done",
    ACTION_VAT_WORK_ITEM_FILED: "done",
    ACTION_VAT_WORK_ITEM_AMOUNT_OVERRIDDEN: "updated",
    ACTION_VAT_WORK_ITEM_UPDATED: "updated",
    ACTION_VAT_WORK_ITEM_DELETED: "updated",
    ACTION_VAT_INVOICE_CREATED: "created",
    ACTION_VAT_INVOICE_UPDATED: "updated",
    ACTION_VAT_INVOICE_AMOUNT_CHANGED: "updated",
    ACTION_VAT_INVOICE_DELETED: "updated",
}


class RecentActivityService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EntityAuditLogRepository(db)
        self.charge_repo = ChargeRepository(db)
        self.report_repo = AnnualReportRepository(db)

    def build(self) -> list[dict]:
        audit_rows = self.repo.list_recent(_ACTIVITY_FETCH_LIMIT)
        client_names = self._client_names(audit_rows)

        items = [
            (row.performed_at, self._serialize(row, client_names[row.id]))
            for row in audit_rows
            if row.id in client_names
        ]

        return [item for _, item in sorted(items, key=lambda pair: pair[0], reverse=True)][
            :_ACTIVITY_LIMIT
        ]

    def _serialize(self, row: EntityAuditLog, client_name: str) -> dict:
        return {
            "id": row.id,
            "date": self._format_date(row),
            "time": self._format_time(row),
            "label": self._label(row),
            "client_name": client_name,
            "href": self._href(row),
            "activity_type": _ACTIVITY_TYPES.get(row.action, "updated"),
        }

    def _client_names(self, audit_rows: list[EntityAuditLog]) -> dict[int, str]:
        charge_ids = {row.entity_id for row in audit_rows if row.entity_type == ENTITY_CHARGE}
        report_ids = {
            row.entity_id for row in audit_rows if row.entity_type == ENTITY_ANNUAL_REPORT
        }

        charges_by_id = self.charge_repo.get_by_ids(charge_ids)
        reports_by_id = self.report_repo.get_by_ids(report_ids)

        activity_client_ids: dict[int, int] = {}
        for row in audit_rows:
            if row.entity_type == ENTITY_CLIENT:
                activity_client_ids[row.id] = row.entity_id
            elif row.entity_type == ENTITY_CHARGE:
                charge = charges_by_id.get(row.entity_id)
                if charge:
                    activity_client_ids[row.id] = charge.client_record_id
            elif row.entity_type == ENTITY_ANNUAL_REPORT:
                report = reports_by_id.get(row.entity_id)
                if report:
                    activity_client_ids[row.id] = report.client_record_id
            elif row.entity_type == ENTITY_BINDER:
                # Binder lifecycle rows carry the owning client in metadata_json (§8).
                client_id = (row.metadata_json or {}).get("client_record_id")
                if client_id is not None:
                    activity_client_ids[row.id] = client_id
            elif isinstance(row.metadata_json, dict):
                # Generic audit rows for VAT and binder-intake carry immutable client
                # context in metadata_json; use it so new audit traffic does not
                # consume the recent window and then disappear from the dashboard.
                client_id = row.metadata_json.get("client_record_id")
                if client_id is not None:
                    activity_client_ids[row.id] = int(client_id)

        # The same client can appear in multiple audit rows; keep the bulk lookup compact.
        records = get_full_records_bulk(self.db, list(set(activity_client_ids.values())))
        return {
            activity_id: records[client_id]["full_name"]
            for activity_id, client_id in activity_client_ids.items()
            if client_id in records
        }

    def _label(self, row: EntityAuditLog) -> str:
        # Binder lifecycle notes are operational reason strings, not display labels —
        # use the action label table so the dashboard shows the lifecycle verb.
        if row.entity_type != ENTITY_BINDER:
            # `note` is only a human-readable label when it is free text. System-written
            # notes are key=value metadata (e.g. "source=vat_import") and must never leak
            # to the dashboard — fall through to the action/entity label table instead.
            if row.note and not row.note.startswith("{") and "=" not in row.note:
                return row.note

        label = _ACTION_LABELS.get(row.action)
        if label:
            return label

        entity = _ENTITY_LABELS.get(row.entity_type, "רשומה")
        return f"בוצעה פעולה ב{entity}"

    def _href(self, row: EntityAuditLog) -> str:
        linked_entities = {
            ENTITY_ANNUAL_REPORT: LinkedEntity.ANNUAL_REPORT,
            ENTITY_CHARGE: LinkedEntity.CHARGE,
            ENTITY_CLIENT: LinkedEntity.CLIENT,
            ENTITY_BINDER: LinkedEntity.BINDER,
            ENTITY_VAT_WORK_ITEM: LinkedEntity.VAT_WORK_ITEM,
        }
        if linked_entity := linked_entities.get(row.entity_type):
            return entity_route(linked_entity, row.entity_id)
        if row.entity_type == ENTITY_BINDER_INTAKE and isinstance(row.metadata_json, dict):
            binder_id = row.metadata_json.get("binder_id")
            return entity_route(LinkedEntity.BINDER, binder_id) if binder_id else "/binders"
        if row.entity_type == ENTITY_VAT_INVOICE and isinstance(row.metadata_json, dict):
            work_item_id = row.metadata_json.get("vat_work_item_id")
            return (
                entity_route(LinkedEntity.VAT_WORK_ITEM, work_item_id)
                if work_item_id
                else "/tax/vat"
            )
        return "/"

    def _timestamp(self, row: EntityAuditLog):
        timestamp = row.performed_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone()

    def _format_date(self, row: EntityAuditLog) -> str:
        return self._timestamp(row).strftime("%d.%m.%Y")

    def _format_time(self, row: EntityAuditLog) -> str:
        return self._timestamp(row).strftime("%H:%M")
