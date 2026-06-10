"""VAT workflow constants — status transitions and validation rules."""

from decimal import Decimal

from app.vat.models.vat_enums import VatWorkItemStatus

# Valid status transitions: from → set of allowed next statuses
VALID_TRANSITIONS: dict[VatWorkItemStatus, set[VatWorkItemStatus]] = {
    VatWorkItemStatus.PENDING_MATERIALS: {
        VatWorkItemStatus.MATERIAL_RECEIVED,
    },
    VatWorkItemStatus.MATERIAL_RECEIVED: {
        VatWorkItemStatus.PENDING_MATERIALS,  # send back if incomplete
        VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,
    },
    VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS: {
        VatWorkItemStatus.READY_FOR_REVIEW,
        VatWorkItemStatus.MATERIAL_RECEIVED,  # rollback
    },
    VatWorkItemStatus.READY_FOR_REVIEW: {
        VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,  # advisor sends back for correction
        VatWorkItemStatus.FILED,
    },
    VatWorkItemStatus.FILED: set(),  # terminal — immutable
}

# Audit action labels
ACTION_WORK_ITEM_CREATED_PENDING = "work_item_created_pending"
ACTION_MATERIAL_RECEIVED = "material_received"
ACTION_STATUS_CHANGED = "status_changed"
ACTION_INVOICE_ADDED = "invoice_added"
ACTION_INVOICE_DELETED = "invoice_deleted"
ACTION_INVOICE_UPDATED = "invoice_updated"
ACTION_OVERRIDE = "vat_override"
ACTION_FILED = "filed"

CATEGORY_LABELS_SERVER: dict[str, str] = {
    "inventory": "קניית סחורה / מלאי",
    "office": "משרד",
    "travel": "נסיעות",
    "professional_services": "שירותים מקצועיים",
    "equipment": "ציוד",
    "rent": "שכירות",
    "salary": "שכר עבודה",
    "marketing": "שיווק",
    "vehicle": "רכב פרטי",
    "entertainment": "אירוח וכיבוד",
    "gifts": "מתנות",
    "fuel": "דלק",
    "vehicle_maintenance": "תחזוקת רכב",
    "vehicle_leasing": "ליסינג רכב",
    "maintenance": "תחזוקה",
    "utilities": "חשמל ומים",
    "communication": "תקשורת",
    "postage_and_shipping": "משלוחים ודואר",
    "bank_fees": "עמלות בנק",
    "tolls_and_parking": "חניה וכבישי אגרה",
    "mixed_expense": "הוצאה מעורבת",
    "vehicle_insurance": "ביטוח רכב",
    "insurance": "ביטוח",
    "municipal_tax": "ארנונה",
}

# Warn when annual turnover exceeds this fraction of the osek patur ceiling (non-blocking)
# Ceiling itself is read from the tax rules package per year
OSEK_PATUR_CEILING_WARNING_RATE: Decimal = Decimal("0.80")

__all__ = [
    "ACTION_FILED",
    "ACTION_INVOICE_ADDED",
    "ACTION_INVOICE_DELETED",
    "ACTION_INVOICE_UPDATED",
    "ACTION_MATERIAL_RECEIVED",
    "ACTION_WORK_ITEM_CREATED_PENDING",
    "ACTION_OVERRIDE",
    "ACTION_STATUS_CHANGED",
    "CATEGORY_LABELS_SERVER",
    "OSEK_PATUR_CEILING_WARNING_RATE",
    "VALID_TRANSITIONS",
]
