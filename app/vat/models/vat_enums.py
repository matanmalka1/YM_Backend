"""VAT Report enums."""

from enum import Enum as PyEnum


class VatWorkItemStatus(str, PyEnum):
    PENDING_MATERIALS = "pending_materials"
    MATERIAL_RECEIVED = "material_received"
    DATA_ENTRY_IN_PROGRESS = "data_entry_in_progress"
    READY_FOR_REVIEW = "ready_for_review"
    FILED = "filed"
    CANCELED = "canceled"


class CounterpartyIdType(str, PyEnum):
    IL_BUSINESS = "il_business"  # עוסק מורשה / ח"פ — ספרת ביקורת ישראלית
    IL_PERSONAL = "il_personal"  # ת"ז ישראלית — ספרת ביקורת ישראלית
    FOREIGN = "foreign"  # תושב חוץ — ללא ספרת ביקורת
    ANONYMOUS = "anonymous"  # 999999999 — קופה רושמת / לא ידוע


class InvoiceType(str, PyEnum):
    INCOME = "income"
    EXPENSE = "expense"


class ExpenseCategory(str, PyEnum):
    """VAT invoice source categories used for VAT deduction and data-entry classification.

    These are granular operational categories captured at invoice-entry time.
    Do not reuse for annual report expense lines — those use ExpenseCategoryType.
    Each value is mapped to an ExpenseCategoryType via _VAT_TO_ANNUAL in
    backend/app/annual_reports/services/vat_import_service.py. Any new value
    added here must also be added to that mapping.
    """

    INVENTORY = "inventory"
    OFFICE = "office"
    TRAVEL = "travel"
    PROFESSIONAL_SERVICES = "professional_services"
    EQUIPMENT = "equipment"
    RENT = "rent"
    SALARY = "salary"
    MARKETING = "marketing"
    VEHICLE = "vehicle"  # רכב כללי
    FUEL = "fuel"  # דלק — 2/3 קיזוז
    VEHICLE_MAINTENANCE = "vehicle_maintenance"  # תיקונים וטיפולים
    VEHICLE_INSURANCE = "vehicle_insurance"  # ביטוח רכב
    VEHICLE_LEASING = "vehicle_leasing"  # ליסינג
    TOLLS_AND_PARKING = "tolls_and_parking"  # כביש 6, חניה
    ENTERTAINMENT = "entertainment"
    GIFTS = "gifts"
    COMMUNICATION = "communication"
    INSURANCE = "insurance"
    MAINTENANCE = "maintenance"
    MUNICIPAL_TAX = "municipal_tax"
    UTILITIES = "utilities"
    POSTAGE_AND_SHIPPING = "postage_and_shipping"
    BANK_FEES = "bank_fees"
    MIXED_EXPENSE = "mixed_expense"


class VatRateType(str, PyEnum):
    STANDARD = "standard"
    EXEMPT = "exempt"
    ZERO_RATE = "zero_rate"


class DocumentType(str, PyEnum):
    TAX_INVOICE = "tax_invoice"
    TRANSACTION_INVOICE = "transaction_invoice"
    RECEIPT = "receipt"
    CONSOLIDATED = "consolidated"
    SELF_INVOICE = "self_invoice"
    CREDIT_NOTE = "credit_note"


__all__ = [
    "DocumentType",
    "ExpenseCategory",
    "InvoiceType",
    "VatRateType",
    "VatWorkItemStatus",
]
