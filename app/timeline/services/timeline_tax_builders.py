from app.timeline.timeline_labels import ANNUAL_REPORT_STATUS_HE


def annual_report_status_changed_event(report, history) -> dict:
    form_str = report.form_type.value if report.form_type else ""
    from_status = history.from_status.value if history.from_status else None
    to_status = history.to_status.value
    from_he = ANNUAL_REPORT_STATUS_HE.get(from_status, from_status) if from_status else None
    to_he = ANNUAL_REPORT_STATUS_HE.get(to_status, to_status)
    transition = f"{from_he} ← {to_he}" if from_he else to_he
    return {
        "event_type": "annual_report_status_changed",
        "timestamp": history.occurred_at,
        "binder_id": None,
        "charge_id": None,
        "description": f"דוח שנתי {form_str} ({report.tax_year}): {transition}",
        "metadata": {
            "history_id": history.id,
            "annual_report_id": report.id,
            "tax_year": report.tax_year,
            "form_type": form_str,
            "from_status": from_status,
            "to_status": to_status,
            "note": history.note,
        },
    }
