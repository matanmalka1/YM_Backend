from datetime import UTC

from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.audit.constants import (
    ACTION_CREATED,
    ACTION_ISSUED,
    ACTION_PAID,
    ACTION_STATUS_CHANGED,
    ACTION_UPDATED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
)
from app.audit.models.entity_audit_log import EntityAuditLog
from app.audit.repositories.entity_audit_log_repository import EntityAuditLogRepository
from app.binders.models.binder import BinderLocationStatus
from app.binders.models.binder_lifecycle_log import BinderLifecycleLog
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.repositories.binder_lifecycle_log_repository import BinderLifecycleLogRepository
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.repositories.client_record_read_repository import get_full_records_bulk

_ACTIVITY_LIMIT = 5
# Fetches more than displayed to allow merging audit + binder rows before trimming to _ACTIVITY_LIMIT.
_ACTIVITY_FETCH_LIMIT = 20

_ENTITY_LABELS = {
    ENTITY_ANNUAL_REPORT: "דוח שנתי",
    ENTITY_CHARGE: "חיוב",
    ENTITY_CLIENT: "לקוח",
}

_ACTION_LABELS = {
    ACTION_CREATED: {
        ENTITY_ANNUAL_REPORT: "נוצר דוח שנתי חדש",
        ENTITY_CHARGE: "נוצר חיוב חדש",
        ENTITY_CLIENT: "נוצר לקוח חדש",
    },
    ACTION_UPDATED: {
        ENTITY_ANNUAL_REPORT: "עודכן דוח שנתי",
        ENTITY_CHARGE: "עודכן חיוב",
        ENTITY_CLIENT: "עודכן לקוח",
    },
    ACTION_ISSUED: {ENTITY_CHARGE: "נפתח חיוב חדש"},
    ACTION_PAID: {ENTITY_CHARGE: "חיוב סומן כשולם"},
    ACTION_STATUS_CHANGED: {
        ENTITY_ANNUAL_REPORT: "עודכן סטטוס דוח שנתי",
        ENTITY_CHARGE: "עודכן סטטוס חיוב",
        ENTITY_CLIENT: "עודכן סטטוס לקוח",
    },
}

_ACTIVITY_TYPES = {
    ACTION_CREATED: "created",
    ACTION_ISSUED: "charge",
    ACTION_PAID: "done",
    ACTION_STATUS_CHANGED: "done",
    ACTION_UPDATED: "updated",
}


class RecentActivityService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EntityAuditLogRepository(db)
        self.charge_repo = ChargeRepository(db)
        self.report_repo = AnnualReportRepository(db)
        self.binder_repo = BinderRepository(db)
        self.binder_lifecycle_log_repo = BinderLifecycleLogRepository(db)

    def build(self) -> list[dict]:
        audit_rows = self.repo.list_recent(_ACTIVITY_FETCH_LIMIT)
        binder_rows = self.binder_lifecycle_log_repo.list_recent(_ACTIVITY_FETCH_LIMIT)
        client_names = self._client_names(audit_rows, binder_rows)

        items = [
            (row.performed_at, self._serialize(row, client_names[row.id]))
            for row in audit_rows
            if row.id in client_names
        ]
        items.extend(
            (
                row.changed_at,
                self._serialize_binder(row, client_names[f"binder:{row.id}"]),
            )
            for row in binder_rows
            if f"binder:{row.id}" in client_names
        )

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

    def _client_names(
        self, audit_rows: list[EntityAuditLog], binder_rows: list[BinderLifecycleLog]
    ) -> dict[int | str, str]:
        charge_ids = {row.entity_id for row in audit_rows if row.entity_type == ENTITY_CHARGE}
        report_ids = {
            row.entity_id for row in audit_rows if row.entity_type == ENTITY_ANNUAL_REPORT
        }
        binder_ids = {row.binder_id for row in binder_rows}

        charges_by_id = self.charge_repo.get_by_ids(charge_ids)
        reports_by_id = self.report_repo.get_by_ids(report_ids)
        binders_by_id = self.binder_repo.get_by_ids(binder_ids)

        activity_client_ids: dict[int | str, int] = {}
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

        for row in binder_rows:
            binder = binders_by_id.get(row.binder_id)
            if binder:
                activity_client_ids[f"binder:{row.id}"] = binder.client_record_id

        # The same client can appear in multiple audit rows; keep the bulk lookup compact.
        records = get_full_records_bulk(self.db, list(set(activity_client_ids.values())))
        return {
            activity_id: records[client_id]["full_name"]
            for activity_id, client_id in activity_client_ids.items()
            if client_id in records
        }

    def _serialize_binder(self, row: BinderLifecycleLog, client_name: str) -> dict:
        return {
            "id": -row.id,
            "date": self._format_date(row),
            "time": self._format_time(row),
            "label": self._binder_label(row),
            "client_name": client_name,
            "href": f"/binders?binder_id={row.binder_id}",
            "activity_type": "done"
            if row.new_value == BinderLocationStatus.READY_FOR_HANDOVER.value
            else "updated",
        }

    def _binder_label(self, row: BinderLifecycleLog) -> str:
        if row.field_name == "location_status":
            if row.new_value == BinderLocationStatus.READY_FOR_HANDOVER.value:
                return "קלסר מוכן למסירה"
            if row.new_value == BinderLocationStatus.HANDED_OVER.value:
                return "קלסר נמסר ללקוח"
            if row.new_value == BinderLocationStatus.IN_OFFICE.value:
                return "קלסר חזר לעבודה במשרד"
        return "עודכן מחזור חיי קלסר"

    def _label(self, row: EntityAuditLog) -> str:
        if row.note and not row.note.startswith("{"):
            return row.note

        label_by_entity = _ACTION_LABELS.get(row.action, {})
        if row.entity_type in label_by_entity:
            return label_by_entity[row.entity_type]

        entity = _ENTITY_LABELS.get(row.entity_type, "רשומה")
        return f"בוצעה פעולה ב{entity}"

    def _href(self, row: EntityAuditLog) -> str:
        if row.entity_type == ENTITY_ANNUAL_REPORT:
            return f"/tax/reports/{row.entity_id}"
        if row.entity_type == ENTITY_CHARGE:
            return f"/charges?charge_id={row.entity_id}"
        if row.entity_type == ENTITY_CLIENT:
            return f"/clients/{row.entity_id}"
        return "/"

    def _timestamp(self, row: EntityAuditLog | BinderLifecycleLog):
        timestamp = getattr(row, "performed_at", None) or row.changed_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone()

    def _format_date(self, row: EntityAuditLog | BinderLifecycleLog) -> str:
        return self._timestamp(row).strftime("%d.%m.%Y")

    def _format_time(self, row: EntityAuditLog | BinderLifecycleLog) -> str:
        return self._timestamp(row).strftime("%H:%M")
