from __future__ import annotations

FALLBACK_CLIENT_NAME = "לקוח/ה"
DEFAULT_NOTIFICATION_SUBJECT = "הודעה ממשרדנו"

# subject + body per trigger
TEMPLATES: dict[str, dict[str, str]] = {
    "binder_ready_for_handover": {
        "subject": "הקלסר שלך מוכן למסירה",
        "body": (
            "שלום {client_name},\n\n"
            "קלסר מספר {binder_number} מוכן למסירה מהמשרד.\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "binder_missing_documents": {
        "subject": "מסמכים חסרים בקלסר שלך",
        "body": (
            "שלום {client_name},\n\n"
            "חסרים מסמכים בקלסר שלך. נא לשלוח את המסמכים הנדרשים בהקדם.\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "binder_general_reminder": {
        "subject": "תזכורת בנוגע לקלסר שלך",
        "body": ("שלום {client_name},\n\n{message}\n\nבברכה,\n{sender_name}\n{office_name}"),
    },
    "invoice_issued": {
        "subject": "חשבונית חדשה הונפקה עבורך",
        "body": (
            "שלום {client_name},\n\n"
            "חשבונית על סך {charge_amount} ₪ הונפקה עבורך.\n"
            "תיאור: {charge_description}\n"
            "תאריך הנפקה: {issued_at}\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "payment_reminder": {
        "subject": "תזכורת לתשלום",
        "body": (
            "שלום {client_name},\n\n"
            "תזכורת: קיים חיוב פתוח על סך {charge_amount} ₪ הממתין לתשלום.\n"
            "תיאור: {charge_description}\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "vat_documents_reminder": {
        "subject": "תזכורת — העברת מסמכי מע״מ",
        "body": (
            "שלום {client_name},\n\n"
            "תזכורת: יש להעביר את מסמכי מע״מ לתקופה {period} בהקדם.\n"
            "מועד הגשה: {deadline}{deadline_note}\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "annual_report_documents_request": {
        "subject": "בקשה להעברת מסמכים לדוח שנתי",
        "body": (
            "שלום {client_name},\n\n"
            "לצורך הכנת הדוח השנתי לשנת {tax_year}, נא להעביר את המסמכים הנדרשים.\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "annual_report_client_reminder": {
        "subject": "תזכורת — אישור דוח שנתי",
        "body": (
            "שלום {client_name},\n\n"
            "הדוח השנתי לשנת {tax_year} ממתין לאישורך.\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "signature_request_sent": {
        "subject": "בקשה לחתימה",
        "body": (
            "שלום {client_name},\n\n"
            "נשלחה אליך בקשה לחתימה על: {document_title}\n\n"
            "לחתימה: {signature_link}\n\n"
            "הבקשה בתוקף עד: {expires_at}\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "signature_request_reminder": {
        "subject": "תזכורת — בקשה לחתימה ממתינה",
        "body": (
            "שלום {client_name},\n\n"
            "תזכורת: בקשה לחתימה על {document_title} עדיין ממתינה לאישורך.\n\n"
            "לחתימה: {signature_link}\n\n"
            "הבקשה בתוקף עד: {expires_at}\n\n"
            "בברכה,\n{sender_name}\n{office_name}"
        ),
    },
    "client_missing_information": {
        "subject": "פרטים חסרים בתיק שלך",
        "body": ("שלום {client_name},\n\n{message}\n\nבברכה,\n{sender_name}\n{office_name}"),
    },
    "client_documents_request": {
        "subject": "בקשה להעברת מסמכים",
        "body": ("שלום {client_name},\n\n{message}\n\nבברכה,\n{sender_name}\n{office_name}"),
    },
    "client_general_message": {
        "subject": "הודעה ממשרדנו",
        "body": ("שלום {client_name},\n\n{message}\n\nבברכה,\n{sender_name}\n{office_name}"),
    },
}

# Variables that must be present in context (fetched from DB by context resolver).
# Base vars (client_name, sender_name, office_name) are always resolved separately.
REQUIRED_CONTEXT_VARS: dict[str, set[str]] = {
    "binder_ready_for_handover": {"binder_number"},
    "binder_missing_documents": set(),
    "binder_general_reminder": {"message"},
    "invoice_issued": {"charge_amount", "charge_description", "issued_at"},
    "payment_reminder": {"charge_amount", "charge_description"},
    "vat_documents_reminder": {"period", "deadline", "deadline_note"},
    "annual_report_documents_request": {"tax_year"},
    "annual_report_client_reminder": {"tax_year"},
    "signature_request_sent": {"document_title", "signature_link", "expires_at"},
    "signature_request_reminder": {"document_title", "signature_link", "expires_at"},
    "client_missing_information": {"message"},
    "client_documents_request": {"message"},
    "client_general_message": {"message"},
}
