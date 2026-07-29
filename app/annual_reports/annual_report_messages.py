MISSING_TAX_CALCULATION_ISSUE = "חסר חישוב מס — יש לשמור את תוצאת חישוב המס"
TAX_CONFLICT_ERROR = "לא ניתן לשמור גם חוב מס וגם החזר מס בו-זמנית"
INCOMPLETE_REQUIRED_SCHEDULE_ISSUE = "נספח נדרש לא הושלם: {label}"
MISSING_REPORT_INCOME_ISSUE = "לא הוזנו נתוני הכנסה לדוח"
ANNUAL_REPORT_NOT_FOUND = "דוח שנתי {report_id} לא נמצא"
ANNUAL_REPORT_CLIENT_NOT_FOUND = "לקוח {client_record_id} לא נמצא"
INVALID_CLIENT_TYPE_ERROR = "סוג לקוח לא חוקי: '{client_type}'"
INVALID_DEADLINE_TYPE_ERROR = "סוג מועד אחרון לא חוקי: '{deadline_type}'"
ANNUAL_REPORT_ALREADY_EXISTS = "דוח שנתי ראשי ללקוח {client_record_id} לשנת מס {tax_year} כבר קיים (id={existing_id}, status={status})"
ANNUAL_REPORT_CREATED_NOTE = "הדוח נוצר. טופס: {form_type}, מועד אחרון: {filing_deadline}"
DEADLINE_NOT_SET = "לא נקבע"
INVALID_INCOME_SOURCE_ERROR = "סוג הכנסה לא חוקי: '{source_type}'"
INCOME_LINE_NOT_FOUND = "שורת הכנסה {line_id} לא נמצאה"
CLIENT_CLOSED_CREATE_WORK_ERROR = "לקוח סגור — לא ניתן ליצור עבודה חדשה"
CLIENT_FROZEN_CREATE_WORK_ERROR = "לקוח מוקפא — לא ניתן ליצור עבודה חדשה"
CLIENT_CLOSED_FINANCIAL_MUTATION_ERROR = "לקוח סגור — לא ניתן לשנות נתונים כספיים"
CLIENT_FROZEN_FINANCIAL_MUTATION_ERROR = "לקוח מוקפא — לא ניתן לשנות נתונים כספיים"
INVALID_EXPENSE_CATEGORY_ERROR = "קטגוריית הוצאה לא חוקית: '{category}'"
EXPENSE_LINE_NOT_FOUND = "שורת הוצאה {line_id} לא נמצאה"
REPORT_NOT_READY_FOR_SUBMISSION = "הדוח אינו מוכן להגשה: {issues}"
INVALID_ANNUAL_REPORT_STATUS = "סטטוס לא חוקי: '{new_status}'"
INVALID_STATUS_TRANSITION = (
    "לא ניתן לעבור מ-'{current_status}' ל-'{new_status}'. סטטוסים הבאים מותרים: {allowed}"
)
DEADLINE_UPDATED_NOTE = "המועד האחרון עודכן ל-{deadline_type}: {filing_deadline}"
CUSTOM_DEADLINE_LABEL = "מותאם אישית"
ANNEX_VALIDATION_ERROR = "נתוני הנספח אינם תקינים: {error}"
ANNEX_LINE_NOT_FOUND = "שורת נספח {line_id} לא נמצאה"
SCHEDULE_NOT_FOUND = "נספח '{schedule}' לא נמצא בדוח {report_id}"
INVALID_SCHEDULE_ERROR = "נספח לא חוקי: '{schedule}'"
UNSUPPORTED_TAX_YEAR_ERROR = "שנת מס {tax_year} אינה נתמכת. שנים נתמכות: {supported_years}"
AUTOPOPULATE_INVALID_STATUS = 'ניתן למלא נתוני מע"מ אוטומטית רק לדוח בשלבים הראשונים'
AUTOPOPULATE_LINES_ALREADY_EXIST = (
    "קיימים נתוני הכנסות/הוצאות בדוח. יש לשלוח force=true למחיקה ומילוי מחדש"
)
AUTOPOPULATE_AUDIT_ACTOR_REQUIRED = 'נדרש משתמש מבצע למילוי אוטומטי מנתוני מע"מ'
VAT_IMPORTED_BUSINESS_INCOME_DESCRIPTION = 'הכנסות עסקיות — יובא ממע"מ'
VAT_IMPORTED_EXPENSE_DESCRIPTION = '{category_label} — יובא ממע"מ'

EXPENSE_CATEGORY_LABELS: dict[str, str] = {
    "office_rent": "שכירות משרד",
    "professional_services": "שירותים מקצועיים",
    "salaries": "שכר עבודה",
    "depreciation": "פחת",
    "vehicle": "רכב",
    "marketing": "שיווק ופרסום",
    "insurance": "ביטוח",
    "communication": "תקשורת",
    "travel": "נסיעות",
    "training": "הכשרה מקצועית",
    "bank_fees": "עמלות בנק",
    "other": "אחר",
}
ANNUAL_DEADLINE_REMINDER_MESSAGE = "תזכורת: מועד מס בעוד {days_before} ימים ({due_date})"
CLIENT_FALLBACK_NAME = "לקוח #{client_record_id}"
