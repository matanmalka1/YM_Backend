from app.notifications.models.notification import TRIGGER_LABELS, Notification


def notification_sent_event(n: Notification) -> dict:
    label = TRIGGER_LABELS.get(n.trigger, n.trigger.value)
    return {
        "event_type": "notification_sent",
        "timestamp": n.sent_at or n.created_at,
        "binder_id": n.binder_id,
        "charge_id": None,
        "description": f"הודעה נשלחה: {label}",
        "metadata": {
            "notification_id": n.id,
            "trigger": n.trigger.value,
            "trigger_label": label,
            "channel": n.channel.value,
            "recipient": n.recipient,
        },
    }


def notification_failed_event(n: Notification) -> dict:
    label = TRIGGER_LABELS.get(n.trigger, n.trigger.value)
    return {
        "event_type": "notification_failed",
        "timestamp": n.failed_at or n.created_at,
        "binder_id": n.binder_id,
        "charge_id": None,
        "description": f"שליחת הודעה נכשלה: {label}",
        "metadata": {
            "notification_id": n.id,
            "trigger": n.trigger.value,
            "trigger_label": label,
            "channel": n.channel.value,
            "error_message": n.error_message,
        },
    }
