from __future__ import annotations

import re

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.core.logging_config import get_logger
from app.notifications.models.notification import NotificationTrigger
from app.notifications.services.notification_messages import FALLBACK_CLIENT_NAME, TEMPLATES

logger = get_logger(__name__)

_TEMPLATE_ERROR_CODE = ErrorCode.NOTIFICATION_TEMPLATE_ERROR
_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")


def _check_visible_placeholder(text: str) -> bool:
    """Return True if a {placeholder} is still present after rendering."""
    return bool(_PLACEHOLDER_RE.search(text))


class NotificationTemplateRenderer:
    def render(
        self,
        trigger: NotificationTrigger,
        context: dict,
        person_name: str,
    ) -> tuple[str, str]:
        """
        Render body + subject for trigger.
        Returns (body, subject).
        Raises AppError on: unknown trigger, missing required key, visible placeholder.
        """
        tmpl = TEMPLATES.get(trigger.value)
        if tmpl is None:
            logger.error("NotificationTemplateRenderer: no template for trigger=%s", trigger)
            raise AppError("תבנית ההודעה לא נמצאה עבור סוג זה", _TEMPLATE_ERROR_CODE)

        full_context = {
            "client_name": person_name or FALLBACK_CLIENT_NAME,
            **context,
        }

        try:
            body = tmpl["body"].format(**full_context)
            subject = tmpl["subject"].format(**full_context)
        except KeyError as exc:
            logger.error("NotificationTemplateRenderer: missing key=%s trigger=%s", exc, trigger)
            raise AppError(f"שדה חובה חסר בתבנית ההודעה: {exc}", _TEMPLATE_ERROR_CODE) from exc

        if _check_visible_placeholder(body) or _check_visible_placeholder(subject):
            logger.error(
                "NotificationTemplateRenderer: visible placeholder after render trigger=%s",
                trigger,
            )
            raise AppError("תבנית ההודעה לא מולאה במלואה", _TEMPLATE_ERROR_CODE)

        return body, subject

    def build_preview(
        self,
        trigger: NotificationTrigger,
        context: dict,
        person_name: str,
    ) -> tuple[str | None, str | None, str | None]:
        """
        Preview version for preview endpoint.
        Returns (body, subject, error_reason).
        error_reason is set when rendering fails — caller should return blocked preview.
        Returns (body, subject, None) on success.
        """
        tmpl = TEMPLATES.get(trigger.value)
        if tmpl is None:
            return None, None, "תבנית לא נמצאה עבור סוג הודעה זה"

        full_context = {
            "client_name": person_name or FALLBACK_CLIENT_NAME,
            **context,
        }

        try:
            body = tmpl["body"].format(**full_context)
            subject = tmpl["subject"].format(**full_context)
        except KeyError as exc:
            missing = str(exc).strip("'")
            return None, None, f"שדה חובה חסר בתבנית: {missing}"

        if _check_visible_placeholder(body) or _check_visible_placeholder(subject):
            return None, None, "תבנית ההודעה לא מולאה במלואה — בדוק את נתוני ההקשר"

        return body, subject, None
