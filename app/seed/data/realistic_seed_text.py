from __future__ import annotations

from app.binders.models.binder_intake_material import MaterialType
from app.charges.models.charge import ChargeType
from app.documents.permanent_documents.models.permanent_document import PermanentDocumentType
from app.signature_requests.models.signature_request import SignatureRequestType
from app.vat.models.vat_enums import ExpenseCategory, InvoiceType

STAFF_DIRECTORY = [
    {"name": "דנה לוי", "role": "ADVISOR"},
    {"name": "אמיר כהן", "role": "ADVISOR"},
    {"name": "נטע מזרחי", "role": "ADVISOR"},
    {"name": "הילה ברק", "role": "SECRETARY"},
    {"name": "שי אברמוב", "role": "SECRETARY"},
    {"name": "מיכל פרידמן", "role": "SECRETARY"},
    {"name": "יואב מלכה", "role": "ADVISOR"},
    {"name": "רוני הראל", "role": "SECRETARY"},
]

CHARGE_TYPE_DETAILS = {
    ChargeType.MONTHLY_RETAINER: ("שכר טרחה חודשי עבור הנהלת חשבונות", 850, 3200),
    ChargeType.ANNUAL_REPORT_FEE: ("הכנת דוח שנתי והגשה לרשות המסים", 1800, 6500),
    ChargeType.VAT_FILING_FEE: ('טיפול בדיווח מע"מ תקופתי', 450, 1800),
    ChargeType.REPRESENTATION_FEE: ("ייצוג בדיון מול רשות המסים", 1200, 7500),
    ChargeType.CONSULTATION_FEE: ("פגישת ייעוץ מקצועית חד פעמית", 650, 2800),
    ChargeType.OTHER: ("חיוב חריג שאושר מול הלקוח", 300, 2200),
}

DOCUMENT_TYPE_DETAILS = {
    PermanentDocumentType.ID_COPY: ("צילום תעודת זהות", "teudat_zehut.pdf"),
    PermanentDocumentType.POWER_OF_ATTORNEY: ("ייפוי כוח לרשות המסים", "yipui_koach.pdf"),
    PermanentDocumentType.ENGAGEMENT_AGREEMENT: ("הסכם התקשרות חתום", "heskem_hitkashrut.pdf"),
    PermanentDocumentType.TAX_FORM: ("טופס מס תקופתי", "tofes_mas.pdf"),
    PermanentDocumentType.RECEIPT: ("קבלה מספק", "kabala.pdf"),
    PermanentDocumentType.INVOICE_DOC: ("חשבונית מס", "heshbonit_mas.pdf"),
    PermanentDocumentType.BANK_APPROVAL: ("אישור ניהול חשבון בנק", "ishur_bank.pdf"),
    PermanentDocumentType.WITHHOLDING_CERTIFICATE: (
        "אישור ניכוי מס במקור",
        "nikui_mas_bamakor.pdf",
    ),
    PermanentDocumentType.NII_APPROVAL: ("אישור ביטוח לאומי", "bituah_leumi.pdf"),
    PermanentDocumentType.OTHER: ("מסמך תומך נוסף", "mismach_tomech.pdf"),
}

MATERIAL_DESCRIPTIONS = {
    MaterialType.VAT: 'חשבוניות הכנסה והוצאה לדיווח מע"מ',
    MaterialType.INCOME_TAX: "פנקס מקדמות ואישורי ניכוי מס במקור",
    MaterialType.ANNUAL_REPORT: "מסמכים לדוח שנתי כולל אישורי 106 ו-867",
    MaterialType.SALARY: "תלושי שכר וטופסי 102",
    MaterialType.BOOKKEEPING: "דפי בנק, חשבוניות ספקים וקבלות",
    MaterialType.NATIONAL_INSURANCE: "אישורי ביטוח לאומי ופנקס תשלומים",
    MaterialType.CAPITAL_DECLARATION: "מסמכים להצהרת הון",
    MaterialType.PENSION_AND_INSURANCE: "אישורי הפקדה לפנסיה וביטוח",
    MaterialType.CORPORATE_DOCS: "פרוטוקולים, תעודת התאגדות ומורשי חתימה",
    MaterialType.TAX_ASSESSMENT: "שומות, החלטות ודרישות מרשות המסים",
    MaterialType.OTHER: "חומר נוסף שהתקבל מהלקוח",
}

VAT_COUNTERPARTY_DETAILS = {
    ExpenseCategory.INVENTORY: ('לב השרון שיווק והפצה בע"מ', 1200, 24000),
    ExpenseCategory.OFFICE: ('אלון ציוד משרדי בע"מ', 150, 4800),
    ExpenseCategory.PROFESSIONAL_SERVICES: ("משרד עורכי דין רוזן", 900, 15000),
    ExpenseCategory.EQUIPMENT: ('אפק מערכות מחשוב בע"מ', 1800, 30000),
    ExpenseCategory.RENT: ('לב העיר נכסים בע"מ', 3500, 18000),
    ExpenseCategory.MARKETING: ('פסיפס פרסום ודיגיטל בע"מ', 700, 22000),
    ExpenseCategory.FUEL: ("דלק ישראל", 250, 3500),
    ExpenseCategory.COMMUNICATION: ("בזק עסקים", 180, 1800),
    ExpenseCategory.BANK_FEES: ("בנק לאומי", 40, 900),
    ExpenseCategory.POSTAGE_AND_SHIPPING: ("י. כהן שירותי הובלה", 250, 6500),
}

VAT_INCOME_COUNTERPARTIES = [
    ("לקוח קמעונאי מקומי", 800, 9000),
    ('קו חוף ייבוא וסחר בע"מ', 4500, 45000),
    ('פסגה הנדסה וניהול בע"מ', 3000, 38000),
    ('רימון מזון ואירוח בע"מ', 1200, 18000),
]

INCOME_DESCRIPTIONS = {
    "salary": "הכנסות שכר לפי טופס 106",
    "business": "הכנסות עסקיות לפי הנהלת חשבונות",
    "interest": "ריבית מפיקדונות ואישורי בנק",
    "dividends": "דיבידנד לפי אישורי ניכוי מס",
    "capital_gains": "רווחי הון לפי טופסי 867",
    "rental": "הכנסות שכירות מנכס",
    "foreign": 'הכנסה מחו"ל לפי אישור מס זר',
}

EXPENSE_DESCRIPTIONS = {
    "office_rent": "שכירות משרד לפי הסכם ותשלומים",
    "professional_services": "שירותים מקצועיים חיצוניים",
    "insurance": "ביטוח עסקי",
    "communication": "טלפון, אינטרנט ושירותי תקשורת",
    "vehicle": "הוצאות רכב מוכרות חלקית",
    "marketing": "פרסום וקידום עסקי",
    "bank_fees": "עמלות בנק",
    "other": "הוצאה עסקית נוספת לבדיקה",
}

SIGNATURE_COPY = {
    SignatureRequestType.ENGAGEMENT_AGREEMENT: (
        "חתימה על הסכם התקשרות",
        "נא לאשר את תנאי ההתקשרות והשירותים השוטפים לשנה הקרובה",
    ),
    SignatureRequestType.ANNUAL_REPORT_APPROVAL: (
        "אישור דוח שנתי לפני הגשה",
        "נא לעבור על תקציר הדוח השנתי ולאשר הגשה לרשות המסים",
    ),
    SignatureRequestType.POWER_OF_ATTORNEY: (
        "חתימה על ייפוי כוח",
        "נא לחתום על ייפוי כוח כדי שנוכל לטפל בפניות מול הרשויות",
    ),
    SignatureRequestType.VAT_RETURN_APPROVAL: (
        'אישור דוח מע"מ תקופתי',
        "נא לאשר את סכום הדיווח לפני שידור הדוח במערכת",
    ),
    SignatureRequestType.CUSTOM: (
        "חתימה על מסמך לקוח",
        "נא לעבור על המסמך המצורף ולאשר בחתימה דיגיטלית",
    ),
}

INVOICE_TYPE_LABELS = {
    InvoiceType.INCOME: "הכנסה",
    InvoiceType.EXPENSE: "הוצאה",
}
