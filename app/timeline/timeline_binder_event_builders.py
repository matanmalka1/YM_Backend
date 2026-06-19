from datetime import datetime

from app.timeline.timeline_labels import BINDER_LIFECYCLE_HE


def binder_received_event(binder) -> dict:
    received_on = getattr(binder, "received_at", None) or binder.period_start
    return {
        "event_type": "binder_received",
        "timestamp": datetime.combine(received_on, datetime.min.time()),
        "binder_id": binder.id,
        "charge_id": None,
        "description": f"קלסר {binder.binder_number} התקבל",
        "metadata": {"binder_number": binder.binder_number},
    }


def binder_handed_over_event(binder) -> dict:
    return {
        "event_type": "binder_handed_over",
        "timestamp": datetime.combine(binder.handed_over_at, datetime.min.time()),
        "binder_id": binder.id,
        "charge_id": None,
        "description": f"קלסר {binder.binder_number} נמסר ללקוח",
        "metadata": {
            "binder_number": binder.binder_number,
            "handover_recipient_name": binder.handover_recipient_name,
        },
    }


def binder_lifecycle_change_event(binder, lifecycle_log) -> dict:
    notes = getattr(lifecycle_log, "notes", None)
    if lifecycle_log.old_value == "null":
        description = f"קלסר {binder.binder_number} הגיע למשרד"
    elif lifecycle_log.old_value == lifecycle_log.new_value and notes:
        description = f"קלסר {binder.binder_number}: {notes}"
    else:
        description = (
            f"קלסר {binder.binder_number}: "
            f"{BINDER_LIFECYCLE_HE.get(lifecycle_log.old_value, 'ערך לא ידוע')} "
            f"← {BINDER_LIFECYCLE_HE.get(lifecycle_log.new_value, 'ערך לא ידוע')}"
        )
    metadata = {
        "field_name": lifecycle_log.field_name,
        "old_value": lifecycle_log.old_value,
        "new_value": lifecycle_log.new_value,
    }
    if notes:
        metadata["notes"] = notes
    return {
        "event_type": "binder_lifecycle_change",
        "timestamp": lifecycle_log.changed_at,
        "binder_id": binder.id,
        "charge_id": None,
        "description": description,
        "metadata": metadata,
    }
