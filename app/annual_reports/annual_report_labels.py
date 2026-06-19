"""Centralised Hebrew display labels for annual report domain."""

SCHEDULE_LABELS: dict[str, str] = {
    "schedule_a": "נספח א — הכנסה מעסק או משלח יד",
    "schedule_b": "נספח ב — הכנסות מרכוש / שכירות / ריבית / דיבידנד / עסקאות אקראיות",
    "schedule_gimmel": "נספח ג — רווח הון מניירות ערך סחירים",
    "schedule_dalet": 'נספח ד — הכנסות מחו"ל ומס זר',
    "form_150": "טופס 150 — החזקה בחבר בני אדם תושב חוץ",
    "form_1504": "טופס 1504 — שותף בשותפות",
    "form_6111": "טופס 6111 — קידוד דוחות כספיים",
    "form_1344": "טופס 1344 — דיווח על הפסדים רלוונטיים",
    "form_1399": "טופס 1399 — הודעה על מכירת נכס ורווח הון",
    "form_1350": "טופס 1350 — משיכות בעל מניות מהותי",
    "form_1327": "טופס 1327 — דוח נאמנות",
    "form_1342": "טופס 1342 — פירוט נכסים לפחת",
    "form_1343": "טופס 1343 — ניכוי נוסף בשל פחת",
    "form_1348": "טופס 1348 — טענת אי-תושבות ישראל",
    "form_858": "טופס 858 — יחידות השתתפות בשותפות נפט",
}

INCOME_LABELS: dict[str, str] = {
    "business": "הכנסות עסק",
    "salary": "שכר עבודה",
    "interest": "ריבית",
    "dividends": "דיבידנד",
    "capital_gains": "רווח הון",
    "rental": "שכירות",
    "foreign": 'הכנסה מחו"ל',
    "pension": "קצבה",
    "other": "אחר",
}

EXPENSE_LABELS: dict[str, str] = {
    "office_rent": 'שכ"ד משרד',
    "professional_services": "שירותים מקצועיים",
    "salaries": "שכר עובדים",
    "depreciation": "פחת",
    "vehicle": "רכב",
    "marketing": "שיווק",
    "insurance": "ביטוח",
    "communication": "תקשורת",
    "travel": "נסיעות",
    "training": "הכשרה",
    "bank_fees": "עמלות בנק",
    "other": "אחר",
}

CLIENT_TYPE_LABELS: dict[str, str] = {
    "individual": "יחיד (1301)",
    "self_employed": "עצמאי (1301 + נספח א')",
    "corporation": "חברה (1214, ובמקרים רלוונטיים גם 6111)",
    "public_institution": 'מלכ"ר / מוסד ציבורי (1215)',
    "partnership": "שותף בשותפות (1301 ובדרך כלל 1504)",
    "control_holder": "בעל שליטה (1301, מועד הגשה של חברות)",
    "exempt_dealer": "עוסק פטור / זעיר החייב בדוח מלא (1301; 0135 אינו דוח ראשי בדומיין זה)",
}

STATUS_LABELS: dict[str, str] = {
    "not_started": "טרם החל",
    "collecting_docs": "איסוף מסמכים",
    "in_preparation": "בהכנה",
    "pending_client": "ממתין ללקוח",
    "submitted": "הוגש",
    "closed": "סגור",
    "canceled": "בוטל",
}

__all__ = [
    "SCHEDULE_LABELS",
    "INCOME_LABELS",
    "EXPENSE_LABELS",
    "CLIENT_TYPE_LABELS",
    "STATUS_LABELS",
]
