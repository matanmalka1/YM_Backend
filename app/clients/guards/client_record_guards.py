from app.core.error_codes import ErrorCode
from app.core.exceptions import ConflictError


def assert_client_record_is_active(client_record) -> None:
    if client_record and getattr(client_record, "status", None) in ("closed", "frozen"):
        raise ConflictError(
            "לא ניתן לבצע את הפעולה על תיק לקוח סגור או מוקפא",
            ErrorCode.CLIENT_RECORD_CLOSED,
        )
