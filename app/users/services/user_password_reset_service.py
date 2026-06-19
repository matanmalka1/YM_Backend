import hashlib
import html as html_lib
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.core.logging_config import get_logger
from app.infrastructure.notifications import EmailChannel
from app.users.repositories.user_password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from app.users.repositories.user_repository import UserRepository
from app.users.services.user_auth_service import AuthService
from app.users.services.user_management_policies import validate_password
from app.utils.time_utils import utcnow

logger = get_logger(__name__)

_FORGOT_MESSAGE = "אם קיים משתמש עם האימייל הזה, נשלחו הוראות לאיפוס סיסמה"
_RESET_MESSAGE = "הסיסמה אופסה בהצלחה"
_INVALID_TOKEN_MESSAGE = "קישור איפוס הסיסמה אינו תקין או שפג תוקפו"


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class PasswordResetService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.token_repo = PasswordResetTokenRepository(db)
        self.email_channel = EmailChannel(
            enabled=settings.NOTIFICATIONS_ENABLED,
            api_key=settings.BREVO_API_KEY,
            api_url=settings.BREVO_API_URL,
            from_address=settings.EMAIL_FROM_ADDRESS,
            from_name=settings.EMAIL_FROM_NAME,
        )

    def request_password_reset(
        self,
        email: str,
        *,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> str:
        normalized_email = email.strip().lower()
        user = self.user_repo.get_by_email(normalized_email)
        if user is None or not user.is_active:
            return _FORGOT_MESSAGE

        self.token_repo.invalidate_unused_tokens_for_user(user.id)

        raw_token = secrets.token_urlsafe(32)
        self.token_repo.create(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=utcnow() + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            requested_ip=requested_ip,
            user_agent=user_agent,
        )
        self.db.commit()

        reset_url = f"{settings.FRONTEND_PASSWORD_RESET_URL}?token={raw_token}"
        if settings.PASSWORD_RESET_DEV_LOG:
            logger.info("[DEV ONLY] Password reset URL for %s: %s", normalized_email, reset_url)

        plain_text = (
            f"שלום {user.full_name},\n\n"
            "התקבלה בקשה לאיפוס הסיסמה שלך.\n"
            f"לאיפוס הסיסמה יש להיכנס לקישור הבא: {reset_url}\n\n"
            f"הקישור תקף למשך {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} דקות.\n"
            "אם לא ביקשת לאפס סיסמה, אפשר להתעלם מההודעה."
        )
        html_content = _build_reset_email_html(
            full_name=user.full_name,
            reset_url=reset_url,
            expires_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
            from_name=settings.EMAIL_FROM_NAME,
        )
        ok, error = self.email_channel.send_html(
            user.email,
            html_content=html_content,
            plain_text=plain_text,
            subject="איפוס סיסמה | מערכת ניהול תיקים",
        )
        if not ok:
            logger.error("Password reset email failed for %s: %s", normalized_email, error)

        return _FORGOT_MESSAGE

    def reset_password(self, raw_token: str, new_password: str) -> str:
        validate_password(new_password)
        token_record = self.token_repo.get_valid_by_token_hash(_hash_token(raw_token))
        if token_record is None:
            raise AppError(_INVALID_TOKEN_MESSAGE, ErrorCode.AUTH_INVALID_PASSWORD_RESET_TOKEN, 400)

        user = self.user_repo.get_by_id(token_record.user_id)
        if user is None or not user.is_active:
            raise AppError(_INVALID_TOKEN_MESSAGE, ErrorCode.AUTH_INVALID_PASSWORD_RESET_TOKEN, 400)

        if not self.token_repo.mark_used(token_record.id):
            raise AppError(_INVALID_TOKEN_MESSAGE, ErrorCode.AUTH_INVALID_PASSWORD_RESET_TOKEN, 400)

        user.password_hash = AuthService.hash_password(new_password)
        user.token_version += 1
        self.db.commit()
        return _RESET_MESSAGE


def _build_reset_email_html(
    *,
    full_name: str,
    reset_url: str,
    expires_minutes: int,
    from_name: str,
) -> str:
    safe_name = html_lib.escape(full_name)
    safe_url = html_lib.escape(reset_url)
    safe_from = html_lib.escape(from_name)
    safe_expires = html_lib.escape(str(expires_minutes))

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>איפוס סיסמה</title>
</head>
<body style="margin:0;padding:0;background:#F4F4F5;font-family:Arial,sans-serif;direction:rtl;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F4F5;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:#1E293B;padding:28px 40px;text-align:right;">
              <span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:-0.3px;">{safe_from}</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;text-align:right;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#0F172A;">איפוס סיסמה</p>
              <p style="margin:0 0 28px;font-size:15px;color:#64748B;">שלום {safe_name},</p>

              <p style="margin:0 0 28px;font-size:15px;color:#334155;line-height:1.7;">
                התקבלה בקשה לאיפוס הסיסמה שלך.<br>
                לחץ על הכפתור הבא כדי לבחור סיסמה חדשה:
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
                <tr>
                  <td style="background:#1E293B;border-radius:8px;">
                    <a href="{safe_url}"
                       style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;letter-spacing:-0.2px;">
                      איפוס סיסמה
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 6px;font-size:13px;color:#94A3B8;">
                הקישור תקף למשך <strong>{safe_expires} דקות</strong>.
              </p>
              <p style="margin:0;font-size:13px;color:#94A3B8;">
                אם לא ביקשת לאפס סיסמה — אפשר להתעלם מהודעה זו.
              </p>
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:0 40px;">
              <hr style="border:none;border-top:1px solid #E2E8F0;margin:0;">
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px;text-align:right;">
              <p style="margin:0;font-size:12px;color:#CBD5E1;">
                הודעה זו נשלחה אוטומטית ממערכת ניהול התיקים של {safe_from}. אין להשיב להודעה זו.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
