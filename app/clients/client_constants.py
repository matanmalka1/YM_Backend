from app.annual_reports.models.annual_report_enums import ClientAnnualFilingType
from app.common.enums import AdvancePaymentFrequency, EntityType, VatType

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_CLIENT_IMPORT_UPLOAD_SIZE = 10 * 1024 * 1024

CLIENT_EXPORT_COLUMNS = [
    ("id", "ID"),
    ("full_name", "Full Name"),
    ("id_number", "ID Number"),
    ("phone", "Phone"),
    ("email", "Email"),
    ("address_street", "Street"),
    ("address_city", "City"),
    ("notes", "Notes"),
]

CLIENT_TEMPLATE_COLUMNS = [
    ("full_name", "Full Name"),
    ("business_name", "Business Name"),
    ("id_number", "ID Number"),
    ("phone", "Phone (optional)"),
    ("email", "Email (optional)"),
    ("entity_type", "Entity Type (optional)"),
    ("vat_reporting_frequency", "VAT Frequency (optional)"),
    ("advance_payment_frequency", "Advance Payment Frequency (optional)"),
]

CLIENT_TEMPLATE_SAMPLE_ROW = [
    "יוסי כהן",
    "יוסי כהן ייעוץ",
    "123456789",
    "0501234567",
    "yossi@example.com",
    "osek_murshe",
    "bimonthly",
    "bimonthly",
]
CLIENT_EXCEL_SHEET_TITLE = "Clients"
CLIENT_EXCEL_FREEZE_PANES = "A2"
CLIENT_IMPORT_DEFAULT_ENTITY_TYPE = EntityType.OSEK_MURSHE
CLIENT_IMPORT_DEFAULT_VAT_REPORTING_FREQUENCY = VatType.BIMONTHLY
CLIENT_IMPORT_DEFAULT_ADVANCE_PAYMENT_FREQUENCY = AdvancePaymentFrequency.BIMONTHLY

CLIENT_OBLIGATION_NEXT_YEAR_START_MONTH = 10
CLIENT_OBLIGATION_TRIGGER_FIELDS = frozenset(
    {
        "entity_type",
        "vat_reporting_frequency",
        "advance_payment_frequency",
    }
)
SUPPORTED_CREATE_ENTITY_TYPES = frozenset(
    {
        EntityType.OSEK_PATUR,
        EntityType.OSEK_MURSHE,
        EntityType.COMPANY_LTD,
    }
)

UNSUPPORTED_EMPLOYEE_CREATE_ERROR = "פתיחת לקוח מסוג שכיר אינה נתמכת במערכת"
CONFLICTING_ID_NUMBER_TYPE_ERROR = "סוג המזהה שסופק אינו תואם לסוג הישות"
PATUR_MANUAL_VAT_FREQUENCY_ERROR = 'אין להזין תדירות דיווח מע"מ עבור עוסק פטור'
SYSTEM_VAT_EXEMPT_CEILING_ERROR = 'תקרת פטור מע"מ נקבעת על ידי המערכת ואינה ניתנת להזנה ידנית'
EDIT_VAT_EXEMPT_CEILING_ERROR = 'תקרת פטור מע"מ נקבעת על ידי המערכת ואינה ניתנת לעריכה ידנית'
NON_PATUR_VAT_EXEMPT_CEILING_ERROR = 'תקרת פטור מע"מ מותרת לעוסק פטור בלבד'
VAT_FREQUENCY_REQUIRED_ERROR = 'יש לציין תדירות דיווח מע"מ עבור עוסק/חברה'
COMPANY_EXEMPT_VAT_ERROR = 'חברה בע"מ אינה יכולה להיות מוגדרת כפטורה ממע"מ'
COMPANY_CORPORATION_ID_ERROR = 'חברה בע"מ חייבת להיווצר עם ח.פ'
ADVANCE_PAYMENT_FREQUENCY_REQUIRED_ERROR = "יש לציין תדירות מקדמות מס הכנסה"

ENTITY_TYPE_TO_REPORT_CLIENT_TYPE: dict[EntityType | None, ClientAnnualFilingType] = {
    EntityType.OSEK_PATUR: ClientAnnualFilingType.EXEMPT_DEALER,
    EntityType.OSEK_MURSHE: ClientAnnualFilingType.SELF_EMPLOYED,
    EntityType.COMPANY_LTD: ClientAnnualFilingType.CORPORATION,
    EntityType.EMPLOYEE: ClientAnnualFilingType.INDIVIDUAL,
    None: ClientAnnualFilingType.INDIVIDUAL,
}
