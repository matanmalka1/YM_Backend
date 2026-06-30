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

# VAT audit actions are now namespaced EntityAuditLog constants in
# app/audit/audit_constants.py (ACTION_VAT_WORK_ITEM_* / ACTION_VAT_INVOICE_*);
# the raw VAT-local strings were removed in the Phase 3 audit refactor.

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
    "CATEGORY_LABELS_SERVER",
    "OSEK_PATUR_CEILING_WARNING_RATE",
    "VALID_TRANSITIONS",
]
