from __future__ import annotations

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class NotificationDeliveryService:
    """
    Sends a notification to a valid recipient via the appropriate channel.

    Contract:
    - Receives a resolved recipient — never decides skipped.
    - Does NOT persist any DB records. SendService owns record creation.
    - Returns (ok: bool, error: str | None).
    """

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        email_channel=None,
    ) -> tuple[bool, str | None]:
        if email_channel is None:
            return False, "email channel not configured"
        ok, err = email_channel.send(recipient, body, subject=subject)
        if not ok:
            logger.error("email delivery failed recipient=%s error=%s", recipient, err)
        return ok, err
