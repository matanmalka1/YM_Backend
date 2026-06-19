from app.timeline.timeline_labels import CHARGE_TYPE_HE


def charge_created_event(charge) -> dict:
    return {
        "event_type": "charge_created",
        "timestamp": charge.created_at,
        "binder_id": None,
        "charge_id": charge.id,
        "description": f"חיוב חדש: {CHARGE_TYPE_HE.get(charge.charge_type.value, 'סוג לא ידוע')}",
        "metadata": {
            "amount": float(charge.amount),
            "status": charge.status.value,
        },
    }


def charge_issued_event(charge) -> dict:
    return {
        "event_type": "charge_issued",
        "timestamp": charge.issued_at,
        "binder_id": None,
        "charge_id": charge.id,
        "description": f"חיוב הונפק: {CHARGE_TYPE_HE.get(charge.charge_type.value, 'סוג לא ידוע')}",
        "metadata": {"amount": float(charge.amount)},
    }


def charge_paid_event(charge) -> dict:
    return {
        "event_type": "charge_paid",
        "timestamp": charge.paid_at,
        "binder_id": None,
        "charge_id": charge.id,
        "description": f"חיוב שולם: {CHARGE_TYPE_HE.get(charge.charge_type.value, 'סוג לא ידוע')}",
        "metadata": {"amount": float(charge.amount)},
    }


def invoice_attached_event(charge, invoice) -> dict:
    return {
        "event_type": "invoice_attached",
        "timestamp": invoice.created_at,
        "binder_id": None,
        "charge_id": charge.id,
        "description": f"חשבונית צורפה: {invoice.external_invoice_id}",
        "metadata": {
            "provider": invoice.provider,
            "external_invoice_id": invoice.external_invoice_id,
        },
    }
