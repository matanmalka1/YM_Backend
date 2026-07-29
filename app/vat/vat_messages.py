VAT_ASSIGNEE_REQUIRED = 'לא ניתן להגיש דוח מע"מ ללא נציג מוקצה (assigned_to)'
VAT_ITEM_NOT_FOUND = 'פריט עבודה {item_id} למע"מ לא נמצא'
VAT_CLIENT_NOT_FOUND = "לקוח {client_record_id} לא נמצא"
OVERRIDE_AMOUNT_MUST_BE_POSITIVE = "סכום דריסה חייב להיות חיובי"
OVERRIDE_JUSTIFICATION_REQUIRED = "נדרש נימוק כאשר מחליפים את הסכום"
FINAL_VAT_AMOUNT_REQUIRED = "סכום מע\u05f4מ סופי חייב להיות מוגדר"
VAT_FILED_ITEM_IMMUTABLE = 'לא ניתן לערוך פריט עבודה שלמע"מ שכבר הוגש'
VAT_INVALID_TRANSITION = "לא ניתן לעבור מ-{current_status} ל-{target_status}"
VAT_NEGATIVE_AMOUNT = 'הסכום של המע"מ לא יכול להיות שלילי'
VAT_NET_AMOUNT_POSITIVE_REQUIRED = "הסכום נטו חייב להיות חיובי"
VAT_EXPENSE_CATEGORY_REQUIRED = "חובה לציין קטגוריית הוצאה עבור חשבוניות הוצאה"
VAT_SUPPLIER_ID_REQUIRED = "חשבונית מס לתשומות חייבת לכלול מספר עוסק של הספק"
VAT_OSEK_PATUR_CEILING_EXCEEDED = (
    "תקרת עוסק פטור חרגה: סך מחזור {new_total:.2f} ₪ עולה על תקרה של {ceiling:.2f} ₪"
)
VAT_CLIENT_CLOSED_ADD_INVOICES = "לקוח זה סגור — לא ניתן להוסיף חשבוניות"
VAT_BUSINESS_ACTIVITY_WRONG_CLIENT = "פעילות עסקית זו אינה שייכת ללקוח של פריט העבודה"
VAT_BUSINESS_ACTIVITY_NOT_FOUND = "פעילות עסקית לא נמצאה"
VAT_INCOME_COUNTERPARTY_NAME = "הכנסות"
VAT_UNKNOWN_COUNTERPARTY_NAME = "לא ידוע"
VAT_INVOICE_NUMBER_CONFLICT = "מספר חשבונית '{invoice_number}' כבר קיים לתקופה ולסוג הזה"
VAT_AUTO_STATUS_CHANGE_ON_FIRST_INVOICE = "מעבר אוטומטי בעת הוספת חשבונית ראשונה"
VAT_ADD_INVOICE_INVALID_STATUS = "לא ניתן להוסיף חשבוניות לפריט עבודה במצב {status}"
VAT_INVOICE_NOT_FOUND_IN_WORK_ITEM = "החשבונית {invoice_id} לא נמצאה בפריט עבודה {item_id}"
VAT_READY_FOR_REVIEW_INVALID_STATUS = "לא ניתן לסמן מוכן לבדיקה מסטטוס {status}"
VAT_CORRECTION_NOTE_REQUIRED = "נדרש טקסט תיקון כאשר מחזירים את הפריט לתיקון"
VAT_CLIENT_EXEMPT = 'לקוח זה פטור ממע"מ ולא ניתן לפתוח עבורו דוח'
VAT_WORK_ITEM_CONFLICT = 'פריט עבודה למע"מ כבר קיים עבור לקוח {client_record_id} לתקופה {period}'
VAT_PENDING_MATERIALS_NOTE_REQUIRED = (
    "pending_materials_note: נדרש תיאור החומרים כאשר הפריט מסומן כמצב המתנה"
)
VAT_MATERIALS_COMPLETE_INVALID_STATUS = "לא ניתן לסמן חומרים כהושלמו מסטטוס {status}"
