CLIENT_ID_NUMBER_EXISTS = "לקוח עם מספר ת.ז. {id_number} כבר קיים במערכת"
CLIENT_ID_NUMBER_DELETED = "לקוח עם מספר ת.ז. {id_number} קיים במערכת אך נמחק"
CLIENT_ID_NUMBER_CONFLICT = "לקוח עם מספר ת.ז. {id_number} כבר קיים"
CLIENT_NOT_FOUND = "לקוח {client_id} לא נמצא"
CLIENT_NOT_DELETED = "לקוח זה אינו מחוק"
CLIENT_ID_NUMBER_ACTIVE_EXISTS = "לקוח עם מספר ת.ז. {id_number} כבר קיים ופעיל במערכת"
CLIENT_OFFICE_NUMBER_CONFLICT = "שגיאה בהקצאת מספר לקוח פנימי — נסה שוב"

# Client-eligibility block. One error code (CLIENT_RECORD.CLOSED) across every
# domain, but two messages: the advisor still has to know which state blocked them,
# because a frozen client can be thawed and a closed one generally cannot.
CLIENT_RECORD_CLOSED_ACTION = "לא ניתן לבצע את הפעולה על תיק לקוח סגור"
CLIENT_RECORD_FROZEN_ACTION = "לא ניתן לבצע את הפעולה על תיק לקוח מוקפא"
