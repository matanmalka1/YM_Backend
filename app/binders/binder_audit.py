"""Audit helpers for binder lifecycle / intake-edit events (generic EntityAuditLog).

Binder lifecycle transitions anchor on ``entity_type=binder``; intake edits anchor
on ``entity_type=binder_intake`` with the owning binder carried in
``metadata_json.binder_id``. Writes go through :class:`EntityAuditWriter` so they are
validated fail-closed and appended in the caller's transaction (§17), replacing the
legacy ``BinderLifecycleLog`` / ``BinderIntakeEditLog`` rows (§10b).
"""

from __future__ import annotations

from app.binders.models.binder import Binder


def binder_metadata(binder: Binder) -> dict:
    """metadata_json for binder lifecycle rows (§8): indexed client context + identity."""
    return {
        "client_record_id": binder.client_record_id,
        "binder_id": binder.id,
        "binder_number": binder.binder_number,
    }


def lifecycle_value(field_name: str, value: str | None) -> dict | None:
    """old_value/new_value snapshot for a binder lifecycle field change."""
    if value is None:
        return None
    return {field_name: value}


def intake_metadata(
    *, client_record_id: int, binder_id: int, intake_id: int, field_name: str
) -> dict:
    """metadata_json for a binder_intake.updated row (§8/§10b)."""
    return {
        "client_record_id": client_record_id,
        "binder_id": binder_id,
        "intake_id": intake_id,
        "field_name": field_name,
    }
